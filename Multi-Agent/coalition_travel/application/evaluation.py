"""Deterministic exact-match metrics for structured request extraction."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from coalition_travel.domain.request import TravelRequestDraft

REQUEST_FIELDS = tuple(TravelRequestDraft.model_fields)


def _normalize(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return sorted(_normalize(item).casefold() for item in value)
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def score_extractions(
    expected: Sequence[TravelRequestDraft],
    actual: Sequence[TravelRequestDraft | None],
) -> dict:
    """Return per-field exact match, full-request accuracy and sample count."""
    if len(expected) != len(actual):
        raise ValueError("expected and actual must contain the same number of records")
    if not expected:
        raise ValueError("evaluation set must not be empty")

    matches = {field: 0 for field in REQUEST_FIELDS}
    request_matches = 0
    for reference, prediction in zip(expected, actual):
        if prediction is None:
            continue
        record_matches = []
        for field in REQUEST_FIELDS:
            matched = _normalize(getattr(reference, field)) == _normalize(
                getattr(prediction, field)
            )
            matches[field] += int(matched)
            record_matches.append(matched)
        request_matches += int(all(record_matches))

    count = len(expected)
    return {
        "samples": count,
        "request_exact_match": request_matches / count,
        "field_exact_match": {field: value / count for field, value in matches.items()},
    }
