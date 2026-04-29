from Message import Message;
from Agent import Agent;
from Leader import CoalitionLeaderAgent;



class BrokerAgent(Agent):
    """
    Agent facilitateur (Directory Facilitator). 
    Implémente l'algorithme de "Couplage" en regroupant les agents par destination.
    """
    def __init__(self, name):
        super().__init__(name)
        # Dictionnaire pour stocker les listes d'attente : {"Tokyo": [agent1, agent2...]}
        self.subscriptions = {} 

    def receive_message(self, message):
        if message.performative == "SUBSCRIBE":
            destination = message.content["destination"]
            buyer = message.sender
            
            # Ajouter l'agent à la liste d'attente pour cette destination
            if destination not in self.subscriptions:
                self.subscriptions[destination] = []
            self.subscriptions[destination].append(buyer)
            
            print(f"[{self.name}] NOUVELLE INSCRIPTION : {buyer.name} veut aller à {destination}. "
                  f"(Total en attente: {len(self.subscriptions[destination])})")
            
            # Vérifier si on peut former une coalition (Règle du TP : 3 ou 4 agents)
            self.check_for_coalition(destination)

    def check_for_coalition(self, destination):
        group = self.subscriptions[destination]
        
        # Logique métier des notes manuscrites du prof :
        # Si 3 agents -> 10% garantis. Si 4 agents -> 20% garantis.
        if len(group) == 4:
            print(f"\n[{self.name}] COALITION OPTIMALE ATTEINTE (4 membres) pour {destination} !")
            self.form_coalition(group, destination, discount=0.20)
            self.subscriptions[destination] = [] # Vider la liste
            
        elif len(group) == 3:
            print(f"\n[{self.name}] COALITION POSSIBLE (3 membres) pour {destination} !")
            # Dans un système plus complexe (IDP/IP), le broker attendrait un peu pour voir
            # si un 4ème arrive. Ici on forme directement la coalition pour la démo.
            self.form_coalition(group, destination, discount=0.10)
            self.subscriptions[destination] = [] # Vider la liste

    def form_coalition(self, members, destination, discount):
        """Crée dynamiquement une entité pour représenter le groupe."""
        leader_name = f"Coalition_{destination}_({len(members)}_membres)"
        
        # Avertir les membres
        for member in members:
            msg = Message(self, member, "INFORM", f"Coalition formée avec {discount*100}% de réduction!")
            member.receive_message(msg)
            
        # Lancer la négociation de groupe
        leader = CoalitionLeaderAgent(leader_name, members, discount)
        leader.negotiate_for_group()


