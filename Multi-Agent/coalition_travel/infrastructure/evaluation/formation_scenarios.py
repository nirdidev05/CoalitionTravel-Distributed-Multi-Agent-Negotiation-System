"""Seeded synthetic scenarios for the P4 experimental protocol (M7, decisions D8 and D9).

This is the only P4 module allowed to build private seller terms (D8, allow-listed in
tests/test_offer_catalog.py). It writes the scenario catalogue in the P1 file format,
reloads it with the strict P1 loader (so every generated scenario passes the P1
validation), builds the simulated oracle itself, and returns public objects only: the
units, the public catalogue, the oracle and a manifest without any floor value.

Controls (specification §11.3):

- admissibility density: each unit-offer pair is admissible with probability
  ``density``, implemented by supplier exclusions on the unit's first profile, so the
  draw is exact and independent per pair; date windows of every profile contain all
  offers and never restrict them;
- solo agreement rate: with the default P3 strategy, a negotiation is rejected exactly
  when the floor total exceeds the reservation (P3-bis). For each unit, an agreement is
  drawn with probability ``agreement_target``; when drawn, the budget per seat is at
  least the lowest admissible floor per seat, otherwise strictly below every one;
- budget heterogeneity: multiplier 1.15 x lognormal(sigma = cv), never below the floor;
- H2: capacity = max(ceil(demand x (1 + margin)), largest tier threshold); the
  ``h2_violation`` family sets capacity = demand - 1 to violate H2 on purpose.

Generated catalogue files belong to the experiment directory and are not versioned.
"""

import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from coalition_travel.application.travel_units import unit_fingerprint
from coalition_travel.domain.negotiation_request import unit_economic_digest
from coalition_travel.domain.offer import OfferCatalog
from coalition_travel.domain.travel_unit import TravelUnit
from coalition_travel.domain.traveler_profile import TravelerProfile
from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog
from coalition_travel.infrastructure.negotiation.simulated_oracle import (
    SimulatedNegotiationOracle,
    SimulatedOracleConfig,
)

SCENARIO_SCHEMA = "p4-scenario-v1"
SCENARIO_REFERENCE_DATE = date(2026, 11, 19)
DESTINATION = "Tokyo"
# Price grids as (min_seats, percent of the base list price per seat), non-increasing.
TIER_GRIDS = {
    "flat": ((1, 100),),
    "moderate": ((1, 100), (3, 95), (6, 90)),
    "steep": ((1, 100), (3, 85), (6, 70)),
}
Family = Literal["factorial", "null", "mutualisation", "isolated", "h2_violation", "large"]
FAMILIES = ("factorial", "null", "mutualisation", "isolated", "h2_violation", "large")


class ScenarioError(ValueError):
    """Invalid parameters, or a generated scenario that breaks its cell preconditions."""


@dataclass(frozen=True)
class ScenarioParameters:
    family: Family = "factorial"
    unit_count: int = 8
    profiles_per_unit: int = 2
    offer_count: int = 2
    capacity_margin_percent: int = 50
    tier_grid: str = "moderate"
    budget_cv_percent: int = 0
    agreement_target_percent: int = 80
    density_percent: int = 60
    seats_per_profile_max: int = 4

    def __post_init__(self):
        if self.family not in FAMILIES:
            raise ScenarioError(f"unknown family {self.family!r}")
        if self.tier_grid not in TIER_GRIDS:
            raise ScenarioError(f"unknown tier grid {self.tier_grid!r}")
        integers = {
            "unit_count": (1, 40),
            "profiles_per_unit": (1, 5),
            "offer_count": (1, 10),
            "capacity_margin_percent": (0, 500),
            "budget_cv_percent": (0, 100),
            "agreement_target_percent": (0, 100),
            "density_percent": (0, 100),
            "seats_per_profile_max": (1, 10),
        }
        for name, (low, high) in integers.items():
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ScenarioError(f"{name} must be an int in [{low}, {high}]")
        if self.family == "h2_violation" and (
            self.tier_grid != "flat" or self.density_percent != 100 or self.unit_count < 2
        ):
            raise ScenarioError("h2_violation needs a flat grid, density 100 and two units")

    def as_dict(self) -> dict:
        return {
            "family": self.family,
            "unit_count": self.unit_count,
            "profiles_per_unit": self.profiles_per_unit,
            "offer_count": self.offer_count,
            "capacity_margin_percent": self.capacity_margin_percent,
            "tier_grid": self.tier_grid,
            "budget_cv_percent": self.budget_cv_percent,
            "agreement_target_percent": self.agreement_target_percent,
            "density_percent": self.density_percent,
            "seats_per_profile_max": self.seats_per_profile_max,
        }

    @property
    def cell_id(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    parameters: ScenarioParameters
    seed_index: int
    reference_date: date
    units: tuple[TravelUnit, ...]
    catalog: OfferCatalog
    oracle: SimulatedNegotiationOracle
    manifest: dict


def derived_seed(cell_id: str, seed_index: int) -> int:
    """First 64 bits of SHA-256(cell_id | seed_index): independent seeds per cell."""
    digest = hashlib.sha256(f"{cell_id}|{seed_index}".encode()).hexdigest()
    return int(digest[:16], 16)


def _tier_floor(tiers: list[dict], seats: int) -> int:
    """Floor per seat of the tier applicable to ``seats`` (largest min_seats <= seats)."""
    applicable = [tier for tier in tiers if tier["min_seats"] <= seats]
    return applicable[-1]["seller_floor_per_seat_cents"]


def build_scenario(params: ScenarioParameters, seed_index: int, output_dir: Path) -> Scenario:
    if not isinstance(params, ScenarioParameters):
        raise TypeError("params must be ScenarioParameters")
    if type(seed_index) is not int or seed_index < 0:
        raise ScenarioError("seed_index must be a non-negative int")
    seed = derived_seed(params.cell_id, seed_index)
    scenario_id = hashlib.sha256(f"{SCENARIO_SCHEMA}|{seed}".encode()).hexdigest()
    rng = random.Random(seed)
    reference = SCENARIO_REFERENCE_DATE

    # Offers and private floors (percent grids applied in integer cents).
    grid = TIER_GRIDS[params.tier_grid]
    offers = []
    for index in range(params.offer_count):
        base = rng.randrange(40_000, 60_001, 100)
        floor_percent = rng.randint(65, 80)
        departure = reference + timedelta(days=120 + 2 * index)
        tiers = []
        for min_seats, percent in grid:
            list_price = base * percent // 100
            tiers.append(
                {
                    "min_seats": min_seats,
                    "list_per_seat_cents": list_price,
                    "seller_floor_per_seat_cents": list_price * floor_percent // 100,
                }
            )
        offers.append(
            {
                "offer_id": f"offer-{index:02d}",
                "supplier_id": f"Supplier{index:02d}",
                "destination": DESTINATION,
                "departure_date": departure.isoformat(),
                "arrival_date": (departure + timedelta(days=1)).isoformat(),
                "direct": index % 2 == 0,
                "tiers": tiers,
            }
        )

    # Units: seats, admissibility draws, then budgets.
    raw_units = []
    for number in range(params.unit_count):
        seats = [
            1 if params.family == "mutualisation" else rng.randint(1, params.seats_per_profile_max)
            for _ in range(params.profiles_per_unit)
        ]
        admissible = [
            index
            for index in range(params.offer_count)
            if rng.random() < params.density_percent / 100
        ]
        raw_units.append({"unit_id": f"u{number:02d}", "seats": seats, "admissible": admissible})

    # Capacities from the demand of the admissible units (H2 by construction, or violated).
    for index, offer in enumerate(offers):
        demand = sum(sum(u["seats"]) for u in raw_units if index in u["admissible"])
        largest_threshold = offer["tiers"][-1]["min_seats"]
        if params.family == "h2_violation":
            largest_unit = max(sum(u["seats"]) for u in raw_units if index in u["admissible"])
            capacity = max(demand - 1, largest_unit, largest_threshold)
            if capacity >= demand:
                raise ScenarioError("the h2_violation cell could not violate H2")
        else:
            capacity = max(
                math.ceil(demand * (100 + params.capacity_margin_percent) / 100),
                largest_threshold,
                1,
            )
        offer["capacity_seats"] = capacity

    units = []
    for raw in raw_units:
        unit_seats = sum(raw["seats"])
        floors = [_tier_floor(offers[index]["tiers"], unit_seats) for index in raw["admissible"]]
        lowest_floor = min(floors) if floors else 50_000
        agree = rng.random() < params.agreement_target_percent / 100
        if agree:
            sigma = params.budget_cv_percent / 100
            multiplier = 1.15 * math.exp(rng.gauss(0.0, sigma) - sigma * sigma / 2)
            per_seat = max(lowest_floor, math.ceil(lowest_floor * multiplier))
        else:
            per_seat = min(lowest_floor - 1, math.floor(lowest_floor * rng.uniform(0.80, 0.97)))
        excluded = tuple(
            sorted(
                offers[index]["supplier_id"]
                for index in range(params.offer_count)
                if index not in raw["admissible"]
            )
        )
        profiles = tuple(
            TravelerProfile(
                profile_id=f"p{position + 1}",
                traveller_count=count,
                destination=DESTINATION,
                budget_per_person=Decimal(per_seat) / 100,
                departure_after=reference + timedelta(days=60 + position),
                arrival_before=reference + timedelta(days=240 + position),
                direct_flight="any",
                excluded_suppliers=excluded if position == 0 else (),
            )
            for position, count in enumerate(raw["seats"])
        )
        destination_key = DESTINATION.casefold()
        units.append(
            TravelUnit(
                raw["unit_id"],
                destination_key,
                profiles,
                unit_fingerprint(destination_key, profiles),
            )
        )

    # Catalogue file in the P1 format, reloaded by the strict P1 loader.
    version = f"scenario-{scenario_id[:12]}"
    document = {
        "catalog_version": version,
        "currency": "EUR",
        "synthetic": True,
        "offers": sorted(offers, key=lambda offer: offer["offer_id"]),
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog_path = output_dir / f"{scenario_id}.json"
    raw_bytes = (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")
    catalog_path.write_bytes(raw_bytes)
    catalog_manifest = {
        "version": version,
        "catalog_file": catalog_path.name,
        "catalog_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "synthetic": True,
        "currency": "EUR",
        "offers": len(offers),
        "purpose": "P4 synthetic experiment scenario",
        "limitations": ["synthetic prices and floors; not a real market"],
    }
    catalog_path.with_suffix(".manifest.json").write_text(
        json.dumps(catalog_manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    catalog, terms_book = load_offer_catalog(catalog_path)
    oracle = SimulatedNegotiationOracle(
        catalog, terms_book, SimulatedOracleConfig(reference_date=reference)
    )
    manifest = {
        "schema": SCENARIO_SCHEMA,
        "scenario_id": scenario_id,
        "cell_id": params.cell_id,
        "parameters": params.as_dict(),
        "seed_index": seed_index,
        "derived_seed": seed,
        "reference_date": reference.isoformat(),
        "catalog_version": catalog.version,
        "catalog_sha256": catalog.sha256,
        "unit_count": len(units),
        "offer_count": len(catalog.offers),
        "units_digest": hashlib.sha256(
            "|".join(sorted(unit_economic_digest(unit) for unit in units)).encode()
        ).hexdigest(),
    }
    return Scenario(
        scenario_id=scenario_id,
        parameters=params,
        seed_index=seed_index,
        reference_date=reference,
        units=tuple(units),
        catalog=catalog,
        oracle=oracle,
        manifest=manifest,
    )
