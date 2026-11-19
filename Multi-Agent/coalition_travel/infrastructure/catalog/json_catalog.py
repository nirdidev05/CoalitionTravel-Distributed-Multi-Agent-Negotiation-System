"""Strict loader for the versioned synthetic offer catalogue and its manifest.

The catalogue file is read once; its SHA-256 is computed on those exact bytes, which are
then decoded (strict UTF-8) and parsed. The manifest lives at
``path.with_suffix(".manifest.json")`` (the convention of ``provenance.load_manifest``),
but is parsed here with the same strict reader: ``load_manifest`` returns a silent
"unversioned" sentinel for a missing file and validates nothing, so it is not used.

The returned ``SellerTermsBook`` holds private seller floors. Only the composition root
may call this loader, and it must hand the book to the seller simulator alone.
"""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

from coalition_travel.domain.offer import (
    OfferCatalog,
    OfferQuote,
    PriceTier,
    SellerFloorTier,
    SellerTerms,
    SellerTermsBook,
    validate_seller_terms_against_catalog,
)

CATALOG_KEYS = frozenset({"catalog_version", "currency", "synthetic", "offers"})
OFFER_KEYS = frozenset(
    {
        "offer_id",
        "supplier_id",
        "destination",
        "departure_date",
        "arrival_date",
        "direct",
        "capacity_seats",
        "tiers",
    }
)
TIER_KEYS = frozenset({"min_seats", "list_per_seat_cents", "seller_floor_per_seat_cents"})
MANIFEST_KEYS = frozenset(
    {
        "version",
        "catalog_file",
        "catalog_sha256",
        "synthetic",
        "currency",
        "offers",
        "purpose",
        "limitations",
    }
)
SUPPORTED_CURRENCY = "EUR"
_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class CatalogValidationError(ValueError):
    """The catalogue or its manifest is missing, malformed or inconsistent."""


def load_offer_catalog(path: str | Path) -> tuple[OfferCatalog, SellerTermsBook]:
    """Load, validate and split the catalogue into public offers and private terms."""
    catalog_path = Path(path)
    raw = _read_bytes(catalog_path)
    sha256 = hashlib.sha256(raw).hexdigest()
    document = _strict_json(raw, str(catalog_path))

    manifest_path = catalog_path.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        raise CatalogValidationError(f"missing catalogue manifest: {manifest_path}")
    manifest = _strict_json(_read_bytes(manifest_path), str(manifest_path))

    version, offers, terms = _parse_catalog(document, str(catalog_path))
    _check_manifest(manifest, str(manifest_path), catalog_path.name, sha256, version, len(offers))

    try:
        catalog = OfferCatalog(
            version, sha256, tuple(sorted(offers, key=lambda offer: offer.offer_id))
        )
        book = SellerTermsBook(
            version, sha256, tuple(sorted(terms, key=lambda entry: entry.offer_id))
        )
        validate_seller_terms_against_catalog(catalog, book)
    except (TypeError, ValueError) as exc:
        raise CatalogValidationError(f"{catalog_path}: {exc}") from exc
    return catalog, book


# --- reading -------------------------------------------------------------------------


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise CatalogValidationError(f"cannot read {path}: {exc}") from exc


def _strict_json(raw: bytes, origin: str):
    """Parse JSON refusing decimals, NaN/Infinity, duplicate keys and invalid UTF-8."""

    def reject_float(token):
        raise CatalogValidationError(f"{origin}: decimal number {token} is not allowed")

    def reject_constant(token):
        raise CatalogValidationError(f"{origin}: constant {token} is not allowed")

    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CatalogValidationError(f"{origin}: duplicate key {key!r}")
            result[key] = value
        return result

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogValidationError(f"{origin}: invalid UTF-8") from exc
    try:
        return json.loads(
            text,
            parse_float=reject_float,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicates,
        )
    except json.JSONDecodeError as exc:
        raise CatalogValidationError(f"{origin}: invalid JSON ({exc.msg})") from exc


# --- field checks --------------------------------------------------------------------


def _object(value, keys: frozenset, location: str) -> dict:
    if type(value) is not dict:
        raise CatalogValidationError(f"{location}: expected an object")
    missing = sorted(keys - value.keys())
    unknown = sorted(value.keys() - keys)
    if missing or unknown:
        raise CatalogValidationError(f"{location}: missing {missing}, unknown {unknown}")
    return value


def _string(value, location: str) -> str:
    if type(value) is not str or not value.strip():
        raise CatalogValidationError(f"{location}: expected a non-blank string")
    return value


def _integer(value, location: str) -> int:
    if type(value) is not int:
        raise CatalogValidationError(f"{location}: expected an integer")
    return value


def _boolean(value, location: str) -> bool:
    if type(value) is not bool:
        raise CatalogValidationError(f"{location}: expected a boolean")
    return value


def _iso_date(value, location: str) -> date:
    if type(value) is not str or not _DATE_PATTERN.fullmatch(value):
        raise CatalogValidationError(f"{location}: expected a YYYY-MM-DD date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CatalogValidationError(f"{location}: invalid date {value!r}") from exc


def _parse_catalog(document, origin: str):
    root = _object(document, CATALOG_KEYS, origin)
    version = _string(root["catalog_version"], f"{origin}.catalog_version")
    if root["currency"] != SUPPORTED_CURRENCY:
        raise CatalogValidationError(f"{origin}.currency: only {SUPPORTED_CURRENCY} is supported")
    if root["synthetic"] is not True:
        raise CatalogValidationError(f"{origin}.synthetic: the catalogue must be synthetic")
    raw_offers = root["offers"]
    if type(raw_offers) is not list or not raw_offers:
        raise CatalogValidationError(f"{origin}.offers: expected a non-empty list")

    offers, terms = [], []
    for index, raw_offer in enumerate(raw_offers):
        location = f"{origin}.offers[{index}]"
        item = _object(raw_offer, OFFER_KEYS, location)
        offer_id = _string(item["offer_id"], f"{location}.offer_id")
        location = f"{location} ({offer_id})"
        raw_tiers = item["tiers"]
        if type(raw_tiers) is not list or not raw_tiers:
            raise CatalogValidationError(f"{location}.tiers: expected a non-empty list")
        price_tiers, floor_tiers = [], []
        for tier_index, raw_tier in enumerate(raw_tiers):
            tier_location = f"{location}.tiers[{tier_index}]"
            tier = _object(raw_tier, TIER_KEYS, tier_location)
            seats = _integer(tier["min_seats"], f"{tier_location}.min_seats")
            list_price = _integer(tier["list_per_seat_cents"], f"{tier_location}.list")
            floor = _integer(tier["seller_floor_per_seat_cents"], f"{tier_location}.floor")
            price_tiers.append((seats, list_price))
            floor_tiers.append((seats, floor))
        capacity = _integer(item["capacity_seats"], f"{location}.capacity_seats")
        try:
            offers.append(
                OfferQuote(
                    offer_id=offer_id,
                    catalog_version=version,
                    supplier_id=_string(item["supplier_id"], f"{location}.supplier_id"),
                    destination=_string(item["destination"], f"{location}.destination"),
                    departure_date=_iso_date(item["departure_date"], f"{location}.departure"),
                    arrival_date=_iso_date(item["arrival_date"], f"{location}.arrival"),
                    direct=_boolean(item["direct"], f"{location}.direct"),
                    capacity_seats=capacity,
                    tiers=tuple(PriceTier(seats, price) for seats, price in price_tiers),
                )
            )
            terms.append(
                SellerTerms(
                    offer_id=offer_id,
                    catalog_version=version,
                    capacity_seats=capacity,
                    floor_tiers=tuple(
                        SellerFloorTier(seats, floor) for seats, floor in floor_tiers
                    ),
                )
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, CatalogValidationError):
                raise
            raise CatalogValidationError(f"{location}: {exc}") from exc
    return version, offers, terms


def _check_manifest(manifest, origin, catalog_file, sha256, version, offer_count) -> None:
    item = _object(manifest, MANIFEST_KEYS, origin)
    if item["version"] != version:
        raise CatalogValidationError(f"{origin}: version does not match the catalogue")
    if item["catalog_file"] != catalog_file:
        raise CatalogValidationError(f"{origin}: catalog_file does not name {catalog_file}")
    declared = item["catalog_sha256"]
    if type(declared) is not str or not _SHA256_PATTERN.fullmatch(declared):
        raise CatalogValidationError(f"{origin}: catalog_sha256 must be a lowercase SHA-256")
    if declared != sha256:
        raise CatalogValidationError(
            f"{origin}: catalog_sha256 {declared} does not match the file ({sha256})"
        )
    if item["synthetic"] is not True:
        raise CatalogValidationError(f"{origin}: synthetic must be true")
    if item["currency"] != SUPPORTED_CURRENCY:
        raise CatalogValidationError(f"{origin}: currency must be {SUPPORTED_CURRENCY}")
    if _integer(item["offers"], f"{origin}.offers") != offer_count:
        raise CatalogValidationError(f"{origin}: offers count does not match the catalogue")
    _string(item["purpose"], f"{origin}.purpose")
    limitations = item["limitations"]
    if type(limitations) is not list or not limitations:
        raise CatalogValidationError(f"{origin}.limitations: expected a non-empty list")
    for index, limitation in enumerate(limitations):
        _string(limitation, f"{origin}.limitations[{index}]")
