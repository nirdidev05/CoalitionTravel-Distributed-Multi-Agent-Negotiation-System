"""Command-line demonstrations for the multi-agent negotiation project."""

from datetime import date, timedelta
from itertools import combinations

from Message import Message
from BuyerAgent import BuyerAgent
from SellerAgent import SellerAgent
from BrokerAgent import BrokerAgent
from CoalitionStructureSearch import (
    dp_search, idp_search, ip_search, brute_force_search,
    print_result, validate_partition,
)
from Negotiation import run_alternating_negotiation
from Leader import CoalitionLeaderAgent


BUDGETS = {
    "Alice": 500,
    "Bob": 600,
    "Carol": 550,
    "Dave": 480,
    "Eve": 530,
}
DISCOUNT = {1: 0.00, 2: 0.05, 3: 0.12, 4: 0.08, 5: 0.06}
DISCOUNT_SUPERADDITIVE = {1: 0.00, 2: 0.05, 3: 0.10, 4: 0.20, 5: 0.30}


def coalition_value(coalition, discounts=DISCOUNT):
    """Example characteristic function: group savings in euros."""
    size = len(coalition)
    total_budget = sum(BUDGETS[name] for name in coalition)
    return total_budget * discounts.get(size, 0.0)


def _run_negotiation(buyer, seller, destination, max_turns=30):
    initial = Message(buyer, seller, "CFP", {"destination": destination})
    result, turns = run_alternating_negotiation(initial, seller, max_turns)
    if result is None:
        print(f"  Arrêt après {turns} tours : aucun accord.")
    elif result.type == "ACCEPT":
        print(f"  Accord : {result.content['price']:.2f}€ en {turns} tours.")
    else:
        print(f"  Négociation refusée en {turns} tours.")
    return result, turns


def _simulate_broker_order(arrival_order, destination, reference_date):
    """Run the real threshold broker; unmatched late arrivals remain singletons."""
    broker = BrokerAgent(
        f"Broker_{destination}", coalition_size=3,
        negotiate_on_formation=False, discounts=DISCOUNT,
    )
    buyers = {name: BuyerAgent(name, BUDGETS[name], reference_date + timedelta(days=30),
                                reference_date=reference_date)
              for name in arrival_order}
    for name in arrival_order:
        broker.receive_message(
            Message(buyers[name], broker, "SUBSCRIBE", {"destination": destination})
        )
    structure = [frozenset(m.name for m in members)
                 for _, members, _ in broker.formation_history]
    structure.extend(frozenset([buyer.name])
                     for buyer in broker.subscriptions.get(destination, []))
    validate_partition(arrival_order, structure)
    value = sum(coalition_value(c) for c in structure)
    return value, structure


def _negotiate_structure(structure, discounts, tag, value_fn=None,
                         reference_date=None):
    reference_date = reference_date or date.today()
    print(f"\n  Négociations effectives : {tag}")
    for index, coalition in enumerate(structure, 1):
        names = sorted(coalition)
        members = [BuyerAgent(name, BUDGETS[name], reference_date + timedelta(days=30),
                              reference_date=reference_date)
                   for name in names]
        if len(members) == 1:
            seller = SellerAgent("VendeurSolo", min_price=400, release_date="01-Dec")
            _run_negotiation(members[0], seller, "solo")
            continue
        leader = CoalitionLeaderAgent(
            f"Groupe{index}_{'_'.join(names)}", members,
            discounts.get(len(members), 0.0), v_func=value_fn,
            group_min_fare=400,
        )
        leader.negotiate_for_group()


def run_scenarios(reference_date=None):
    """Run all project demonstrations; reference_date makes deadlines reproducible."""
    reference_date = reference_date or date.today()
    if not isinstance(reference_date, date):
        raise TypeError("reference_date must be a date")

    print("DÉBUT — NÉGOCIATION MULTI-AGENT")
    seller = SellerAgent("AirFrance", min_price=400, release_date="01-Nov")
    alice = BuyerAgent("Alice", 500, reference_date + timedelta(days=13),
                      reference_date=reference_date)
    print("\nSCÉNARIO 1 — Négociation bilatérale")
    _run_negotiation(alice, seller, "Paris")

    print("\nSCÉNARIO 2 — Coalition par le broker")
    broker = BrokerAgent("TravelBroker", group_min_fare=400)
    for name, budget in (("Bob", 550), ("Carol", 600), ("Dave", 520)):
        buyer = BuyerAgent(name, budget, reference_date + timedelta(days=30),
                           reference_date=reference_date)
        broker.receive_message(Message(buyer, broker, "SUBSCRIBE",
                                       {"destination": "Tokyo"}))
    broker4 = BrokerAgent("TravelBroker4", coalition_size=4, group_min_fare=400)
    for name, budget in (("Lina", 540), ("Marc", 560),
                         ("Nora", 580), ("Omar", 600)):
        buyer = BuyerAgent(name, budget, reference_date + timedelta(days=30),
                           reference_date=reference_date)
        broker4.receive_message(Message(buyer, broker4, "SUBSCRIBE",
                                        {"destination": "Rome"}))

    print("\nSCÉNARIO 3 — Préférence blacklist")
    eve = BuyerAgent("Eve", 700, reference_date + timedelta(days=30),
                     blacklist=["AirFrance"], reference_date=reference_date)
    print(" ", eve.receive_message(Message(seller, eve, "PROPOSE", {"price": 350.0})))

    print("\nSCÉNARIO 4 — Pression temporelle, dates relatives")
    frank = BuyerAgent("Frank", 450, reference_date + timedelta(days=5),
                       reference_date=reference_date)
    grace = BuyerAgent("Grace", 450, reference_date + timedelta(days=180),
                       reference_date=reference_date)
    print(f"  Taux plafond Frank : {frank._compute_concession_rate():.1%}")
    print(f"  Taux plafond Grace : {grace._compute_concession_rate():.1%}")
    _run_negotiation(frank, SellerAgent("AirFrance", 400, "01-Nov"), "Londres")
    _run_negotiation(grace, SellerAgent("AirFrance", 400, "01-Nov"), "Londres")

    print("\nSCÉNARIO 5 — Optimisation DP / IDP / IP")
    agents = list(BUDGETS)
    v = lambda coalition: coalition_value(coalition, DISCOUNT)
    print("  Valeurs des coalitions :")
    for size in range(1, len(agents) + 1):
        for group in combinations(agents, size):
            print(f"    {set(group)} : {v(frozenset(group)):.2f}€")
    val_dp, struct_dp, count_dp = dp_search(agents, v)
    val_idp, struct_idp, count_idp, pruned = idp_search(agents, v)
    val_ip, struct_ip, count_ip = ip_search(agents, v)
    val_oracle, struct_oracle, partitions = brute_force_search(agents, v)
    validate_partition(agents, struct_dp)
    validate_partition(agents, struct_idp)
    validate_partition(agents, struct_ip)
    if not all(abs(val_dp - value) < 1e-9
               for value in (val_idp, val_ip, val_oracle)):
        raise RuntimeError("DP, IDP, IP et la référence exhaustive divergent")
    print_result("DP", val_dp, struct_dp, "coalitions évaluées", count_dp)
    print_result("IDP", val_idp, struct_idp, "coalitions évaluées", count_idp,
                 extra=("paires élaguées", pruned))
    print_result("IP", val_ip, struct_ip, "variables ILP", count_ip)
    print_result("Oracle exhaustif", val_oracle, struct_oracle,
                 "partitions parcourues", partitions)
    print(f"  Grand coalition seule : {v(frozenset(agents)):.2f}€")

    print("\nSCÉNARIO 6 — Broker glouton réel comparé à l’optimum IDP")
    order_one = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    greedy_one, structure_one = _simulate_broker_order(
        order_one, "Tokyo-A", reference_date
    )
    print(f"  Ordre {order_one} : {structure_one}, valeur {greedy_one:.2f}€")

    # Pick an arrival order whose first threshold coalition has the lowest value;
    # the Broker itself still decides when and how the coalition forms.
    possible_groups = list(combinations(agents, 3))
    worst_first_group = min(possible_groups, key=lambda c: coalition_value(c))
    order_two = list(worst_first_group) + [name for name in agents if name not in worst_first_group]
    greedy_two, structure_two = _simulate_broker_order(
        order_two, "Tokyo-B", reference_date
    )
    print(f"  Ordre {order_two} : {structure_two}, valeur {greedy_two:.2f}€")
    print(f"  IDP : {struct_idp}, valeur {val_idp:.2f}€")
    print(f"  Écarts IDP : {val_idp-greedy_one:.2f}€ et {val_idp-greedy_two:.2f}€")
    _negotiate_structure(struct_idp, DISCOUNT, "structure optimale", value_fn=v,
                         reference_date=reference_date)

    v_sa = lambda coalition: coalition_value(coalition, DISCOUNT_SUPERADDITIVE)
    val_sa, struct_sa, _, _ = idp_search(agents, v_sa)
    best_split_sa = max(
        v_sa(frozenset(group)) + v_sa(frozenset(set(agents) - set(group)))
        for group in combinations(agents, 2)
    )
    print(f"  Meilleure scission 2+3 : {best_split_sa:.2f}€ ; "
          f"grand coalition : {v_sa(frozenset(agents)):.2f}€")
    print_result("IDP — fonction super-additive", val_sa, struct_sa,
                 "valeur optimale", f"{val_sa:.2f}€")
    _negotiate_structure(struct_sa, DISCOUNT_SUPERADDITIVE,
                         "grande coalition", value_fn=v_sa,
                         reference_date=reference_date)
    print("\nFIN DES SCÉNARIOS")


if __name__ == "__main__":
    run_scenarios()
