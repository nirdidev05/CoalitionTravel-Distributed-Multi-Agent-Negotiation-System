"""Structured request contracts at the natural-language boundary."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TravelRequestDraft(BaseModel):
    """Candidate extracted facts; missing required facts trigger clarification.

    This model is intentionally a draft: an LLM's output is not yet a trusted
    business request. Application validation decides whether it can proceed.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    destination: str | None = Field(default=None, min_length=2, max_length=120)
    travellers: int | None = Field(default=None, ge=1, le=20, strict=True)
    budget_per_person: Decimal | None = Field(default=None, gt=Decimal(0), allow_inf_nan=False)
    currency: Literal["EUR"] = "EUR"
    departure_after: date | None = None
    arrival_before: date | None = None
    direct_flight: Literal["required", "preferred", "any"] = "any"
    excluded_suppliers: list[str] = Field(default_factory=list)

    @field_validator("excluded_suppliers")
    @classmethod
    def normalize_excluded_suppliers(cls, suppliers: list[str]) -> list[str]:
        normalized = [supplier.strip() for supplier in suppliers]
        if any(not supplier for supplier in normalized):
            raise ValueError("excluded supplier names cannot be blank")
        if len({name.casefold() for name in normalized}) != len(normalized):
            raise ValueError("excluded supplier names must be unique")
        return normalized
