"""Composition root of the simulated market (plan 3H/P5, §4.5).

This is the only module of the 3H path that loads the catalogue with its private seller
terms. It hands the terms book to the seller simulator and keeps no other reference to
it: callers receive the public catalogue and journaling sessions only. It is
allow-listed in ``tests/test_offer_catalog.py`` for that reason (reviewed change, I1).

One ``SimulatedMarket`` wraps one deterministic ``SimulatedNegotiationOracle``. Each
planning session gets a fresh ``JournalingNegotiationOracle`` on top of it, so the
journals of a lot never mix with those of another lot.
"""

from datetime import date, datetime
from pathlib import Path

from coalition_travel.domain.offer import OfferCatalog
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from coalition_travel.infrastructure.negotiation.journaling_oracle import (
    JournalingNegotiationOracle,
)
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
)


class SimulatedMarket:
    """Public catalogue plus a factory of journaling negotiation sessions."""

    def __init__(self, catalog: OfferCatalog, oracle: SimulatedNegotiationOracle):
        if type(catalog) is not OfferCatalog:
            raise TypeError("catalog must be an OfferCatalog")
        if type(oracle) is not SimulatedNegotiationOracle:
            raise TypeError("oracle must be a SimulatedNegotiationOracle")
        self._catalog = catalog
        self._oracle = oracle

    @property
    def catalog(self) -> OfferCatalog:
        return self._catalog

    @property
    def reference_date(self) -> date:
        return self._oracle.config.reference_date

    @property
    def oracle_configuration_id(self) -> str:
        return self._oracle.oracle_configuration_id

    def open_session(self) -> JournalingNegotiationOracle:
        """A fresh journaling oracle for one lot; its journals start empty."""
        return JournalingNegotiationOracle(self._oracle)


def open_simulated_market(
    catalog_path: str | Path,
    reference_date: date,
    config: SimulatedOracleConfig | None = None,
) -> SimulatedMarket:
    """Load the catalogue, build the seller simulator and return the public market."""
    if isinstance(reference_date, datetime) or type(reference_date) is not date:
        raise TypeError("reference_date must be a datetime.date")
    if config is None:
        config = SimulatedOracleConfig(reference_date=reference_date)
    elif type(config) is not SimulatedOracleConfig:
        raise TypeError("config must be a SimulatedOracleConfig")
    elif config.reference_date != reference_date:
        raise ValueError("config.reference_date differs from the market reference date")
    catalog, terms_book = load_offer_catalog(catalog_path)
    return SimulatedMarket(catalog, SimulatedNegotiationOracle(catalog, terms_book, config))
