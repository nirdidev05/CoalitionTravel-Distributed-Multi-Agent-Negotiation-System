"""Canonical JSON of a proposal and closed status documents (scope review §6.4, §7.1).

- A proposal is rendered from a ``TripProposal`` only: field names are the JSON keys,
  rationals are "p/q" strings (the I2 digest convention), dates are ISO strings, and each
  explanation also carries its French ``message``.
- Serialization: ``json.dumps(sort_keys=True, ensure_ascii=False, indent=2)`` plus a
  final newline, in UTF-8. No duration, so the output is identical byte for byte.
- ``trip-request-status-v1``: the document written instead of a proposal for exit codes
  2, 3 and 4 with ``--json``. Its schema is closed for keys **and values** (revision 3):
  the validator refuses anything outside the tables, before writing.
- Every rendered text passes the vocabulary rule; a failure is a system defect.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import is_dataclass
from datetime import date
from fractions import Fraction

from pydantic import ValidationError

from coalition_travel.application.request_contracts import (
    TravelerProfileDraft,
    TravelRequestDraft,
)
from coalition_travel.application.request_understanding import (
    REQUIRED_FIELDS,
    REQUIRED_FIELDS_V2,
)
from coalition_travel.application.trip_planning import RequestRejection
from coalition_travel.application.trip_proposal import Explanation, TripProposal, public_fields
from coalition_travel.infrastructure.presentation.explanations_fr import explanation_message
from coalition_travel.infrastructure.presentation.vocabulary import forbidden_words_in

STATUS_SCHEMA = "trip-request-status-v1"
# v2 (scope review I4, D-I4-10): for route requests only. The v1 schema is unchanged.
STATUS_SCHEMA_V2 = "trip-request-status-v2"
PLACE_FIELDS = ("origin", "destination")
SOURCES = ("draft-json", "llm", "replay")
NOT_VALIDATED_REASONS = ("refused", "empty_answer", "end_of_input")
COMMON_KEYS = frozenset({"schema", "status", "source", "reference_date"})
STATUS_KEYS = {
    "needs_clarification": frozenset({"missing_fields", "rounds"}),
    "invalid": frozenset({"errors"}),
    "request_rejected": frozenset({"reason", "rejection_status", "missing_fields", "errors"}),
    "not_validated": frozenset({"reason"}),
}
MAX_CLARIFICATION_ROUNDS = 3
BUDGET_REJECTIONS = frozenset(
    {"budget_below_one_cent", "budget_out_of_range", "budget_total_out_of_range"}
)


class PresentationError(RuntimeError):
    """A rendered document breaks its contract (schema or vocabulary): a system defect."""


class StatusDocumentError(PresentationError):
    """A status document is outside the closed schema of trip-request-status-v1."""


# --- canonical serialization --------------------------------------------------------------


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n"


def ensure_vocabulary(text: str) -> str:
    found = forbidden_words_in(text)
    if found:
        raise PresentationError(f"forbidden words in a rendered document: {list(found)}")
    return text


def to_data(value):
    """JSON form of a proposal tree."""
    if type(value) is Explanation:
        return {
            "code": value.code,
            "level": value.level,
            "params": to_data(value.params),
            "message": explanation_message(value),
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {name: to_data(item) for name, item in public_fields(value)}
    if isinstance(value, Fraction):
        return f"{value.numerator}/{value.denominator}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {key: to_data(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [to_data(item) for item in value]
    if value is None or isinstance(value, str | int):
        return value
    raise TypeError(f"no JSON form for {type(value).__name__}")


def render_proposal_json(proposal: TripProposal) -> str:
    """The canonical JSON of ``trip-proposal-v1``; accepts a TripProposal only."""
    if type(proposal) is not TripProposal:
        raise TypeError("the JSON renderer accepts a TripProposal only")
    return ensure_vocabulary(canonical_json(to_data(proposal)))


# --- error strings: the closed domain E (§6.4) --------------------------------------------

DRAFT_FIELD_NAMES = frozenset(TravelRequestDraft.model_fields) | frozenset(
    TravelerProfileDraft.model_fields
)


def error_path(loc) -> str:
    """Pydantic location as ``profiles[0].profile_id``; ``$`` is the root, ``?`` an
    unknown name (never the received key itself)."""
    path = ""
    for segment in loc:
        if isinstance(segment, int) and not isinstance(segment, bool):
            path += f"[{segment}]"
        else:
            name = segment if segment in DRAFT_FIELD_NAMES else "?"
            path += f".{name}" if path else name
    return path or "$"


def reduce_validation_error(exc: ValidationError) -> tuple[str, ...]:
    """E8: one ``chemin: type`` line per error, without the received value."""
    return tuple(f"{error_path(item['loc'])}: {item['type']}" for item in exc.errors())


def forbidden_term_error(path: str) -> str:
    """E9 (D-I3-17)."""
    return f"forbidden_term: {path}"


_NAME = "|".join(re.escape(name) for name in sorted(DRAFT_FIELD_NAMES, key=len, reverse=True))
_SEGMENT = rf"(?:(?:{_NAME})(?:\[\d+\])*|\?(?:\[\d+\])*)"
_PATH = rf"(?:\$|{_SEGMENT}(?:\.{_SEGMENT})*)"
_PROFILE_ID = r"[^\n]{1,80}"
VALIDATION_FORMS = (  # E1 to E5: the five messages of validate_request_draft
    re.compile(r"departure_after must not be before the reference date"),
    re.compile(r"arrival_before must not be before the reference date"),
    re.compile(r"departure_after must not be after arrival_before"),
    re.compile(rf"profile {_PROFILE_ID}: departure_after is before reference date"),
    re.compile(rf"profile {_PROFILE_ID}: arrival_before is before reference date"),
)
ERROR_FORMS = VALIDATION_FORMS + (
    re.compile(r"request text must not be blank"),  # E6
    re.compile(r"request text exceeds [1-9]\d* characters"),  # E7
    re.compile(rf"{_PATH}: [a-z][a-z0-9_]*"),  # E8
    re.compile(rf"forbidden_term: {_PATH}"),  # E9
)


def _matches(text, forms) -> bool:
    return isinstance(text, str) and any(form.fullmatch(text) for form in forms)


# --- status documents ---------------------------------------------------------------------


def _common(status: str, source: str, reference_date: date, schema=STATUS_SCHEMA) -> dict:
    return {
        "schema": schema,
        "status": status,
        "source": source,
        "reference_date": reference_date.isoformat(),
    }


def needs_clarification_document(
    *, source, reference_date, missing_fields, rounds, schema=STATUS_SCHEMA
) -> dict:
    return _common("needs_clarification", source, reference_date, schema) | {
        "missing_fields": list(missing_fields),
        "rounds": rounds,
    }


def invalid_document(*, source, reference_date, errors, schema=STATUS_SCHEMA) -> dict:
    return _common("invalid", source, reference_date, schema) | {"errors": list(errors)}


def request_rejected_document(
    *, source, reference_date, rejection: RequestRejection, schema=STATUS_SCHEMA
) -> dict:
    return _common("request_rejected", source, reference_date, schema) | {
        "reason": rejection.reason,
        "rejection_status": "other" if rejection.status is None else rejection.status,
        "missing_fields": list(rejection.missing_fields),
        "errors": list(rejection.errors),
    }


def not_validated_document(*, source, reference_date, reason, schema=STATUS_SCHEMA) -> dict:
    return _common("not_validated", source, reference_date, schema) | {"reason": reason}


def unknown_place_document(*, source, reference_date, fields, known_places) -> dict:
    """v2 only (D-I4-9): which place fields are unknown, and the known canonical names.
    The unknown value itself is never written."""
    return _common("unknown_place", source, reference_date, STATUS_SCHEMA_V2) | {
        "fields": list(fields),
        "known_places": list(known_places),
    }


def _ordered_required(values) -> bool:
    return (
        isinstance(values, list)
        and bool(values)
        and all(isinstance(value, str) for value in values)
        and values == [field for field in REQUIRED_FIELDS if field in values]
        and len(set(values)) == len(values)
    )


def _rejected_exit_code(document) -> int:
    """The five allowed rows of request_rejected (scope review §6.4, revision 3)."""
    reason = document["reason"]
    status = document["rejection_status"]
    missing, errors = document["missing_fields"], document["errors"]
    if not isinstance(missing, list) or not isinstance(errors, list):
        raise StatusDocumentError("missing_fields and errors are lists")
    if reason == "request_not_ready" and status == "needs_clarification":
        if _ordered_required(missing) and errors == []:
            return 2
    elif reason == "request_not_ready" and status == "invalid":
        if missing == [] and errors and all(_matches(e, VALIDATION_FORMS) for e in errors):
            return 3
    elif reason in BUDGET_REJECTIONS and status == "other" and missing == [] and errors == []:
        return 3
    raise StatusDocumentError("request_rejected outside its five allowed rows")


def validate_status_document(document) -> int:
    """Check the closed schema, keys and values; return the exit code of the document."""
    if isinstance(document, dict) and document.get("schema") == STATUS_SCHEMA_V2:
        return _validate_v2(document)
    if not isinstance(document, dict):
        raise StatusDocumentError("a status document is a JSON object")
    status = document.get("status")
    if status not in STATUS_KEYS:
        raise StatusDocumentError("unknown status")
    if set(document) != COMMON_KEYS | STATUS_KEYS[status]:
        raise StatusDocumentError("keys differ from the closed schema")
    if any(value is None for value in document.values()):
        raise StatusDocumentError("no null value is allowed")
    if document["schema"] != STATUS_SCHEMA or document["source"] not in SOURCES:
        raise StatusDocumentError("schema or source outside its domain")
    reference = document["reference_date"]
    if not isinstance(reference, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reference):
        raise StatusDocumentError("reference_date is an ISO date")
    try:
        date.fromisoformat(reference)
    except ValueError as exc:
        raise StatusDocumentError("reference_date is an ISO date") from exc
    if status == "needs_clarification":
        rounds = document["rounds"]
        if not _ordered_required(document["missing_fields"]):
            raise StatusDocumentError("missing_fields: ordered subset of REQUIRED_FIELDS")
        if type(rounds) is not int or not 0 <= rounds <= MAX_CLARIFICATION_ROUNDS:
            raise StatusDocumentError("rounds is an integer from 0 to 3")
        if document["source"] == "draft-json" and rounds != 0:
            raise StatusDocumentError("no clarification round with --draft-json")
        return 2
    if status == "invalid":
        errors = document["errors"]
        if not isinstance(errors, list) or not errors:
            raise StatusDocumentError("errors is a non-empty list")
        if not all(_matches(error, ERROR_FORMS) for error in errors):
            raise StatusDocumentError("an error string is outside the domain E")
        return 3
    if status == "request_rejected":
        return _rejected_exit_code(document)
    if document["reason"] not in NOT_VALIDATED_REASONS:
        raise StatusDocumentError("reason outside refused, empty_answer, end_of_input")
    return 4


# --- trip-request-status-v2 (I4) ----------------------------------------------------------

_ROUTE_FIXED = (
    "departure_before must not be before the reference date",
    "return_after must not be before the reference date",
    "return_before must not be before the reference date",
    "departure_after must not be after departure_before",
    "return_after must not be after return_before",
    "a one_way request must not have a return window",
    "the return window must not end before the departure window starts",
)
ROUTE_VALIDATION_FORMS = tuple(re.compile(re.escape(text)) for text in _ROUTE_FIXED) + (
    re.compile(
        rf"profile {_PROFILE_ID}: (departure_before|return_after|return_before) "
        "is before reference date"
    ),
    re.compile(rf"profile {_PROFILE_ID}: the (departure|return) window is empty"),
    re.compile(rf"profile {_PROFILE_ID}: a one_way request must not have a return window"),
    re.compile(
        rf"profile {_PROFILE_ID}: the return window ends before the departure window starts"
    ),
)
STATUS_KEYS_V2 = STATUS_KEYS | {"unknown_place": frozenset({"fields", "known_places"})}


def _ordered_subset(values, reference) -> bool:
    return (
        isinstance(values, list)
        and bool(values)
        and all(isinstance(value, str) for value in values)
        and values == [field for field in reference if field in values]
        and len(set(values)) == len(values)
    )


def _validate_v2(document) -> int:
    status = document.get("status")
    if not isinstance(status, str) or status not in STATUS_KEYS_V2:
        raise StatusDocumentError("unknown status")
    if set(document) != COMMON_KEYS | STATUS_KEYS_V2[status]:
        raise StatusDocumentError("keys differ from the closed schema")
    if any(value is None for value in document.values()):
        raise StatusDocumentError("no null value is allowed")
    if document["source"] not in SOURCES:
        raise StatusDocumentError("source outside its domain")
    reference = document["reference_date"]
    if not isinstance(reference, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", reference):
        raise StatusDocumentError("reference_date is an ISO date")
    try:
        date.fromisoformat(reference)
    except ValueError as exc:
        raise StatusDocumentError("reference_date is an ISO date") from exc
    validation_forms = VALIDATION_FORMS + ROUTE_VALIDATION_FORMS
    if status == "needs_clarification":
        rounds = document["rounds"]
        if not _ordered_subset(document["missing_fields"], REQUIRED_FIELDS_V2):
            raise StatusDocumentError("missing_fields: ordered subset of REQUIRED_FIELDS_V2")
        if type(rounds) is not int or not 0 <= rounds <= MAX_CLARIFICATION_ROUNDS:
            raise StatusDocumentError("rounds is an integer from 0 to 3")
        if document["source"] == "draft-json" and rounds != 0:
            raise StatusDocumentError("no clarification round with --draft-json")
        return 2
    if status == "invalid":
        errors = document["errors"]
        if not isinstance(errors, list) or not errors:
            raise StatusDocumentError("errors is a non-empty list")
        if not all(_matches(error, ERROR_FORMS + ROUTE_VALIDATION_FORMS) for error in errors):
            raise StatusDocumentError("an error string is outside the domain E")
        return 3
    if status == "unknown_place":
        known = document["known_places"]
        if not _ordered_subset(document["fields"], PLACE_FIELDS):
            raise StatusDocumentError("fields: ordered subset of origin, destination")
        if (
            not isinstance(known, list)
            or not known
            or any(not isinstance(name, str) or not name.strip() for name in known)
            or known != sorted(set(known))
        ):
            raise StatusDocumentError("known_places: sorted, unique, non-blank names")
        return 2
    if status == "request_rejected":
        reason, rejection = document["reason"], document["rejection_status"]
        missing, errors = document["missing_fields"], document["errors"]
        if not isinstance(missing, list) or not isinstance(errors, list):
            raise StatusDocumentError("missing_fields and errors are lists")
        if reason == "request_not_ready" and rejection == "needs_clarification":
            if _ordered_subset(missing, REQUIRED_FIELDS_V2) and errors == []:
                return 2
        elif reason == "request_not_ready" and rejection == "invalid":
            if missing == [] and errors and all(_matches(e, validation_forms) for e in errors):
                return 3
        elif reason in BUDGET_REJECTIONS and rejection == "other" and not missing and not errors:
            return 3
        raise StatusDocumentError("request_rejected outside its five allowed rows")
    if document["reason"] not in NOT_VALIDATED_REASONS:
        raise StatusDocumentError("reason outside refused, empty_answer, end_of_input")
    return 4


def render_status_json(document) -> tuple[str, int]:
    """Validated canonical JSON of a status document, with its exit code."""
    code = validate_status_document(document)
    return ensure_vocabulary(canonical_json(document)), code
