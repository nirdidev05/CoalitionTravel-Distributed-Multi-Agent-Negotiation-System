"""Validation and clarification policy for structured LLM extraction results."""

from dataclasses import dataclass
from datetime import date, datetime
from time import perf_counter
from typing import Literal, Protocol

from pydantic import ValidationError

from coalition_travel.domain.request import TravelRequestDraft


class StructuredRequestExtractor(Protocol):
    async def extract(self, text: str, reference_date: date) -> TravelRequestDraft:
        """Extract candidate facts; implementations may call an LLM provider."""


@dataclass(frozen=True)
class RequestUnderstandingResult:
    status: Literal["ready", "needs_clarification", "invalid"]
    request: TravelRequestDraft | None = None
    missing_fields: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    latency_ms: float | None = None
    provider: str | None = None
    model: str | None = None


REQUIRED_FIELDS = ("destination", "travellers", "budget_per_person")


def validate_request_draft(
    request: TravelRequestDraft,
    reference_date: date,
) -> RequestUnderstandingResult:
    """Apply deterministic business checks after schema validation."""
    if not isinstance(reference_date, date) or isinstance(reference_date, datetime):
        raise TypeError("reference_date must be a date")
    missing = tuple(field for field in REQUIRED_FIELDS if getattr(request, field) is None)
    if missing:
        return RequestUnderstandingResult(
            status="needs_clarification", request=request, missing_fields=missing
        )

    errors = []
    if request.departure_after and request.departure_after < reference_date:
        errors.append("departure_after must not be before the reference date")
    if request.arrival_before and request.arrival_before < reference_date:
        errors.append("arrival_before must not be before the reference date")
    if (
        request.departure_after
        and request.arrival_before
        and request.departure_after > request.arrival_before
    ):
        errors.append("departure_after must not be after arrival_before")
    if errors:
        return RequestUnderstandingResult(status="invalid", request=request, errors=tuple(errors))
    return RequestUnderstandingResult(status="ready", request=request)


async def understand_request(
    text: str,
    extractor: StructuredRequestExtractor,
    reference_date: date,
) -> RequestUnderstandingResult:
    """Run extraction, schema validation and business validation in order.

    Provider/network errors intentionally propagate to the caller. They must be
    observable as infrastructure failures, not mislabeled as user input errors.
    """
    if not isinstance(reference_date, date) or isinstance(reference_date, datetime):
        raise TypeError("reference_date must be a date")
    if not isinstance(text, str) or not text.strip():
        return RequestUnderstandingResult(
            status="invalid", errors=("request text must not be blank",)
        )
    started = perf_counter()
    provider = getattr(extractor, "provider_name", extractor.__class__.__name__)
    model = getattr(extractor, "model", None)
    try:
        draft = await extractor.extract(text.strip(), reference_date)
    except ValidationError as exc:
        return RequestUnderstandingResult(
            status="invalid",
            errors=(str(exc),),
            latency_ms=(perf_counter() - started) * 1000,
            provider=provider,
            model=model,
        )
    if not isinstance(draft, TravelRequestDraft):
        return RequestUnderstandingResult(
            status="invalid",
            errors=("extractor must return a validated TravelRequestDraft",),
            latency_ms=(perf_counter() - started) * 1000,
            provider=provider,
            model=model,
        )
    result = validate_request_draft(draft, reference_date)
    return RequestUnderstandingResult(
        status=result.status,
        request=result.request,
        missing_fields=result.missing_fields,
        errors=result.errors,
        latency_ms=(perf_counter() - started) * 1000,
        provider=provider,
        model=model,
    )
