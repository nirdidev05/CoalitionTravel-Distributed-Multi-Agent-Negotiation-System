from Message import Message;
from Agent import Agent;
from Leader import CoalitionLeaderAgent;



class BrokerAgent(Agent):
    """
    Agent facilitateur (Directory Facilitator). 
    Implémente l'algorithme de "Couplage" en regroupant les agents par destination.
    """
    def __init__(self, name, coalition_size=3, negotiate_on_formation=True,
                 discounts=None, group_min_fare=400,
                 group_release_date="01-Dec"):
        super().__init__(name)
        if coalition_size < 2:
            raise ValueError("coalition_size must be at least 2")
        self.coalition_size = coalition_size
        self.negotiate_on_formation = negotiate_on_formation
        self.discounts = discounts or {2: 0.05, 3: 0.10, 4: 0.20}
        if any(size < 1 or not 0 <= rate < 1
               for size, rate in self.discounts.items()):
            raise ValueError("discounts must map coalition sizes to rates in [0, 1)")
        if group_min_fare <= 0:
            raise ValueError("group_min_fare must be positive")
        self.group_min_fare = group_min_fare
        self.group_release_date = group_release_date
        self.formation_history = []
        # Dictionnaire pour stocker les listes d'attente : {"Tokyo": [agent1, agent2...]}
        self.subscriptions = {} 

    def receive_message(self, message):
        if message.type == "SUBSCRIBE":
            destination = message.content["destination"]
            buyer = message.sender
            
            # Ajouter l'agent à la liste d'attente pour cette destination
            if destination not in self.subscriptions:
                self.subscriptions[destination] = []
            if buyer in self.subscriptions[destination]:
                return
            self.subscriptions[destination].append(buyer)
            
            print(f"[{self.name}] NOUVELLE INSCRIPTION : {buyer.name} veut aller à {destination}. "
                  f"(Total en attente: {len(self.subscriptions[destination])})")
            
            # Vérifier si le seuil configuré est atteint.
            self.check_for_coalition(destination)

    def check_for_coalition(self, destination):
        group = self.subscriptions[destination]
        
        discount = self.discounts.get(self.coalition_size, 0.0)
        if len(group) == self.coalition_size:
            print(f"\n[{self.name}] COALITION FORMÉE ({self.coalition_size} membres) pour {destination} !")
            self.form_coalition(group, destination, discount=discount)
            self.subscriptions[destination] = [] # Vider la liste

    def form_coalition(self, members, destination, discount):
        """Crée dynamiquement une entité pour représenter le groupe."""
        leader_name = f"Coalition_{destination}_({len(members)}_membres)"
        self.formation_history.append((destination, tuple(members), discount))
        
        # Avertir les membres
        for member in members:
            msg = Message(self, member, "INFORM", f"Coalition formée avec {discount*100}% de réduction!")
            member.receive_message(msg)

        # ÉTAPE 2 — le broker délègue la négociation à un CoalitionLeaderAgent
        print(f"\n  ÉTAPE 2 — Broker crée CoalitionLeaderAgent '{leader_name}' et délègue la négociation.")
        if self.negotiate_on_formation:
            leader = CoalitionLeaderAgent(
                leader_name, members, discount,
                group_min_fare=self.group_min_fare,
                group_release_date=self.group_release_date
            )
            leader.negotiate_for_group()

    def finalize_pending(self, destination, min_size=2):
        """Form one final smaller coalition from buyers still waiting."""
        if min_size < 2:
            raise ValueError("min_size must be at least 2")
        group = self.subscriptions.get(destination, [])
        if len(group) < min_size:
            return None
        discount = self.discounts.get(len(group), 0.0)
        self.form_coalition(group[:], destination, discount)
        self.subscriptions[destination] = []
        return group[:]


