from Message import Message;
from Agent import Agent;


class BuyerAgent(Agent):
    """
    Agent Acheteur (Client).
    Constraints: budget max, deadline, max 6 bids, max 10% increase per bid.
    """
    def __init__(self, name, budget, deadline):
        super().__init__(name)
        self.budget = budget
        self.deadline = deadline
        
        #  Constraints TP
        self.max_bids = 6
        self.bid_count = 0
        self.current_offer = budget * 0.6  # Starts by offering 60% of budget

    def receive_message(self, message):
        print(f"\n{self.name} reçoit: {message}")

        if message.type == "PROPOSE":
            seller_price = message.content["price"]

            # 1. Is the price within my budget?
            if seller_price <= self.budget:
                print(f"{self.name} (Raisonnement): Le prix {seller_price:.2f}€ est dans mon budget ({self.budget}€). J'ACCEPTE.")
                return Message(self, message.sender, "ACCEPT", {"price": seller_price})
            
            # 2. If not, can i make another bid?
            self.bid_count += 1
            if self.bid_count > self.max_bids:
                print(f"{self.name} (Raisonnement): J'ai dépassé mes 6 soumissions. J'abandonne la négociation. JE REJETTE.")
                return Message(self, message.sender, "REJECT", {"reason": "Max bids reached"})

            # 3. Make a counter-offer (Increase by max 10%)
            print(f"{self.name} (Raisonnement): Le prix est trop haut. C'est ma {self.bid_count}ème tentative. J'augmente mon offre de 10%.")
            self.current_offer = min(self.budget, self.current_offer * 1.10) # Increase by 10%
            
            return Message(self, message.sender, "PROPOSE", {"price": self.current_offer})

    def __repr__(self):
        return str(self.__dict__)
