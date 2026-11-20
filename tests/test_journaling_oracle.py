"""3H, I1: journaling adapter under the cache (plan §4.4) and market composition root."""

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from coalition_travel.application.negotiation_cache import CachingNegotiationOracle
from coalition_travel.application.reference_costs import NegotiationOracleContractError
from coalition_travel.domain.negotiation_request import negotiation_request_for
from coalition_travel.domain.offer import OfferCatalog
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from coalition_travel.infrastructure.negotiation.journaling_oracle import (
    JournalConsistencyError,
    JournalingNegotiationOracle,
    NonDeterministicJournalError,
    check_journal_concordance,
)
from coalition_travel.infrastructure.negotiation.market import (
    SimulatedMarket,
    open_simulated_market,
)
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    NegotiationSimulation,
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
)
from p4_support import REFERENCE, make_unit

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data/catalog/catalog_v1.json"


@pytest.fixture(scope="module")
def simulated():
    catalog, terms = load_offer_catalog(CATALOG_PATH)
    return catalog, SimulatedNegotiationOracle(catalog, terms, SimulatedOracleConfig(REFERENCE))


def request_for(catalog, budget="520", seats=1, unit_id="u1"):
    return negotiation_request_for(
        (make_unit(unit_id, seats=seats, budget=budget),), catalog.get("tyo-northstar-20270310")
    )


class ScriptedOracle:
    """Detailed oracle returning scripted simulations (or raising) in call order."""

    def __init__(self, configuration, script):
        self.oracle_configuration_id = configuration
        self.script = list(script)
        self.calls = 0

    def negotiate_detailed(self, request):
        self.calls += 1
        item = self.script[min(self.calls, len(self.script)) - 1]
        if isinstance(item, Exception):
            raise item
        return item


def test_cache_miss_stores_one_canonical_journal_matching_the_outcome(simulated):
    catalog, oracle = simulated
    session = JournalingNegotiationOracle(oracle)
    request = request_for(catalog)
    outcome = session.negotiate(request)
    assert outcome.status == "agreement"
    assert session.oracle_calls == 1
    assert list(session.journals) == [request.request_key]
    journal = session.journal_for(request.request_key)
    check_journal_concordance(journal, outcome)  # J2
    assert (journal.request_key, journal.status, journal.agreed_total_cents) == (
        outcome.request_key,
        outcome.status,
        outcome.agreed_total_cents,
    )
    assert journal.router_iterations == outcome.turns
    assert journal.oracle_configuration_id == outcome.oracle_configuration_id


def test_cache_hit_reuses_the_canonical_journal_without_calling_the_oracle(simulated):
    catalog, oracle = simulated
    session = JournalingNegotiationOracle(oracle)
    cache = CachingNegotiationOracle(session)
    request = request_for(catalog)
    first = cache.negotiate(request)
    journal = session.journal_for(request.request_key)
    second = cache.negotiate(request)
    assert second == first
    assert session.oracle_calls == 1 and len(session.journals) == 1
    assert cache.statistics.hits == 1 and cache.statistics.oracle_calls == 1
    assert session.journal_for(request.request_key) is journal
    check_journal_concordance(journal, second)  # J2 with the cached outcome


def test_same_key_twice_without_cache_is_deduplicated(simulated):
    catalog, oracle = simulated
    session = JournalingNegotiationOracle(oracle)
    request = request_for(catalog)
    session.negotiate(request)
    canonical = session.journal_for(request.request_key)
    session.negotiate(request)
    assert session.oracle_calls == 2
    assert len(session.journals) == 1
    assert session.journal_for(request.request_key) is canonical


@pytest.mark.parametrize("change", ["journal_sha256", "outcome_and_journal_amount"])
def test_same_key_twice_with_a_different_result_raises(simulated, change):
    catalog, oracle = simulated
    request = request_for(catalog)
    real = oracle.negotiate_detailed(request)
    if change == "journal_sha256":
        other = NegotiationSimulation(real.outcome, replace(real.journal, journal_sha256="f" * 64))
    else:  # still concordant, same journal digest field, but another outcome
        amount = real.outcome.agreed_total_cents - 100
        other = NegotiationSimulation(
            replace(real.outcome, agreed_total_cents=amount),
            replace(real.journal, agreed_total_cents=amount),
        )
    session = JournalingNegotiationOracle(
        ScriptedOracle(oracle.oracle_configuration_id, [real, other])
    )
    session.negotiate(request)
    with pytest.raises(NonDeterministicJournalError):
        session.negotiate(request)
    assert len(session.journals) == 1
    assert session.journal_for(request.request_key) is real.journal


def _tampered(journal, field):
    if field == "request_key":
        return replace(journal, request_key="0" * 64)
    if field == "status":
        return replace(
            journal,
            status="rejected",
            terminal_reason="leader_counteroffers_exhausted",
            agreed_total_cents=None,
        )
    if field == "amount":
        return replace(journal, agreed_total_cents=journal.agreed_total_cents - 1)
    if field == "configuration":
        return replace(journal, oracle_configuration_id="another-configuration")
    if field == "turns":
        return replace(
            journal, router_iterations=journal.router_iterations - 1, events=journal.events[:-1]
        )
    raise AssertionError(field)


@pytest.mark.parametrize("field", ["request_key", "status", "amount", "configuration", "turns"])
def test_an_inconsistent_journal_is_refused_and_nothing_is_stored(simulated, field):
    catalog, oracle = simulated
    request = request_for(catalog)
    real = oracle.negotiate_detailed(request)
    bad = NegotiationSimulation(real.outcome, _tampered(real.journal, field))
    scripted = ScriptedOracle(oracle.oracle_configuration_id, [bad])
    session = JournalingNegotiationOracle(scripted)
    cache = CachingNegotiationOracle(session)
    with pytest.raises(JournalConsistencyError):
        cache.negotiate(request)
    assert not session.journals
    with pytest.raises(JournalConsistencyError):
        cache.negotiate(request)  # no cache entry: the oracle is called again
    assert scripted.calls == 2 and cache.statistics.hits == 0


def test_an_outcome_violating_the_contract_leaves_no_orphan_journal(simulated):
    catalog, oracle = simulated
    request = request_for(catalog)
    real = oracle.negotiate_detailed(request)
    too_high = request.reservation_cents + 1
    bad = NegotiationSimulation(
        replace(real.outcome, agreed_total_cents=too_high),
        replace(real.journal, agreed_total_cents=too_high),
    )
    scripted = ScriptedOracle(oracle.oracle_configuration_id, [bad])
    session = JournalingNegotiationOracle(scripted)
    cache = CachingNegotiationOracle(session)
    with pytest.raises(NegotiationOracleContractError):
        cache.negotiate(request)
    assert not session.journals  # refused by the adapter before any storage
    with pytest.raises(NegotiationOracleContractError):
        cache.negotiate(request)
    assert scripted.calls == 2


def test_an_oracle_exception_leaves_no_journal_and_no_cache_entry(simulated):
    catalog, oracle = simulated
    scripted = ScriptedOracle(oracle.oracle_configuration_id, [RuntimeError("seller crashed")])
    session = JournalingNegotiationOracle(scripted)
    cache = CachingNegotiationOracle(session)
    request = request_for(catalog)
    for _ in range(2):
        with pytest.raises(RuntimeError, match="seller crashed"):
            cache.negotiate(request)
    assert not session.journals and session.oracle_calls == 0 and scripted.calls == 2


def test_a_rejected_negotiation_is_journaled_too(simulated):
    catalog, oracle = simulated
    session = JournalingNegotiationOracle(oracle)
    request = request_for(catalog, budget="100")
    outcome = session.negotiate(request)
    assert outcome.status == "rejected" and outcome.agreed_total_cents is None
    journal = session.journal_for(request.request_key)
    assert journal.status == "rejected" and journal.terminal_reason is not None


def test_configuration_identity_and_type_checks(simulated):
    _, oracle = simulated
    session = JournalingNegotiationOracle(oracle)
    assert session.oracle_configuration_id == oracle.oracle_configuration_id
    with pytest.raises(TypeError, match="negotiate_detailed"):
        JournalingNegotiationOracle(type("NoDetail", (), {"oracle_configuration_id": "x"})())
    with pytest.raises(TypeError, match="oracle_configuration_id"):
        JournalingNegotiationOracle(object())
    with pytest.raises(TypeError, match="NegotiationRequest"):
        session.negotiate("not a request")
    with pytest.raises(KeyError):
        session.journal_for("0" * 64)
    with pytest.raises(TypeError):
        session.journals["k"] = None  # read-only view


def test_market_opens_fresh_sessions_and_exposes_public_objects_only():
    market = open_simulated_market(CATALOG_PATH, REFERENCE)
    assert type(market) is SimulatedMarket
    assert type(market.catalog) is OfferCatalog and market.reference_date == REFERENCE
    first, second = market.open_session(), market.open_session()
    assert first is not second
    assert not first.journals and first.oracle_calls == 0
    assert first.oracle_configuration_id == market.oracle_configuration_id
    first.negotiate(request_for(market.catalog))
    assert not second.journals  # sessions never share journals
    public = {type(value).__name__ for value in vars(market).values()}
    assert public == {"OfferCatalog", "SimulatedNegotiationOracle"}


def test_market_refuses_an_inconsistent_configuration():
    with pytest.raises(ValueError, match="reference_date"):
        open_simulated_market(
            CATALOG_PATH, REFERENCE, SimulatedOracleConfig(reference_date=date(2026, 11, 20))
        )
    with pytest.raises(TypeError):
        open_simulated_market(CATALOG_PATH, "2026-11-19")
    config = SimulatedOracleConfig(REFERENCE, seller_concession_rate=Decimal("0.05"))
    custom = open_simulated_market(CATALOG_PATH, REFERENCE, config)
    default = open_simulated_market(CATALOG_PATH, REFERENCE)
    assert custom.oracle_configuration_id != default.oracle_configuration_id
