"""B0: the unmodified historical BrokerAgent, run on agents built from TravelUnits.

Protocol (specification section 7, decision recorded there):

- one BuyerAgent per unit: name = unit_id, budget = to_agent_amount(B_u),
  traveller_count = seats(u), deadline = reference_date + 30 days (as in Entry.py);
- one BrokerAgent per destination key, with its historical parameters
  (coalition_size = 3, default discounts) and negotiate_on_formation = False;
- each unit sends SUBSCRIBE with its destination key, in the given arrival order;
- units still waiting at the end are singletons, without finalize_pending, exactly like
  ``_simulate_broker_order`` in Entry.py;
- the historical console output is captured and discarded.

The structure is then re-scored in the P4 game by ``rescore_structure``; the Broker's
own value (budget x discount) is never compared with P4 savings.
"""

import contextlib
import hashlib
import io
import random
from collections.abc import Iterable, Sequence
from datetime import date, timedelta

from BrokerAgent import BrokerAgent
from BuyerAgent import BuyerAgent
from Message import Message

from coalition_travel.domain.coalition_game import Coalition, canonical_structure
from coalition_travel.domain.money import to_agent_amount
from coalition_travel.domain.travel_unit import TravelUnit

B0_ARRIVAL_ORDERS = 20
B0_DEADLINE_DAYS = 30


def arrival_orders(
    unit_ids: Iterable[str], count: int, seed_material: str
) -> tuple[tuple[str, ...], ...]:
    """``count`` deterministic permutations derived from SHA-256(seed_material)."""
    if type(count) is not int or count < 1:
        raise ValueError("count must be a positive int")
    base = tuple(sorted(unit_ids))
    seed = int(hashlib.sha256(seed_material.encode("utf-8")).hexdigest()[:16], 16)
    generator = random.Random(seed)
    orders = []
    for _ in range(count):
        order = list(base)
        generator.shuffle(order)
        orders.append(tuple(order))
    return tuple(orders)


def run_b0(
    units: Sequence[TravelUnit], arrival_order: Sequence[str], reference_date: date
) -> tuple[Coalition, ...]:
    """Structure formed by the historical Broker for one arrival order."""
    by_id = {unit.unit_id: unit for unit in units}
    if len(by_id) != len(units) or any(type(unit) is not TravelUnit for unit in units):
        raise ValueError("units must be TravelUnit instances with unique identifiers")
    if sorted(arrival_order) != sorted(by_id):
        raise ValueError("arrival_order must be a permutation of the unit identifiers")
    brokers: dict[str, BrokerAgent] = {}
    deadline = reference_date + timedelta(days=B0_DEADLINE_DAYS)
    with contextlib.redirect_stdout(io.StringIO()):
        for unit_id in arrival_order:
            unit = by_id[unit_id]
            destination = unit.destination_key
            broker = brokers.get(destination)
            if broker is None:
                broker = BrokerAgent(f"Broker_{destination}", negotiate_on_formation=False)
                brokers[destination] = broker
            buyer = BuyerAgent(
                unit_id,
                to_agent_amount(unit.budget_total_cents),
                deadline,
                reference_date=reference_date,
                traveller_count=unit.seats,
            )
            broker.receive_message(
                Message(buyer, broker, "SUBSCRIBE", {"destination": destination})
            )
    blocks: list[tuple[str, ...]] = []
    for destination, broker in brokers.items():
        blocks.extend(
            tuple(member.name for member in members) for _, members, _ in broker.formation_history
        )
        blocks.extend((buyer.name,) for buyer in broker.subscriptions.get(destination, []))
    structure = canonical_structure(blocks)
    if sorted(unit for block in structure for unit in block) != sorted(by_id):
        raise RuntimeError("the historical Broker did not partition the units")
    return structure
