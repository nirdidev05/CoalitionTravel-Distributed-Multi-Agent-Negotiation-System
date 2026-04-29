class Message:
    """
    Represents a standard FIPA-ACL Message for agent communication.

    """
    def __init__(self, sender, receiver, type, content):
        self.sender = sender           # Agent Sender
        self.receiver = receiver       # Agent Receiver
        self.type = type       # (CFP, PROPOSE, ACCEPT, REJECT)
        self.content = content         # Contenu (e.g., {"price": 450})

    def __repr__(self): # toString
        return f"[{self.type}] {self.sender.name} -> {self.receiver.name}: {self.content}"
