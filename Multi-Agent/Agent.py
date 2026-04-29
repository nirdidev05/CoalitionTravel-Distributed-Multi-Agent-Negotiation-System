class Agent:
    """Base class for all agents."""
    def __init__(self, name):
        self.name = name

    def receive_message(self, message):
        """Every agent must be able to receive messages."""
        raise NotImplementedError("Subclasses must implement this reasoning logic.")
