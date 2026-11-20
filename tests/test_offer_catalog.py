"""P1.4 — synthetic offer catalogue, strict loading and the seller-floor boundary."""

import ast
import copy
import dataclasses
import hashlib
import json
from datetime import date
from pathlib import Path

import pytest
from coalition_travel.domain.offer import (
    OfferCatalog,
    OfferQuote,
    PriceTier,
    SellerFloorTier,
    SellerTerms,
    SellerTermsBook,
    validate_seller_terms_against_catalog,
)
from coalition_travel.infrastructure.catalog.json_catalog import (
    CatalogValidationError,
    load_offer_catalog,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = REPOSITORY_ROOT / "data/catalog/catalog_v1.json"
CATALOG_SHA256 = "4b145ecbdbd662d49015ef199bcd60b03b63b2e131e2cdcb3c14d8b182dc3071"
SOURCE_ROOT = REPOSITORY_ROOT / "Multi-Agent"
FLOOR_ALLOW_LIST = (
    Path("coalition_travel/domain/offer.py"),
    Path("coalition_travel/infrastructure/catalog/json_catalog.py"),
    Path("coalition_travel/infrastructure/negotiation/simulated_oracle.py"),
    # P4 decision D8: the experimental scenario generator builds private terms and the
    # oracle itself, and returns public objects only.
    Path("coalition_travel/infrastructure/evaluation/formation_scenarios.py"),
    # 3H, I1: composition root of the simulated market; it hands the terms book to the
    # seller simulator only and returns the public catalogue and journaling sessions.
    Path("coalition_travel/infrastructure/negotiation/market.py"),
)
GUARDED_NAMES = frozenset(
    {
        "SellerTerms",
        "SellerTermsBook",
        "SellerFloorTier",
        "load_offer_catalog",
        "validate_seller_terms_against_catalog",
        "floor_total",
        "floor_tier_for",
        "floor_tiers",
        "floor_per_seat",
    }
)


# --- the versioned fixture ------------------------------------------------------------


def test_fixture_loads_with_version_hash_and_sorted_offers():
    catalog, book = load_offer_catalog(CATALOG_PATH)
    assert catalog.version == book.version == "catalog-v1"
    assert catalog.sha256 == book.sha256 == CATALOG_SHA256
    assert hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest() == CATALOG_SHA256
    assert [offer.offer_id for offer in catalog.offers] == [
        "rom-cloudwing-20270405",
        "tyo-northstar-20270310",
        "tyo-skyways-20270312",
    ]
    assert [entry.offer_id for entry in book.terms] == [o.offer_id for o in catalog.offers]
    assert all(offer.synthetic is True for offer in catalog.offers)


def test_two_loads_are_equal_and_hashable():
    first = load_offer_catalog(CATALOG_PATH)
    second = load_offer_catalog(CATALOG_PATH)
    assert first == second
    assert hash(first[0]) == hash(second[0])
    assert hash(first[1]) == hash(second[1])


def test_offer_fields_match_the_validated_values():
    catalog, book = load_offer_catalog(CATALOG_PATH)
    northstar = catalog.get("tyo-northstar-20270310")
    assert northstar.supplier_id == "Northstar"
    assert northstar.destination_key == "tokyo"
    assert (northstar.departure_date, northstar.arrival_date) == (
        date(2027, 3, 10),
        date(2027, 3, 11),
    )
    assert northstar.direct is True
    assert northstar.capacity_seats == 60
    assert northstar.tiers == (PriceTier(1, 56_000), PriceTier(3, 52_000), PriceTier(6, 48_000))
    assert book.get("tyo-northstar-20270310").floor_tiers == (
        SellerFloorTier(1, 40_000),
        SellerFloorTier(3, 37_000),
        SellerFloorTier(6, 34_000),
    )
    assert catalog.get("tyo-skyways-20270312").direct is False
    with pytest.raises(KeyError):
        catalog.get("unknown")
    with pytest.raises(KeyError):
        book.get("unknown")


@pytest.mark.parametrize(
    "seats,min_seats",
    [(1, 1), (2, 1), (3, 3), (4, 3), (5, 3), (6, 6), (59, 6), (60, 6)],
)
def test_tier_lookup_uses_the_largest_threshold_not_above_the_seat_count(seats, min_seats):
    catalog, book = load_offer_catalog(CATALOG_PATH)
    offer = catalog.get("tyo-northstar-20270310")
    assert offer.tier_for(seats).min_seats == min_seats
    assert book.get(offer.offer_id).floor_tier_for(seats).min_seats == min_seats


def test_totals_use_the_tier_of_the_group_size():
    catalog, book = load_offer_catalog(CATALOG_PATH)
    assert catalog.get("tyo-northstar-20270310").list_total(4) == 4 * 52_000
    assert book.get("tyo-northstar-20270310").floor_total(4) == 4 * 37_000
    assert catalog.get("rom-cloudwing-20270405").list_total(1) == 30_000


@pytest.mark.parametrize("seats,error", [(0, ValueError), (61, ValueError), (2.0, TypeError)])
def test_tier_lookup_rejects_seat_counts_outside_the_capacity(seats, error):
    catalog, book = load_offer_catalog(CATALOG_PATH)
    with pytest.raises(error):
        catalog.get("tyo-northstar-20270310").tier_for(seats)
    with pytest.raises(error):
        book.get("tyo-northstar-20270310").floor_total(seats)


def test_offers_are_found_by_normalized_destination():
    catalog, _ = load_offer_catalog(CATALOG_PATH)
    tokyo = catalog.offers_for_destination("  TOKYO ")
    assert [offer.supplier_id for offer in tokyo] == ["Northstar", "SkyWays"]
    assert catalog.offers_for_destination("Lisbon") == ()


# --- invalid catalogues ---------------------------------------------------------------


def _base_document() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _write(tmp_path, *, document=None, text=None, manifest_changes=None, offers=None):
    """Write a catalogue and a manifest consistent with it unless manifest_changes say so."""
    catalog_path = tmp_path / "catalog_test.json"
    if text is None:
        text = json.dumps(document, indent=2)
    catalog_path.write_bytes(text.encode("utf-8"))
    manifest = {
        "version": (document or {}).get("catalog_version", "catalog-v1"),
        "catalog_file": catalog_path.name,
        "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
        "synthetic": True,
        "currency": "EUR",
        "offers": offers if offers is not None else len((document or {}).get("offers", [])),
        "purpose": "test",
        "limitations": ["fictional test fixture"],
    }
    manifest.update(manifest_changes or {})
    catalog_path.with_suffix(".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return catalog_path


def _mutated(mutation):
    document = _base_document()
    mutation(document)
    return document


def _offer(document, offer_id="tyo-northstar-20270310"):
    return next(offer for offer in document["offers"] if offer["offer_id"] == offer_id)


INVALID_DOCUMENTS = {
    "floor_above_list": lambda d: _offer(d)["tiers"][1].update(seller_floor_per_seat_cents=60_000),
    "list_increases": lambda d: _offer(d)["tiers"][2].update(list_per_seat_cents=99_000),
    "floor_increases": lambda d: _offer(d)["tiers"][2].update(seller_floor_per_seat_cents=39_000),
    "first_tier_not_one": lambda d: _offer(d)["tiers"][0].update(min_seats=2),
    "min_seats_not_increasing": lambda d: _offer(d)["tiers"][2].update(min_seats=3),
    "tier_above_capacity": lambda d: _offer(d).update(capacity_seats=5),
    "capacity_zero": lambda d: _offer(d).update(capacity_seats=0),
    "capacity_bool": lambda d: _offer(d).update(capacity_seats=True),
    "departure_after_arrival": lambda d: _offer(d).update(departure_date="2027-03-12"),
    "malformed_date": lambda d: _offer(d).update(departure_date="2027-3-10"),
    "impossible_date": lambda d: _offer(d).update(arrival_date="2027-02-30"),
    "direct_not_bool": lambda d: _offer(d).update(direct=1),
    "not_synthetic": lambda d: d.update(synthetic=False),
    "other_currency": lambda d: d.update(currency="USD"),
    "unknown_offer_field": lambda d: _offer(d).update(availability=12),
    "missing_tier_field": lambda d: _offer(d)["tiers"][0].pop("seller_floor_per_seat_cents"),
    "duplicate_offer_id": lambda d: d["offers"].append(copy.deepcopy(_offer(d))),
    "blank_supplier": lambda d: _offer(d).update(supplier_id="  "),
    "amount_as_string": lambda d: _offer(d)["tiers"][0].update(list_per_seat_cents="56000"),
    "empty_offers": lambda d: d.update(offers=[]),
}


@pytest.mark.parametrize("name", sorted(INVALID_DOCUMENTS))
def test_invalid_catalogue_content_is_rejected(tmp_path, name):
    path = _write(tmp_path, document=_mutated(INVALID_DOCUMENTS[name]))
    with pytest.raises(CatalogValidationError):
        load_offer_catalog(path)


@pytest.mark.parametrize(
    "replacement",
    [
        ('"list_per_seat_cents": 56000', '"list_per_seat_cents": 56000.0'),
        ('"list_per_seat_cents": 56000', '"list_per_seat_cents": NaN'),
        ('"list_per_seat_cents": 56000', '"list_per_seat_cents": Infinity'),
        ('"direct": true', '"direct": true, "direct": false'),
    ],
)
def test_decimal_numbers_constants_and_duplicate_keys_are_rejected(tmp_path, replacement):
    text = json.dumps(_base_document(), indent=2)
    assert replacement[0] in text
    path = _write(tmp_path, text=text.replace(replacement[0], replacement[1], 1), offers=3)
    with pytest.raises(CatalogValidationError):
        load_offer_catalog(path)


def test_invalid_utf8_is_rejected(tmp_path):
    path = _write(tmp_path, document=_base_document())
    path.write_bytes(path.read_bytes().replace(b"Rome", b"R\xffme"))
    with pytest.raises(CatalogValidationError):
        load_offer_catalog(path)


# --- manifest consistency -------------------------------------------------------------


def test_missing_manifest_is_an_error(tmp_path):
    path = _write(tmp_path, document=_base_document())
    path.with_suffix(".manifest.json").unlink()
    with pytest.raises(CatalogValidationError, match="missing catalogue manifest"):
        load_offer_catalog(path)


def test_any_byte_change_without_manifest_update_is_rejected(tmp_path):
    path = _write(tmp_path, document=_base_document())
    load_offer_catalog(path)  # consistent pair loads
    path.write_bytes(path.read_bytes().replace(b"CloudWing", b"CloudWinG", 1))
    with pytest.raises(CatalogValidationError, match="does not match the file"):
        load_offer_catalog(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "catalog-v2"},
        {"catalog_file": "other.json"},
        {"offers": 4},
        {"synthetic": False},
        {"currency": "USD"},
        {"catalog_sha256": "ABC"},
        {"limitations": []},
        {"limitations": [""]},
        {"purpose": " "},
        {"extra_key": 1},
    ],
)
def test_inconsistent_manifest_is_rejected(tmp_path, changes):
    path = _write(tmp_path, document=_base_document(), manifest_changes=changes)
    with pytest.raises(CatalogValidationError):
        load_offer_catalog(path)


# --- direct domain construction --------------------------------------------------------


def _quote(**changes):
    fields = {
        "offer_id": "o1",
        "catalog_version": "v1",
        "supplier_id": "Northstar",
        "destination": "Tokyo",
        "departure_date": date(2027, 3, 10),
        "arrival_date": date(2027, 3, 11),
        "direct": True,
        "capacity_seats": 10,
        "tiers": (PriceTier(1, 50_000), PriceTier(3, 45_000)),
    }
    fields.update(changes)
    return OfferQuote(**fields)


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"tiers": [PriceTier(1, 50_000)]}, TypeError),
        ({"tiers": ()}, ValueError),
        ({"synthetic": False}, ValueError),
        ({"direct": 1}, TypeError),
        ({"capacity_seats": 20_000}, ValueError),
        ({"offer_id": " o1"}, ValueError),
        ({"tiers": (PriceTier(1, 100_000_000),), "capacity_seats": 10_000}, ValueError),
    ],
)
def test_offer_quote_rejects_invalid_direct_construction(changes, error):
    with pytest.raises(error):
        _quote(**changes)


@pytest.mark.parametrize(
    "tier_args,error",
    [((0, 100), ValueError), ((1, 0), ValueError), ((True, 100), TypeError), ((1, 1.5), TypeError)],
)
def test_tiers_reject_invalid_values(tier_args, error):
    with pytest.raises(error):
        PriceTier(*tier_args)
    with pytest.raises(error):
        SellerFloorTier(*tier_args)


def _terms(**changes):
    fields = {
        "offer_id": "o1",
        "catalog_version": "v1",
        "capacity_seats": 10,
        "floor_tiers": (SellerFloorTier(1, 40_000), SellerFloorTier(3, 38_000)),
    }
    fields.update(changes)
    return SellerTerms(**fields)


def test_cross_validation_detects_every_mismatch():
    sha = "1" * 64
    catalog = OfferCatalog("v1", sha, (_quote(),))
    validate_seller_terms_against_catalog(catalog, SellerTermsBook("v1", sha, (_terms(),)))
    mismatches = [
        SellerTermsBook("v1", "2" * 64, (_terms(),)),
        SellerTermsBook("v1", sha, (_terms(offer_id="o2"),)),
        SellerTermsBook("v1", sha, (_terms(capacity_seats=9),)),
        SellerTermsBook(
            "v1", sha, (_terms(floor_tiers=(SellerFloorTier(1, 40_000), SellerFloorTier(4, 1))),)
        ),
        SellerTermsBook(
            "v1",
            sha,
            (_terms(floor_tiers=(SellerFloorTier(1, 60_000), SellerFloorTier(3, 38_000))),),
        ),
    ]
    for book in mismatches:
        with pytest.raises(ValueError):
            validate_seller_terms_against_catalog(catalog, book)
    with pytest.raises(TypeError):
        validate_seller_terms_against_catalog(catalog, catalog)


def test_registries_are_deeply_immutable():
    catalog, book = load_offer_catalog(CATALOG_PATH)
    with pytest.raises(dataclasses.FrozenInstanceError):
        catalog.offers[0].direct = False
    with pytest.raises(dataclasses.FrozenInstanceError):
        book.terms[0].floor_tiers[0].floor_per_seat = 1
    assert type(catalog.offers) is tuple and type(catalog.offers[0].tiers) is tuple
    assert type(book.terms) is tuple and type(book.terms[0].floor_tiers) is tuple


# --- confidentiality boundary of seller floors ------------------------------------------


def test_public_types_hold_no_floor_field():
    for public_type in (PriceTier, OfferQuote, OfferCatalog):
        names = [field.name for field in dataclasses.fields(public_type)]
        assert not [name for name in names if "floor" in name], public_type.__name__


def test_public_catalogue_does_not_reach_any_private_object():
    catalog, _ = load_offer_catalog(CATALOG_PATH)
    private_types = (SellerTerms, SellerTermsBook, SellerFloorTier)
    pending = [catalog]
    while pending:
        current = pending.pop()
        assert not isinstance(current, private_types)
        if dataclasses.is_dataclass(current):
            pending.extend(getattr(current, field.name) for field in dataclasses.fields(current))
        elif isinstance(current, tuple):
            pending.extend(current)


def _referenced_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.update(node.name.split("."))
            if node.asname:
                names.add(node.asname)
    return names


@pytest.mark.parametrize(
    "source",
    [
        "from coalition_travel.domain.offer import SellerTermsBook",
        "import coalition_travel.domain.offer as offer\nterms = offer.SellerTerms",
        "from coalition_travel.infrastructure.catalog.json_catalog import load_offer_catalog as l",
        "price = terms.floor_total(3)",
        "value = tier.floor_per_seat",
    ],
)
def test_floor_guard_detects_imports_attributes_and_aliases(source):
    """Sensitivity check of the detector used by the allow-list test below."""
    assert _referenced_names(ast.parse(source)) & GUARDED_NAMES


def test_floor_guard_ignores_unrelated_names():
    source = "from decimal import ROUND_FLOOR\nimport math\nvalue = math.floor(2.5)"
    assert not _referenced_names(ast.parse(source)) & GUARDED_NAMES


def test_floor_allow_list_contains_exactly_the_reviewed_modules():
    """Any future addition must change this test explicitly (decision D8)."""
    assert FLOOR_ALLOW_LIST == (
        Path("coalition_travel/domain/offer.py"),
        Path("coalition_travel/infrastructure/catalog/json_catalog.py"),
        Path("coalition_travel/infrastructure/negotiation/simulated_oracle.py"),
        Path("coalition_travel/infrastructure/evaluation/formation_scenarios.py"),
        Path("coalition_travel/infrastructure/negotiation/market.py"),
    )


def test_only_allow_listed_modules_touch_private_seller_floors():
    """SellerTermsBook goes to the seller simulator only, never to compatibility or reports.

    Adding the P3 simulator module to FLOOR_ALLOW_LIST must be an explicit, reviewed change.
    """
    for allowed in FLOOR_ALLOW_LIST:
        assert (SOURCE_ROOT / allowed).is_file(), f"allow-listed module missing: {allowed}"
    violations = []
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        relative = path.relative_to(SOURCE_ROOT)
        if "__pycache__" in relative.parts or any(p.endswith(".egg-info") for p in relative.parts):
            continue
        if relative in FLOOR_ALLOW_LIST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        leaked = sorted(_referenced_names(tree) & GUARDED_NAMES)
        if leaked:
            violations.append(f"{relative}: {', '.join(leaked)}")
    assert not violations, "private seller floor names used outside the allow-list:\n" + "\n".join(
        violations
    )
