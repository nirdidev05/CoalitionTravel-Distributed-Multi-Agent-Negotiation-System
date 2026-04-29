from Message import Message;
from Agent import Agent;




class SellerAgent(Agent):
    """
    Agent Fournisseur (Vendeur).
    Constraints: tarif minimal, date de mise en vente.
    """
    def __init__(self, name, min_price, release_date):
        super().__init__(name)
        self.min_price = min_price
        self.release_date = release_date
        self.current_offer = min_price * 1.4  # Starts by asking 40% above minimum price

    def receive_message(self, message):
        print(f"\n{self.name} reçoit: {message}")

        # Module de Raisonnement 
        if message.type == "CFP": # Call For Proposal
            print(f"{self.name} (Raisonnement): Un client cherche un billet. Je propose {self.current_offer:.2f}€.")
            return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})

        elif message.type == "PROPOSE": # agent received offere from buyer agent
            buyer_offer = message.content["price"]
            
            # If the buyer offers more than our absolute minimum, we accept!
            if buyer_offer >= self.min_price:
                print(f"{self.name} (Raisonnement): L'offre de {buyer_offer:.2f}€ est au-dessus de mon minimum ({self.min_price}€). J'ACCEPTE.")
                return Message(self, message.sender, "ACCEPT", {"price": buyer_offer})
            else:
                # Monotonic Concession: We lower our price slightly to reach an agreement
                self.current_offer = max(self.min_price, self.current_offer * 0.90) # Drop price by 10%
                print(f"{self.name} (Raisonnement): L'offre est trop basse. Je fais une contre-proposition à {self.current_offer:.2f}€.")
                return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})
            
    def __repr__(self):
        return str(self.__dict__)