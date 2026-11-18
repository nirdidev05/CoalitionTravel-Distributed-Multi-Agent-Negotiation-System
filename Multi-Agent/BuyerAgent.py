from Message import Message;
from Agent import Agent;
from datetime import date, datetime;
from math import isfinite


class BuyerAgent(Agent):
    """
    Agent Acheteur (Client).
    Constraints: budget max, deadline, max 6 bids, max 10% increase per bid.

    Preferences:
      - blacklist : list of seller names to refuse unconditionally (C1 p.51 — acte déclaratif)
      - preferred : list of seller names to accept without haggling

    Dynamic concession (C2, p.10 — pression temporelle / facteur d'escompte d_i):
      Far from deadline  → small concession (~2%)
      Close to deadline  → large concession (up to 10%)

    Zeuthen strategy (C2, p.13-17):
      The concession amount is driven by the conflict risk: the agent with the
      lower risk concedes. risk → 0 = big concession, risk → 1 = hold firm.
      The deadline-based rate caps the maximum concession (≤ 10%).
    """
    def __init__(self, name, budget, deadline, blacklist=None, preferred=None,
                 reference_date=None):
        super().__init__(name)
        if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not isfinite(budget) or budget <= 0:
            raise ValueError("budget must be a positive number")
        if not isinstance(deadline, (str, date, datetime)):
            raise TypeError("deadline must be a date, datetime, or supported date string")
        self.budget   = budget
        self.deadline = deadline
        self.reference_date = reference_date or date.today()
        if isinstance(self.reference_date, datetime):
            self.reference_date = self.reference_date.date()
        if not isinstance(self.reference_date, date):
            raise TypeError("reference_date must be a date or datetime")

        # Preferences — C1 p.51 (actes déclaratifs : refus catégoriques)
        self.blacklist = blacklist if blacklist is not None else []
        self.preferred = preferred if preferred is not None else []

        # Constraints TP
        self.max_bids = 6
        self.bid_count = 0
        self.current_offer = budget * 0.6  # Starts by offering 60% of budget
        self.payment_due = None

    # ------------------------------------------------------------------
    # Temporal pressure helpers  (C2, page 10)
    # ------------------------------------------------------------------

    def _parse_deadline(self):
        """Parse 'DD-Mon' or 'DD-Mon-YYYY' deadline string into a datetime."""
        if isinstance(self.deadline, datetime):
            return self.deadline
        if isinstance(self.deadline, date):
            return datetime.combine(self.deadline, datetime.min.time())
        if not self.deadline.strip():
            return None
        for fmt in ("%d-%b-%Y", "%d-%b"):
            try:
                dt = datetime.strptime(self.deadline, fmt)
                if fmt == "%d-%b":
                    # No year given — assume current year, or next if already passed
                    dt = dt.replace(year=self.reference_date.year)
                    if dt.date() < self.reference_date:
                        dt = dt.replace(year=dt.year + 1)
                return dt
            except ValueError:
                continue
        return None

    def _compute_concession_rate(self):
        """
        Dynamic concession rate based on temporal pressure (C2, page 10).

        Rubinstein discount factor d_i: the closer d_i is to 1, the more
        patient the agent. Here we map deadline proximity to d_i:
          - deadline > 30 days away  → low urgency  → rate ≈ 2%  (patient)
          - deadline ≤  0 days away  → max urgency  → rate = 10% (impatient)

        Formula:
            urgency = max(0,  1 - days_remaining / 30)
            rate    = 0.02 + urgency * 0.08          ∈ [2%, 10%]
        """
        deadline_dt = self._parse_deadline()
        if deadline_dt is None:
            return 0.10  # fallback: flat 10% if deadline unparseable

        days_remaining = (deadline_dt.date() - self.reference_date).days

        urgency = max(0.0, 1.0 - days_remaining / 30.0)
        rate    = 0.02 + urgency * 0.08
        return round(rate, 4)

    # ------------------------------------------------------------------
    # Zeuthen strategy  (C2, pages 13-17)
    # ------------------------------------------------------------------

    def _zeuthen_risk(self, my_offer, their_offer):
        """Risque de conflit de Zeuthen (C2, page 16).

        Formule DU COURS (à utiliser à l'écrit) — elle suppose u_i(conflit) = 0 :

            risk_i = [u_i(d_i) - u_i(d_j)] / u_i(d_i)

        où d_i = mon offre, d_j = leur offre, u(p) = budget - p.

        Variante IMPLÉMENTÉE ici (plus robuste) — on pénalise le conflit par
        u(conflit) = -budget au lieu de 0 :

            risk_i = [u_i(d_i) - u_i(d_j)] / [u_i(d_i) - u_i(conflit)]
                   = [u_i(d_i) - u_i(d_j)] / [u_i(d_i) + budget]

        Pourquoi ce choix dans le code ? Dans ce TP l'acheteur ne contre-propose
        que si leur_offre > budget, donc u(leur_offre) < 0. Avec u(conflit) = 0
        la formule du cours donne risk >= 1 (plafonné) -> l'acheteur ne concède
        jamais. La pénalité -budget garde un risque GRADUÉ dans [0, 1] et des
        concessions progressives, sans changer l'interprétation Zeuthen :
          risk proche de 1 -> peu à perdre, je TIENS BON (ne concède pas) ;
          risk proche de 0 -> je crains le conflit, c'est à moi de CONCÉDER.
        Règle : à chaque tour, l'agent dont le risque est le plus faible concède.
        """
        u_mine     = self.budget - my_offer       # u_i(d_i) : utilité si MON offre passe
        u_theirs   = self.budget - their_offer    # u_i(d_j) : utilité si j'accepte LEUR offre
        u_conflict = -self.budget                 # cours : 0 ; ici -budget -> risque borné [0,1]

        denom = u_mine - u_conflict
        if denom <= 0:
            return 1.0   # plus rien à perdre -> risque maximal -> je ne concède pas
        risk = (u_mine - u_theirs) / denom
        return max(0.0, min(1.0, risk))

    # ------------------------------------------------------------------
    # Core agent reasoning
    # ------------------------------------------------------------------

    def receive_message(self, message):
        print(f"\n{self.name} reçoit: {message}")

        if message.type == "PROPOSE":
            seller_price = message.content["price"]
            seller_name  = message.sender.name

            # 0. Preferences — blacklist check (C1 p.51 — acte déclaratif de refus)
            if seller_name in self.blacklist:
                print(f"{self.name} (Préférences): {seller_name} est dans ma liste de refus. "
                      f"Je REJETTE sans négocier, même si le prix {seller_price:.2f}€ est attractif.")
                return Message(self, message.sender, "REJECT",
                               {"reason": f"{seller_name} blacklisted"})

            # 0b. Preferred seller — accept immediately if price is in budget
            if seller_name in self.preferred and seller_price <= self.budget:
                print(f"{self.name} (Préférences): {seller_name} est ma compagnie préférée "
                      f"et le prix {seller_price:.2f}€ est dans mon budget. J'ACCEPTE directement.")
                return Message(self, message.sender, "ACCEPT", {"price": seller_price})

            # 1. Is the price within my budget?
            if seller_price <= self.budget:
                print(f"{self.name} (Raisonnement): Le prix {seller_price:.2f}€ est dans mon "
                      f"budget ({self.budget}€). J'ACCEPTE.")
                return Message(self, message.sender, "ACCEPT", {"price": seller_price})

            # 2. Can I make another bid?
            self.bid_count += 1
            if self.bid_count > self.max_bids:
                print(f"{self.name} (Raisonnement): J'ai dépassé mes 6 soumissions. "
                      f"J'abandonne la négociation. JE REJETTE.")
                return Message(self, message.sender, "REJECT",
                               {"reason": "Max bids reached"})

            # 3. Concession = stratégie de Zeuthen (C2 p.13-17) modulée par la
            #    pression temporelle / facteur d'escompte (C2 p.10).
            #    - Zeuthen décide DE COMBIEN concéder via le risque de conflit :
            #      risque faible -> grosse concession ; risque élevé -> on tient bon.
            #    - Le facteur d'escompte (deadline) fixe le PLAFOND de concession.
            risk     = self._zeuthen_risk(self.current_offer, seller_price)
            max_rate = self._compute_concession_rate()        # plafond ∈ [2%, 10%]
            rate     = max_rate * (1.0 - risk)                 # ∈ [0, max_rate] ≤ 10%

            days_remaining = None
            deadline_dt = self._parse_deadline()
            if deadline_dt:
                days_remaining = (deadline_dt.date() - self.reference_date).days

            print(f"{self.name} (Raisonnement): Prix trop haut. "
                  f"Soumission {self.bid_count}/{self.max_bids}. "
                  f"Risque Zeuthen = {risk:.2f} → concession +{rate*100:.1f}% "
                  f"(plafond deadline {max_rate*100:.1f}%, ~{days_remaining}j).")

            if rate <= 1e-9:
                print(f"{self.name} (Zeuthen): mon risque est maximal, je TIENS BON "
                      f"et j'attends que le vendeur concède.")

            self.current_offer = min(self.budget, self.current_offer * (1 + rate))

            return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})

    def __repr__(self):
        return str(self.__dict__)
