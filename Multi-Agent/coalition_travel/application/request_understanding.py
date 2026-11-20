"""Validation and clarification policy for structured LLM extraction results."""

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from time import perf_counter
from typing import Literal, Protocol

from coalition_travel.application.request_contracts import TravelRequestDraft, is_route_request


class RequestExtractionError(RuntimeError):
    """Base exception for technical failures at the request-extraction boundary."""


class RequestInputError(RequestExtractionError):
    """An individual request cannot be submitted to an extractor as provided."""


class StructuredOutputError(RequestExtractionError):
    """An extractor returned output that does not satisfy its structured contract."""


class ExtractorContractError(RequestExtractionError):
    """An extractor implementation violated the application port contract."""


class RequestProviderError(RequestExtractionError):
    """An external model provider could not complete an extraction request."""


class StructuredRequestExtractor(Protocol):
    async def extract(self, text: str, reference_date: date) -> TravelRequestDraft:
        """Extract facts or raise RequestExtractionError on technical failure."""


class ContextAwareStructuredRequestExtractor(Protocol):
    async def extract_with_context(
        self, text: str, reference_date: date, knowledge_context: str
    ) -> TravelRequestDraft: ...


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
# v2 (route) requests, scope review I4, D-I4-3: closed windows; the return window is
# required for a round trip only. The order is the order of the clarification questions.
REQUIRED_FIELDS_V2 = (
    "origin",
    "destination",
    "travellers",
    "budget_per_person",
    "trip_type",
    "departure_after",
    "departure_before",
    "return_after",
    "return_before",
)
_RETURN_FIELDS = ("return_after", "return_before")


def validate_request_draft(
    request: TravelRequestDraft,
    reference_date: date,
) -> RequestUnderstandingResult:
    """Apply deterministic business checks after schema validation."""
    if not isinstance(reference_date, date) or isinstance(reference_date, datetime):
        raise TypeError("reference_date must be a date")
    if is_route_request(request):  # v2 (I4, D-I4-1); the v1 rule below is unchanged
        missing = _route_missing_fields(request)
    else:
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
    for profile in request.profiles:
        if profile.departure_after and profile.departure_after < reference_date:
            errors.append(f"profile {profile.profile_id}: departure_after is before reference date")
        if profile.arrival_before and profile.arrival_before < reference_date:
            errors.append(f"profile {profile.profile_id}: arrival_before is before reference date")
    if is_route_request(request):
        errors.extend(_route_errors(request, reference_date))
    if errors:
        return RequestUnderstandingResult(status="invalid", request=request, errors=tuple(errors))
    return RequestUnderstandingResult(status="ready", request=request)


def _route_missing_fields(request: TravelRequestDraft) -> tuple[str, ...]:
    """A window bound is present when the request sets it, or when every profile does:
    the effective window of each traveller is then closed (D-I4-3)."""
    required = [name for name in REQUIRED_FIELDS_V2 if name not in _RETURN_FIELDS]
    if request.trip_type == "round_trip":
        required.extend(_RETURN_FIELDS)

    def present(name: str) -> bool:
        if getattr(request, name) is not None:
            return True
        return (
            name in _WINDOW_FIELDS
            and bool(request.profiles)
            and all(getattr(profile, name) is not None for profile in request.profiles)
        )

    return tuple(name for name in REQUIRED_FIELDS_V2 if name in required and not present(name))


_WINDOW_FIELDS = ("departure_after", "departure_before", "return_after", "return_before")


def _route_errors(request: TravelRequestDraft, reference_date: date) -> list[str]:
    """Deterministic v2 checks with fixed messages (domain E of trip-request-status-v2)."""
    errors = []
    for name in ("departure_before", "return_after", "return_before"):
        value = getattr(request, name)
        if value is not None and value < reference_date:
            errors.append(f"{name} must not be before the reference date")
    request_windows = (
        request.departure_after,
        request.departure_before,
        request.return_after,
        request.return_before,
    )
    errors.extend(_window_errors(request.trip_type, *request_windows, prefix=""))
    for profile in request.profiles:
        overrides = (profile.departure_after, *(getattr(profile, n) for n in _PROFILE_WINDOWS))
        if all(value is None for value in overrides):
            continue
        for name in _PROFILE_WINDOWS:
            value = getattr(profile, name)
            if value is not None and value < reference_date:
                errors.append(f"profile {profile.profile_id}: {name} is before reference date")
        effective = tuple(
            override if override is not None else inherited
            for override, inherited in zip(overrides, request_windows)
        )
        own = profile.return_after is not None or profile.return_before is not None
        errors.extend(
            _window_errors(
                request.trip_type,
                *effective,
                prefix=f"profile {profile.profile_id}: ",
                own_return=own,
            )
        )
    return errors


_PROFILE_WINDOWS = ("departure_before", "return_after", "return_before")


def _window_errors(
    trip_type,
    departure_after,
    departure_before,
    return_after,
    return_before,
    *,
    prefix,
    own_return=True,
) -> list[str]:
    errors = []
    if prefix == "":
        if departure_after and departure_before and departure_after > departure_before:
            errors.append("departure_after must not be after departure_before")
        if return_after and return_before and return_after > return_before:
            errors.append("return_after must not be after return_before")
        if trip_type == "one_way" and (return_after or return_before):
            errors.append("a one_way request must not have a return window")
        if return_before and departure_after and return_before < departure_after:
            errors.append("the return window must not end before the departure window starts")
        return errors
    if departure_after and departure_before and departure_after > departure_before:
        errors.append(f"{prefix}the departure window is empty")
    if return_after and return_before and return_after > return_before:
        errors.append(f"{prefix}the return window is empty")
    if trip_type == "one_way" and own_return:
        errors.append(f"{prefix}a one_way request must not have a return window")
    if return_before and departure_after and return_before < departure_after:
        errors.append(f"{prefix}the return window ends before the departure window starts")
    return errors


async def understand_request(
    text: str,
    extractor: StructuredRequestExtractor,
    reference_date: date,
    knowledge_service=None,
) -> RequestUnderstandingResult:
    """Run extraction, schema validation and business validation in order.

    Technical extraction errors intentionally propagate to the caller. They must be
    observable as infrastructure or contract failures, not mislabeled as user input errors.
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
    clean_text = text.strip()
    if knowledge_service is not None:
        context = await asyncio.to_thread(
            knowledge_service.augment_prompt,
            clean_text,
            filters={"domain": "business_knowledge"},
        )
        contextual_extract = getattr(extractor, "extract_with_context", None)
        if contextual_extract is None:
            raise ExtractorContractError(
                "knowledge retrieval requires an extractor with extract_with_context"
            )
        draft = await contextual_extract(clean_text, reference_date, context)
    else:
        draft = await extractor.extract(clean_text, reference_date)
    if not isinstance(draft, TravelRequestDraft):
        raise ExtractorContractError(
            f"extractor must return a validated TravelRequestDraft; received {type(draft).__name__}"
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
