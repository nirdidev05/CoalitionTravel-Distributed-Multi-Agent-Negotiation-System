"""Strict loader of the versioned synthetic demand pool (plan 3H/P5, ID-1, step I1).

The pool holds requests that are already structured (``TravelRequestDraft`` fields), not
free text, so that a demonstration lot is reproducible and independent of the LLM. The
file is JSON Lines: one object per line with exactly the keys ``request_id``,
``synthetic`` (must be true) and ``draft``. Budgets are JSON strings ("520.00"): decimal
numbers, NaN and Infinity are refused, as in the catalogue loader.

The manifest lives at ``path.with_suffix(".manifest.json")`` and pins the file's SHA-256,
its version, the catalogue version it targets and the number of requests. Pool request
identifiers start with ``pool-`` so that they never collide with a traveller's request.
"""

import hashlib
import json
import re
from pathlib import Path

from pydantic import ValidationError

from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.trip_planning import DemandPoolSnapshot, PlanningRequest

LINE_KEYS = frozenset({"request_id", "synthetic", "draft"})
MANIFEST_KEYS = frozenset(
    {
        "version",
        "pool_file",
        "pool_sha256",
        "synthetic",
        "catalog_version",
        "requests",
        "purpose",
        "limitations",
    }
)
POOL_ID_PATTERN = re.compile(r"pool-[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class DemandPoolError(ValueError):
    """The demand pool or its manifest is missing, malformed or inconsistent."""


def load_demand_pool(path: str | Path) -> DemandPoolSnapshot:
    """Read the pool once, check it against its manifest and return its requests."""
    pool_path = Path(path)
    raw = _read_bytes(pool_path)
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DemandPoolError(f"{pool_path}: invalid UTF-8") from exc
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise DemandPoolError(f"{pool_path}: the pool is empty")
    requests = []
    for number, line in enumerate(lines, start=1):
        origin = f"{pool_path}:{number}"
        item = _object(_strict_json(line, origin), LINE_KEYS, origin)
        request_id = item["request_id"]
        if type(request_id) is not str or not POOL_ID_PATTERN.fullmatch(request_id):
            raise DemandPoolError(f"{origin}: request_id must match {POOL_ID_PATTERN.pattern}")
        if item["synthetic"] is not True:
            raise DemandPoolError(f"{origin}: synthetic must be true")
        if type(item["draft"]) is not dict:
            raise DemandPoolError(f"{origin}: draft must be an object")
        try:
            draft = TravelRequestDraft.model_validate(item["draft"])
        except ValidationError as exc:
            raise DemandPoolError(f"{origin}: invalid draft ({exc.error_count()} errors)") from exc
        requests.append(PlanningRequest(request_id, draft))
    identifiers = [item.request_id for item in requests]
    if len(set(identifiers)) != len(identifiers):
        raise DemandPoolError(f"{pool_path}: request_id values must be unique")

    manifest_path = pool_path.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        raise DemandPoolError(f"missing demand pool manifest: {manifest_path}")
    try:  # I1 hardening (review reserve 2): one error type for every invalid manifest
        manifest_text = _read_bytes(manifest_path).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DemandPoolError(f"{manifest_path}: invalid UTF-8") from exc
    manifest = _object(
        _strict_json(manifest_text, str(manifest_path)), MANIFEST_KEYS, str(manifest_path)
    )
    origin = str(manifest_path)
    if manifest["pool_file"] != pool_path.name:
        raise DemandPoolError(f"{origin}: pool_file does not name {pool_path.name}")
    declared = manifest["pool_sha256"]
    if type(declared) is not str or not _SHA256_PATTERN.fullmatch(declared):
        raise DemandPoolError(f"{origin}: pool_sha256 must be a lowercase SHA-256")
    if declared != sha256:
        raise DemandPoolError(f"{origin}: pool_sha256 {declared} does not match the file")
    if manifest["synthetic"] is not True:
        raise DemandPoolError(f"{origin}: synthetic must be true")
    if type(manifest["requests"]) is not int or manifest["requests"] != len(requests):
        raise DemandPoolError(f"{origin}: requests count does not match the pool")
    for name in ("version", "catalog_version", "purpose"):
        if type(manifest[name]) is not str or not manifest[name].strip():
            raise DemandPoolError(f"{origin}: {name} must be a non-empty string")
    limitations = manifest["limitations"]
    if type(limitations) is not list or not limitations:
        raise DemandPoolError(f"{origin}: limitations must be a non-empty list")
    if any(type(item) is not str or not item.strip() for item in limitations):
        raise DemandPoolError(f"{origin}: limitations must be non-empty strings")
    return DemandPoolSnapshot(
        version=manifest["version"],
        sha256=sha256,
        catalog_version=manifest["catalog_version"],
        requests=tuple(requests),
    )


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise DemandPoolError(f"cannot read {path}: {exc}") from exc


def _strict_json(text: str, origin: str):
    """Parse JSON refusing decimal numbers, NaN/Infinity and duplicate keys."""

    def reject_float(token):
        raise DemandPoolError(f"{origin}: decimal number {token} is not allowed")

    def reject_constant(token):
        raise DemandPoolError(f"{origin}: constant {token} is not allowed")

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DemandPoolError(f"{origin}: duplicate key {key!r}")
            result[key] = value
        return result

    try:
        return json.loads(
            text,
            parse_float=reject_float,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except json.JSONDecodeError as exc:
        raise DemandPoolError(f"{origin}: invalid JSON ({exc.msg})") from exc


def _object(value, keys: frozenset, origin: str) -> dict:
    if type(value) is not dict:
        raise DemandPoolError(f"{origin}: expected an object")
    missing = sorted(keys - value.keys())
    unknown = sorted(value.keys() - keys)
    if missing or unknown:
        raise DemandPoolError(f"{origin}: missing keys {missing}, unknown keys {unknown}")
    return value
