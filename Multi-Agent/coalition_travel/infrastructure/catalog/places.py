"""Strict loader of the closed place directory ``places_v1.json`` (ID-11, plan §6.5, I4).

The file is read once; its SHA-256 is computed on those bytes and checked against the
manifest ``places_v1.manifest.json``, with the same strict JSON reader as the catalogue
(no decimal number, no NaN, no duplicate key). ``check_catalog_places`` ties the
directory to a package catalogue: every origin and destination must be a canonical name.
"""

import hashlib
import re
from pathlib import Path

from coalition_travel.domain.offer import OfferCatalog
from coalition_travel.domain.places import Place, PlaceDirectory, PlaceDirectoryError
from coalition_travel.infrastructure.catalog.json_catalog import (
    CatalogValidationError,
    _integer,
    _object,
    _read_bytes,
    _strict_json,
    _string,
)

DIRECTORY_KEYS = frozenset({"version", "places"})
PLACE_KEYS = frozenset({"name", "aliases"})
MANIFEST_KEYS = frozenset(
    {"version", "places_file", "places_sha256", "places", "purpose", "limitations"}
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def load_place_directory(path: str | Path) -> PlaceDirectory:
    """Read the directory and its manifest; refuse any inconsistency."""
    directory_path = Path(path)
    raw = _read_bytes(directory_path)
    sha256 = hashlib.sha256(raw).hexdigest()
    origin = str(directory_path)
    root = _object(_strict_json(raw, origin), DIRECTORY_KEYS, origin)
    version = _string(root["version"], f"{origin}.version")
    raw_places = root["places"]
    if type(raw_places) is not list or not raw_places:
        raise CatalogValidationError(f"{origin}.places: expected a non-empty list")
    places = []
    for index, raw_place in enumerate(raw_places):
        location = f"{origin}.places[{index}]"
        item = _object(raw_place, PLACE_KEYS, location)
        aliases = item["aliases"]
        if type(aliases) is not list:
            raise CatalogValidationError(f"{location}.aliases: expected a list")
        places.append(
            (
                _string(item["name"], f"{location}.name"),
                tuple(_string(alias, f"{location}.aliases") for alias in aliases),
            )
        )
    try:
        directory = PlaceDirectory(version, tuple(Place(name, aliases) for name, aliases in places))
    except PlaceDirectoryError as exc:
        raise CatalogValidationError(f"{origin}: {exc}") from exc

    manifest_path = directory_path.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        raise CatalogValidationError(f"missing place directory manifest: {manifest_path}")
    manifest_origin = str(manifest_path)
    manifest = _object(
        _strict_json(_read_bytes(manifest_path), manifest_origin), MANIFEST_KEYS, manifest_origin
    )
    if manifest["version"] != version:
        raise CatalogValidationError(f"{manifest_origin}: version does not match the directory")
    if manifest["places_file"] != directory_path.name:
        raise CatalogValidationError(f"{manifest_origin}: places_file does not name the file")
    declared = manifest["places_sha256"]
    if type(declared) is not str or not _SHA256_PATTERN.fullmatch(declared):
        raise CatalogValidationError(f"{manifest_origin}: places_sha256 must be a SHA-256")
    if declared != sha256:
        raise CatalogValidationError(f"{manifest_origin}: places_sha256 does not match the file")
    if _integer(manifest["places"], f"{manifest_origin}.places") != len(directory.places):
        raise CatalogValidationError(f"{manifest_origin}: places count does not match")
    _string(manifest["purpose"], f"{manifest_origin}.purpose")
    limitations = manifest["limitations"]
    if type(limitations) is not list or not limitations:
        raise CatalogValidationError(f"{manifest_origin}.limitations: expected a non-empty list")
    for index, limitation in enumerate(limitations):
        _string(limitation, f"{manifest_origin}.limitations[{index}]")
    return directory


def check_catalog_places(catalog: OfferCatalog, directory: PlaceDirectory) -> None:
    """Every origin and destination of a package catalogue is a canonical place name."""
    for offer in catalog.offers:
        for spelling in (offer.origin, offer.destination):
            if spelling is None or directory.resolve(spelling) != spelling:
                raise CatalogValidationError(
                    f"offer {offer.offer_id}: {spelling!r} is not a canonical place name"
                )
