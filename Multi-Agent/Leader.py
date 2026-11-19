from decimal import Decimal

from Agent import Agent
from CoalitionStructureSearch import print_shapley_transfers
from Message import Message
from Negotiation import run_alternating_negotiation
from SellerAgent import SellerAgent


class CoalitionLeaderAgent(Agent):
    """
    Agent créé dynamiquement. Représente l'ensemble du groupe.
    (Émergence d'une organisation)
    """
    def __init__(self, name, members, discount, v_func=None,
                 group_min_fare=400, group_release_date="01-Dec"):
        super().__init__(name)
        if not members:
            raise ValueError("a coalition must contain at least one member")
        if not 0 <= discount < 1:
            raise ValueError("discount must be in [0, 1)")
        if group_min_fare <= 0:
            raise ValueError("group_min_fare must be positive")
        self.members = members
        self.total_travellers = sum(getattr(member, "traveller_count", 1) for member in members)
        self.discount = discount
        self.v_func = v_func   # si on passe v, on calcule les transferts Shapley après l'accord
        self.group_min_fare = group_min_fare
        self.group_release_date = group_release_date
        self.allocations = None
        self.total_budget = sum((Decimal(str(m.budget)) for m in members), Decimal(0))
        # Initialisés ici pour que receive_message() marche même avant negotiate_for_group()
        self.budget        = self.total_budget / len(members)  # budget moyen par défaut
        self.current_offer = float(self.budget) * 0.6
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
            self.current_offer = min(float(self.budget), self.current_offer * 1.10)
            print(f"[{self.name}] Contre-offre du groupe : {self.current_offer:.2f}€.")
            return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})

    def negotiate_for_group(self):
        print("\n  ÉTAPE 3 — CoalitionLeaderAgent négocie directement avec le vendeur.")
        print("\n--- DÉBUT DE LA NÉGOCIATION DE GROUPE ---")
        print(f"[{self.name}] Je représente {self.total_travellers} voyageurs.")
        print(f"[{self.name}] Budget cumulé : {self.total_budget}€.")
        print(f"[{self.name}] Réduction garantie par la coalition : {self.discount*100:.0f}%.")

        # Tarif catalogue fourni indépendamment des budgets des acheteurs.
        # Les prix négociés sont des totaux pour le nombre de billets du groupe.
        quantity = self.total_travellers
        seller_min_price = self.group_min_fare * quantity * (1 - self.discount)
        seller_initial_offer = self.group_min_fare * 1.4 * quantity * (1 - self.discount)

        group_seller = SellerAgent(
            name="GroupSeller",
            min_price=round(seller_min_price, 2),
            release_date=self.group_release_date,
            initial_offer=round(seller_initial_offer, 2)
        )
        print(f"[{self.name}] Négociation avec {group_seller.name} "
              f"(plancher total : {group_seller.min_price:.2f}€, "
              f"budget total : {self.total_budget:.2f}€).")

        per_person_caps = [getattr(member, "budget_per_person", None) for member in self.members]
        known_caps = [Decimal(str(cap)) for cap in per_person_caps if cap is not None]
        common_cap = min(known_caps) * quantity if known_caps else self.total_budget
        # Convert only at the legacy float-price negotiation boundary.
        self.budget = min(float(self.total_budget), float(common_cap))
        self.current_offer = self.budget * 0.6
        self.bid_count = 0

        initial_msg = Message(self, group_seller, "CFP", {"destination": "groupe"})
        current_msg, _turns = run_alternating_negotiation(
            initial_msg, group_seller, max_turns=30
        )

        if current_msg is None:
            print("  ⚠️  Arrêt forcé après 30 tours — aucun accord groupe trouvé.")
        elif current_msg and current_msg.type == "ACCEPT":
            final_price = current_msg.content["price"]
            print(f"\n[{self.name}] ACCORD OBTENU à {final_price:.2f}€ "
                  f"({final_price/quantity:.2f}€/billet en moyenne).")
            budgets = {m.name: float(m.budget) for m in self.members}
            if self.v_func is not None:
                coalition_set = frozenset(m.name for m in self.members)
                payments = print_shapley_transfers(
                    coalition_set, self.v_func, final_price, budgets=budgets
                )
            else:
                payments = _bounded_equal_allocation(final_price, budgets)
            self.allocations = payments.copy()
            for member in self.members:
                paid = payments[member.name]
                member.payment_due = paid
                print(f"  → {member.name} paie {paid:.2f}€ "
                      f"(budget : {member.budget:.2f}€, reste : {member.budget-paid:.2f}€)")
            solo_seller_min = round(self.group_min_fare * quantity, 2)
            print("\n  ┌─ Avantage réel de la coalition :")
            print(f"  │  Plancher sans remise : {solo_seller_min:.2f}€ au total")
            print(f"  │  Plancher avec remise : {group_seller.min_price:.2f}€ au total")
            print(f"  │  Économie plancher    : {solo_seller_min-group_seller.min_price:.2f}€ au total")
            print("  └───────────────────────────────────────────────────────")
        else:
            print(f"[{self.name}] Négociation de groupe échouée.")

        print("-----------------------------------------\n")


def _bounded_equal_allocation(total, budgets):
    """Allocate equally where possible, respecting every member's budget."""
    if total > sum(budgets.values()) + 1e-8:
        raise ValueError("agreement exceeds the coalition's combined budget")
    remaining = set(budgets)
    payments = {name: 0.0 for name in budgets}
    amount_left = float(total)
    while remaining:
        share = amount_left / len(remaining)
        capped = [name for name in remaining
                  if share > budgets[name] - payments[name] + 1e-10]
        if not capped:
            for name in remaining:
                payments[name] += share
            break
        for name in capped:
            cap = budgets[name] - payments[name]
            payments[name] += cap
            amount_left -= cap
            remaining.remove(name)
    return payments


