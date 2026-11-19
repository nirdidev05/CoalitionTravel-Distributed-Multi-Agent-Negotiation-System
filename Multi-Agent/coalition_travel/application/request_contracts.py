"""Pydantic contracts at the natural-language request boundary."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TravelerProfileDraft(BaseModel):
    """One explicitly stated group of travelers sharing negotiation constraints."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    profile_id: str = Field(min_length=1, max_length=80)
    traveller_count: int = Field(ge=1, le=20, strict=True)
    budget_per_person: Decimal | None = Field(default=None, gt=Decimal(0), allow_inf_nan=False)
    departure_after: date | None = None
    arrival_before: date | None = None
    direct_flight: Literal["required", "preferred", "any"] | None = None
    excluded_suppliers: list[str] | None = None

    @field_validator("excluded_suppliers")
    @classmethod
    def normalize_excluded_suppliers(cls, suppliers: list[str] | None) -> list[str] | None:
        if suppliers is None:
            return None
        normalized = [supplier.strip() for supplier in suppliers]
        if any(not supplier for supplier in normalized):
            raise ValueError("excluded supplier names cannot be blank")
        if len({name.casefold() for name in normalized}) != len(normalized):
            raise ValueError("excluded supplier names must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_profile_window(self):
        if (
            self.departure_after
            and self.arrival_before
            and self.departure_after > self.arrival_before
        ):
            raise ValueError("profile departure_after must not be after arrival_before")
        return self


class TravelRequestDraft(BaseModel):
    """Untrusted candidate facts extracted from one traveler request."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    destination: str | None = Field(default=None, min_length=2, max_length=120)
    travellers: int | None = Field(default=None, ge=1, le=20, strict=True)
    budget_per_person: Decimal | None = Field(default=None, gt=Decimal(0), allow_inf_nan=False)
    currency: Literal["EUR"] = "EUR"
    departure_after: date | None = None
    arrival_before: date | None = None
    direct_flight: Literal["required", "preferred", "any"] = "any"
    excluded_suppliers: list[str] = Field(default_factory=list)
    profiles: list[TravelerProfileDraft] = Field(default_factory=list)

    @field_validator("excluded_suppliers")
    @classmethod
    def normalize_excluded_suppliers(cls, suppliers: list[str]) -> list[str]:
        normalized = [supplier.strip() for supplier in suppliers]
        if any(not supplier for supplier in normalized):
            raise ValueError("excluded supplier names cannot be blank")
        if len({name.casefold() for name in normalized}) != len(normalized):
            raise ValueError("excluded supplier names must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_profile_total(self):
        if self.profiles and self.travellers is not None:
            represented = sum(profile.traveller_count for profile in self.profiles)
            if represented != self.travellers:
                raise ValueError(
                    f"profile traveller counts ({represented}) must equal travellers ({self.travellers})"
                )
        if len({profile.profile_id for profile in self.profiles}) != len(self.profiles):
            raise ValueError("profile_id values must be unique")
        return self
