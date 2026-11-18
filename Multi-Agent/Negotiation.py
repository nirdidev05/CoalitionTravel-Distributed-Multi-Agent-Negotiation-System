"""Reusable alternating-offers protocol for one-to-one and group negotiations."""

from Message import Message


TERMINAL_TYPES = {"ACCEPT", "REJECT"}


def run_alternating_negotiation(initial_message, first_receiver, max_turns=30):
    """Run a FIPA alternating-offers exchange until it reaches a terminal message.

    The participants remain autonomous: this function only routes each reply to the
    receiver named by the returned message. It works for BuyerAgent/SellerAgent as
    well as CoalitionLeaderAgent/ SellerAgent exchanges.
    """
    current_message = initial_message
    receiver = first_receiver
    turns = 0

    while current_message and current_message.type not in TERMINAL_TYPES:
        if turns >= max_turns:
            return None, turns
        reply = receiver.receive_message(current_message)
        current_message = reply
        if current_message:
            receiver = current_message.receiver
        turns += 1

    return current_message, turns


def negotiation_succeeded(message):
    """Return whether a negotiation ended with an agreement."""
    return bool(message and message.type == "ACCEPT")
