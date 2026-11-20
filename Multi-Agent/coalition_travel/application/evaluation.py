"""Deterministic exact-match metrics for structured request extraction."""

import json
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from numbers import Real

from pydantic import BaseModel

from coalition_travel.application.request_contracts import TravelRequestDraft

REQUEST_FIELDS = tuple(TravelRequestDraft.model_fields)


def _normalize(value):
    """Return a typed canonical form; preserve sequence order unless domain says otherwise."""
    if value is None:
        return ("none",)
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (Decimal, Real)):
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError):
            number = Decimal(str(float(value)))
        if number.is_nan():
            return ("number", "NaN")
        if number.is_infinite():
            return ("number", "Infinity" if number > 0 else "-Infinity")
        if number.is_zero():
            return ("number", 0, (0,), 0)
        sign, digits, exponent = number.as_tuple()
        digits = list(digits)
        while digits and digits[-1] == 0:
            digits.pop()
            exponent += 1
        return ("number", sign, tuple(digits), exponent)
    if isinstance(value, datetime):
        return ("datetime", value.isoformat())
    if isinstance(value, date):
        return ("date", value.isoformat())
    if isinstance(value, str):
        return ("str", value.strip().casefold())
    if isinstance(value, BaseModel):
        return _normalize(value.model_dump(mode="python"))
    if isinstance(value, dict):
        pairs = [(_normalize(key), _normalize(item)) for key, item in value.items()]
        return ("dict", tuple(sorted(pairs, key=lambda pair: json.dumps(pair[0], sort_keys=True))))
    if isinstance(value, (list, tuple)):
        return ("list", tuple(_normalize(item) for item in value))
    return (type(value).__qualname__, value)


def _profile_parts(profile):
    """Canonical profile constraints and effectif; profile IDs are technical labels."""
    if isinstance(profile, BaseModel):
        values = profile.model_dump(mode="python")
    elif isinstance(profile, dict):
        values = profile
    else:
        values = vars(profile)
    constraints = {
        key: value for key, value in values.items() if key not in {"profile_id", "traveller_count"}
    }
    if "excluded_suppliers" in constraints and constraints["excluded_suppliers"] is not None:
        constraints["excluded_suppliers"] = sorted(
            (_normalize(item) for item in constraints["excluded_suppliers"]), key=repr
        )
    return _normalize(constraints), _normalize(values.get("traveller_count"))


def _canonical_profiles(profiles):
    return tuple(sorted((_profile_parts(profile) for profile in profiles), key=repr))


def _canonical_profile_constraints(profiles):
    return tuple(
        sorted((constraints for constraints, _ in _canonical_profiles(profiles)), key=repr)
    )


def _normalize_field(field, value):
    if field == "profiles":
        return ("profiles", _canonical_profiles(value))
    if field == "excluded_suppliers" and value is not None:
        return ("suppliers", tuple(sorted((_normalize(item) for item in value), key=repr)))
    return _normalize(value)


def score_extractions(
    expected: Sequence[TravelRequestDraft],
    actual: Sequence[TravelRequestDraft | None],
) -> dict:
    """Score requests and profile segmentation, ignoring profile IDs and list order.

    Numeric values compare by mathematical value (so 500, 500.0 and Decimal("500.00")
    match). Strings compare case-insensitively after trimming. ``None`` remains distinct
    from empty strings and empty collections. Profile IDs are excluded because they do
    not describe traveler needs. The effectif metric compares the multiset of group sizes;
    ``profile_exact_match`` additionally checks each size against its group's constraints.
    """
    if len(expected) != len(actual):
        raise ValueError("expected and actual must contain the same number of records")
    if not expected:
        raise ValueError("evaluation set must not be empty")

    matches = {field: 0 for field in REQUEST_FIELDS}
    profile_counts = 0
    profile_effectifs = 0
    profile_constraints = 0
    profile_exact = 0
    request_matches = 0
    for reference, prediction in zip(expected, actual):
        if prediction is None:
            continue
        record_matches = []
        for field in REQUEST_FIELDS:
            matched = _normalize_field(field, getattr(reference, field)) == _normalize_field(
                field, getattr(prediction, field)
            )
            matches[field] += int(matched)
            record_matches.append(matched)
        request_matches += int(all(record_matches))

        expected_profiles = reference.profiles
        predicted_profiles = prediction.profiles
        profile_counts += int(len(expected_profiles) == len(predicted_profiles))
        profile_effectifs += int(
            tuple(sorted(profile.traveller_count for profile in expected_profiles))
            == tuple(sorted(profile.traveller_count for profile in predicted_profiles))
        )
        profile_constraints += int(
            _canonical_profile_constraints(expected_profiles)
            == _canonical_profile_constraints(predicted_profiles)
        )
        profile_exact += int(
            _canonical_profiles(expected_profiles) == _canonical_profiles(predicted_profiles)
        )

    count = len(expected)
    return {
        "samples": count,
        "request_exact_match": request_matches / count,
        "field_exact_match": {field: value / count for field, value in matches.items()},
        "profile_count_exact_match": profile_counts / count,
        "profile_traveller_counts_exact_match": profile_effectifs / count,
        "profile_constraints_exact_match": profile_constraints / count,
        "profile_exact_match": profile_exact / count,
    }
