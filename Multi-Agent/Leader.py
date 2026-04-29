from Message import Message;
from Agent import Agent;



class CoalitionLeaderAgent(Agent):
    """
    Agent créé dynamiquement. Représente l'ensemble du groupe.
    (Émergence d'une organisation)
    """
    def __init__(self, name, members, discount):
        super().__init__(name)
        self.members = members
        self.discount = discount
        # Le budget du groupe est la somme des budgets individuels
        self.total_budget = sum(m.budget for m in members)

    def negotiate_for_group(self):
        print(f"\n--- DÉBUT DE LA NÉGOCIATION DE GROUPE ---")
        print(f"[{self.name}] Je représente {len(self.members)} acheteurs.")
        print(f"[{self.name}] Notre budget cumulé est de {self.total_budget}€.")
        print(f"[{self.name}] Nous exigeons la réduction garantie de {self.discount*100}%.")
        
        # Ici on appellerait le SellerAgent comme dans la partie 1, 
        # mais en utilisant le pouvoir d'achat du groupe !
        print(f"[{self.name}] Négociation groupée réussie grâce à la coopération !")
        print(f"-----------------------------------------\n")


