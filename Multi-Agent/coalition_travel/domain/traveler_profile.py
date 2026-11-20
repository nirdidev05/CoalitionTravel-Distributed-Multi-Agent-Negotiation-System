"""Technology-independent traveler profile and common-offer facts."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class TravelerProfile:
    profile_id: str
    traveller_count: int
    destination: str
    budget_per_person: Decimal
    departure_after: date | None = None
    arrival_before: date | None = None
    direct_flight: Literal["required", "preferred", "any"] = "any"
    excluded_suppliers: tuple[str, ...] = ()
    # Effective route windows of a v2 request (I4); always None on the v1 path.
    departure_before: date | None = None
    return_after: date | None = None
    return_before: date | None = None

    @property
    def route_windows(self) -> tuple[date | None, date | None, date | None]:
        return (self.departure_before, self.return_after, self.return_before)

    def __post_init__(self):
        if not self.profile_id.strip() or not self.destination.strip():
            raise ValueError("profile_id and destination must not be blank")
        if (
            isinstance(self.traveller_count, bool)
            or not isinstance(self.traveller_count, int)
            or self.traveller_count < 1
        ):
            raise ValueError("traveller_count must be positive")
        budget = Decimal(str(self.budget_per_person))
        if not budget.is_finite() or budget <= 0:
            raise ValueError("budget_per_person must be finite and positive")
        object.__setattr__(self, "budget_per_person", budget)

    @property
    def total_budget(self) -> Decimal:
        return self.budget_per_person * self.traveller_count


@dataclass(frozen=True)
class CommonOffer:
    destination: str
    price_per_person: Decimal
    departure_date: date | None = None
    arrival_date: date | None = None
    direct: bool | None = None
    supplier: str | None = None

    def __post_init__(self):
        if not self.destination.strip():
            raise ValueError("offer destination must not be blank")
        price = Decimal(str(self.price_per_person))
        if not price.is_finite() or price <= 0:
            raise ValueError("offer price_per_person must be finite and positive")
        object.__setattr__(self, "price_per_person", price)
        if self.supplier is not None and not self.supplier.strip():
            raise ValueError("offer supplier must not be blank")


@dataclass(frozen=True)
class CompatibilityResult:
    status: Literal["compatible", "conditional", "incompatible"]
    reasons: tuple[str, ...]
    profile_ids: tuple[str, ...]
    knowledge_sources: tuple[str, ...] = ()
