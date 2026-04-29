from Message import Message;
from BuyerAgent import BuyerAgent;
from SellerAgent import SellerAgent;



if __name__ == "__main__":
    print("DÉBUT DE LA NÉGOCIATION MULTI-AGENT")
    
    # Instantiattion
    airfrance = SellerAgent(name="AirFrance", min_price=400, release_date="01-Nov")
    print(repr(airfrance))
    print("----------")
    alice = BuyerAgent(name="Alice", budget=500, deadline="01-Dec")
    print(repr(alice))
    print("----------")

    # Alice initiates the conversation CFP
    initial_msg = Message(alice, airfrance, "CFP", {"destination": "Paris"})
    current_msg = initial_msg
    next_receiver = airfrance

    # The Negotiation Loop (Rubinstein alternating offers protocol)
    while current_msg and current_msg.type not in ["ACCEPT", "REJECT"]:
        reply_msg = next_receiver.receive_message(current_msg)
        
        current_msg = reply_msg
        if current_msg:
            next_receiver = current_msg.receiver

    print("\n FIN DE LA NÉGOCIATION ")

