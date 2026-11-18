from Message import Message;
from Agent import Agent;
from SellerAgent import SellerAgent;
from CoalitionStructureSearch import print_shapley_transfers;
from Negotiation import run_alternating_negotiation;



class CoalitionLeaderAgent(Agent):
    """
    Agent créé dynamiquement. Représente l'ensemble du groupe.
    (Émergence d'une organisation)
    """
    def __init__(self, name, members, discount, v_func=None):
        super().__init__(name)
        self.members = members
        self.discount = discount
        self.v_func = v_func   # si on passe v, on calcule les transferts Shapley après l'accord
        self.total_budget = sum(m.budget for m in members)
        # Initialisés ici pour que receive_message() marche même avant negotiate_for_group()
        self.budget        = self.total_budget / len(members)  # budget moyen par défaut
        self.current_offer = self.budget * 0.6
        self.bid_count     = 0

    def receive_message(self, message):
        """Le leader réagit comme un acheteur lors de la négociation de groupe."""
        if message.type == "PROPOSE":
            seller_price = message.content["price"]
            if seller_price <= self.budget:
                print(f"[{self.name}] Prix {seller_price:.2f}€ acceptable. J'ACCEPTE pour le groupe.")
                return Message(self, message.sender, "ACCEPT", {"price": seller_price})
            self.bid_count += 1
            if self.bid_count > 6:
                print(f"[{self.name}] Max soumissions atteint. REJET.")
                return Message(self, message.sender, "REJECT", {"reason": "Max bids reached"})
            self.current_offer = min(self.budget, self.current_offer * 1.10)
            print(f"[{self.name}] Contre-offre du groupe : {self.current_offer:.2f}€.")
            return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})

    def negotiate_for_group(self):
        print(f"\n  ÉTAPE 3 — CoalitionLeaderAgent négocie directement avec le vendeur.")
        print(f"\n--- DÉBUT DE LA NÉGOCIATION DE GROUPE ---")
        print(f"[{self.name}] Je représente {len(self.members)} acheteurs.")
        print(f"[{self.name}] Budget cumulé : {self.total_budget}€.")
        print(f"[{self.name}] Réduction garantie par la coalition : {self.discount*100:.0f}%.")

        # Le budget moyen du groupe sert de base pour le vendeur
        # on applique la réduction de la coalition sur le prix min du vendeur
        avg_budget = self.total_budget / len(self.members)
        seller_min_price = avg_budget * 0.7 * (1 - self.discount)

        group_seller = SellerAgent(
            name="GroupSeller",
            min_price=round(seller_min_price, 2),
            release_date="01-Dec"
        )
        print(f"[{self.name}] Négociation avec {group_seller.name} "
              f"(prix min vendeur : {group_seller.min_price}€, "
              f"budget moyen acheteurs : {avg_budget:.2f}€).")

        # on utilise le budget moyen (pas le cumulé) pour ne pas écraser la négo
        self.budget = avg_budget
        self.current_offer = avg_budget * 0.6
        self.bid_count = 0

        initial_msg = Message(self, group_seller, "CFP", {"destination": "groupe"})
        current_msg, turns = run_alternating_negotiation(
            initial_msg, group_seller, max_turns=30
        )

        if current_msg is None:
            print("  ⚠️  Arrêt forcé après 30 tours — aucun accord groupe trouvé.")
        elif current_msg and current_msg.type == "ACCEPT":
            final_price = current_msg.content["price"]
            print(f"\n[{self.name}] ACCORD OBTENU à {final_price:.2f}€ "
                  f"(soit {final_price/len(self.members):.2f}€/personne grâce à la coalition).")
            share = final_price / len(self.members)
            for m in self.members:
                print(f"  → {m.name} paie {share:.2f}€ (budget initial : {m.budget}€, "
                      f"économie : {m.budget - share:.2f}€)")
            # partie c : si v est dispo, on affiche les transferts de tokens entre membres
            if self.v_func is not None:
                coalition_set = frozenset(m.name for m in self.members)
                print_shapley_transfers(coalition_set, self.v_func, final_price)
            # Avantage réel de la coalition : prix min vendeur avec vs sans réduction
            solo_seller_min = round(avg_budget * 0.7, 2)
            print(f"\n  ┌─ Avantage réel de la coalition :")
            print(f"  │  Prix min vendeur SANS coalition : {solo_seller_min:.2f}€/pers.")
            print(f"  │  Prix min vendeur AVEC coalition : {group_seller.min_price:.2f}€/pers.  (−{self.discount*100:.0f}% garanti par le groupe)")
            print(f"  │  Gain garanti par le groupe      : {solo_seller_min - group_seller.min_price:.2f}€/pers.")
            print(f"  └───────────────────────────────────────────────────────")
        else:
            print(f"[{self.name}] Négociation de groupe échouée.")

        print(f"-----------------------------------------\n")


