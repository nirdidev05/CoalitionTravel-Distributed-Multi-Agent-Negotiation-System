"""Shared builders for the P4 tests (not a test module)."""

import hashlib
import itertools
import random
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from coalition_travel.domain.coalition_game import CoalitionGame, build_game
from coalition_travel.domain.negotiation_request import NegotiationOutcome
from coalition_travel.domain.offer import OfferCatalog, OfferQuote, PriceTier
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile

REFERENCE = date(2026, 11, 19)
TEST_CONFIGURATION = "table-oracle-configuration"


def make_unit(unit_id, seats=1, budget="500", excluded=(), destination="Tokyo"):
    profile = TravelerProfile(
        "p1", seats, destination, Decimal(budget), excluded_suppliers=tuple(excluded)
    )
    return TravelUnit(
        unit_id, destination.casefold(), (profile,), hashlib.sha256(unit_id.encode()).hexdigest()
    )


def make_offer(offer_id, *, supplier=None, tiers=((1, 50_000),), capacity=40, destination="Tokyo"):
    return OfferQuote(
        offer_id,
        "p4-test",
        supplier or f"Supplier-{offer_id}",
        destination,
        date(2027, 3, 10),
        date(2027, 3, 11),
        True,
        capacity,
        tuple(PriceTier(seats, price) for seats, price in tiers),
    )


def make_catalog(offers):
    return OfferCatalog("p4-test", "e" * 64, tuple(sorted(offers, key=lambda o: o.offer_id)))


class TableOracle:
    """Configured oracle whose agreed totals come from ``price(unit_ids, offer_id)``.

    ``price`` returns cents or None (rejected). Units must be economically distinct in
    tests that rely on unit identities, because the P4 cache is economic.
    """

    def __init__(
        self,
        price: Callable[[tuple[str, ...], str], int | None],
        configuration: str = TEST_CONFIGURATION,
    ):
        self.price = price
        self.oracle_configuration_id = configuration
        self.calls = []

    def negotiate(self, request):
        unit_ids = tuple(unit.unit_id for unit in request.units)
        self.calls.append((unit_ids, request.offer.offer_id))
        amount = self.price(unit_ids, request.offer.offer_id)
        if amount is None:
            return NegotiationOutcome(
                request.request_key, "rejected", None, 14, self.oracle_configuration_id
            )
        return NegotiationOutcome(
            request.request_key, "agreement", amount, 3, self.oracle_configuration_id
        )


def random_game(rng: random.Random, n: int, feasible_probability=0.45, low=-400, high=900):
    """Random game with singletons feasible (v = 0) and random multi-unit values."""
    players = tuple(f"u{index}" for index in range(n))
    references = {unit: 10_000 + 100 * index for index, unit in enumerate(players)}
    costs = {(unit,): references[unit] for unit in players}
    for size in range(2, n + 1):
        for coalition in itertools.combinations(players, size):
            if rng.random() < feasible_probability:
                value = rng.choice((0, rng.randint(low, high)))
                costs[coalition] = sum(references[u] for u in coalition) - value
            else:
                costs[coalition] = None
    return build_game("component-test", references, costs, TEST_CONFIGURATION)


def set_partitions(items):
    """All set partitions of ``items`` (independent reference enumeration)."""
    items = list(items)
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for partition in set_partitions(rest):
        yield [[first], *partition]
        for index in range(len(partition)):
            yield [*partition[:index], [first, *partition[index]], *partition[index + 1 :]]


def exclusion_optimum(game: CoalitionGame):
    """Best (V, number of blocks) over partitions into feasible blocks only."""
    best = None
    for partition in set_partitions(game.players):
        blocks = [tuple(sorted(block)) for block in partition]
        if not all(game.is_feasible(block) for block in blocks):
            continue
        key = (sum(game.value(block) for block in blocks), len(blocks))
        if best is None or key > best:
            best = key
    return best
