"""Synthetic supplier offers: public catalogue types and private seller terms.

Confidentiality boundary. ``PriceTier``, ``OfferQuote`` and ``OfferCatalog`` are public:
they carry list prices only and contain no seller floor. ``SellerFloorTier``,
``SellerTerms`` and ``SellerTermsBook`` are private: they are passed exclusively to the
seller negotiation simulator (phase P3 onwards) and never to the compatibility component,
the public catalogue or any traveler-facing report. ``tests/test_offer_catalog.py``
enforces this boundary with an AST allow-list.

Every offer is fictional (``synthetic`` must be True): it never represents availability,
a schedule or a commercial commitment.
"""

from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise

from coalition_travel.domain.destination import normalize_destination_key
from coalition_travel.domain.money import MAX_CENTS, Cents, require_cents

MAX_CAPACITY_SEATS = 10_000
MAX_IDENTIFIER_LENGTH = 120
_HEX_DIGITS = frozenset("0123456789abcdef")


def _require_identifier(value, name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value or value != value.strip() or len(value) > MAX_IDENTIFIER_LENGTH:
        raise ValueError(
            f"{name} must be non-blank, stripped and at most {MAX_IDENTIFIER_LENGTH} characters"
        )


def _require_seat_count(value, name: str, maximum: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an int")
    if not 1 <= value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")


def _require_sha256(value) -> None:
    if type(value) is not str:
        raise TypeError("sha256 must be a string")
    if len(value) != 64 or not set(value) <= _HEX_DIGITS:
        raise ValueError("sha256 must be a lowercase hexadecimal SHA-256 digest")


def _validate_tier_sequence(min_seats: tuple[int, ...], prices: tuple[Cents, ...], kind: str):
    if not min_seats:
        raise ValueError(f"{kind} tiers must not be empty")
    if min_seats[0] != 1:
        raise ValueError(f"the first {kind} tier must start at one seat")
    if any(later <= earlier for earlier, later in pairwise(min_seats)):
        raise ValueError(f"{kind} tier min_seats must be strictly increasing")
    if any(later > earlier for earlier, later in pairwise(prices)):
        raise ValueError(f"{kind} per-seat prices must not increase with group size")


def _tier_index(min_seats: tuple[int, ...], seats: int) -> int:
    """Index of the tier with the largest min_seats <= seats."""
    index = 0
    for position, threshold in enumerate(min_seats):
        if threshold <= seats:
            index = position
    return index


# --- public catalogue ----------------------------------------------------------------


@dataclass(frozen=True)
class PriceTier:
    min_seats: int
    list_per_seat: Cents

    def __post_init__(self):
        _require_seat_count(self.min_seats, "min_seats", MAX_CAPACITY_SEATS)
        require_cents(self.list_per_seat, minimum=1, name="list_per_seat")


@dataclass(frozen=True)
class OfferQuote:
    offer_id: str
    catalog_version: str
    supplier_id: str
    destination: str
    departure_date: date
    arrival_date: date
    direct: bool
    capacity_seats: int
    tiers: tuple[PriceTier, ...]
    synthetic: bool = True

    def __post_init__(self):
        for name in ("offer_id", "catalog_version", "supplier_id", "destination"):
            _require_identifier(getattr(self, name), name)
        normalize_destination_key(self.destination)
        for name in ("departure_date", "arrival_date"):
            value = getattr(self, name)
            if type(value) is not date or isinstance(value, datetime):
                raise TypeError(f"{name} must be a datetime.date")
        if self.departure_date > self.arrival_date:
            raise ValueError("departure_date must not be after arrival_date")
        if type(self.direct) is not bool:
            raise TypeError("direct must be a bool")
        _require_seat_count(self.capacity_seats, "capacity_seats", MAX_CAPACITY_SEATS)
        if self.synthetic is not True:
            raise ValueError("catalogue offers must be explicitly synthetic")
        if type(self.tiers) is not tuple or any(type(t) is not PriceTier for t in self.tiers):
            raise TypeError("tiers must be a tuple of PriceTier")
        min_seats = tuple(tier.min_seats for tier in self.tiers)
        _validate_tier_sequence(
            min_seats, tuple(tier.list_per_seat for tier in self.tiers), "price"
        )
        if min_seats[-1] > self.capacity_seats:
            raise ValueError("a price tier starts above the offer capacity")
        # Per-seat prices never increase, so this bounds every total within capacity.
        if self.capacity_seats * self.tiers[0].list_per_seat > MAX_CENTS:
            raise ValueError("offer totals exceed the supported monetary domain")

    @property
    def destination_key(self) -> str:
        return normalize_destination_key(self.destination)

    def tier_for(self, seats: int) -> PriceTier:
        _require_seat_count(seats, "seats", self.capacity_seats)
        return self.tiers[_tier_index(tuple(t.min_seats for t in self.tiers), seats)]

    def list_total(self, seats: int) -> Cents:
        return require_cents(seats * self.tier_for(seats).list_per_seat, name="list_total")


@dataclass(frozen=True)
class OfferCatalog:
    version: str
    sha256: str
    offers: tuple[OfferQuote, ...]

    def __post_init__(self):
        _require_identifier(self.version, "version")
        _require_sha256(self.sha256)
        if type(self.offers) is not tuple or any(type(o) is not OfferQuote for o in self.offers):
            raise TypeError("offers must be a tuple of OfferQuote")
        if not self.offers:
            raise ValueError("a catalogue needs at least one offer")
        identifiers = tuple(offer.offer_id for offer in self.offers)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("offer_id values must be unique")
        if identifiers != tuple(sorted(identifiers)):
            raise ValueError("offers must be sorted by offer_id")
        if any(offer.catalog_version != self.version for offer in self.offers):
            raise ValueError("every offer must belong to the catalogue version")

    def get(self, offer_id: str) -> OfferQuote:
        for offer in self.offers:
            if offer.offer_id == offer_id:
                return offer
        raise KeyError(f"unknown offer {offer_id!r}")

    def offers_for_destination(self, destination: str) -> tuple[OfferQuote, ...]:
        key = normalize_destination_key(destination)
        return tuple(offer for offer in self.offers if offer.destination_key == key)


# --- private seller terms (seller negotiation simulator only) ------------------------


@dataclass(frozen=True)
class SellerFloorTier:
    min_seats: int
    floor_per_seat: Cents

    def __post_init__(self):
        _require_seat_count(self.min_seats, "min_seats", MAX_CAPACITY_SEATS)
        require_cents(self.floor_per_seat, minimum=1, name="floor_per_seat")


@dataclass(frozen=True)
class SellerTerms:
    offer_id: str
    catalog_version: str
    capacity_seats: int
    floor_tiers: tuple[SellerFloorTier, ...]

    def __post_init__(self):
        _require_identifier(self.offer_id, "offer_id")
        _require_identifier(self.catalog_version, "catalog_version")
        _require_seat_count(self.capacity_seats, "capacity_seats", MAX_CAPACITY_SEATS)
        if type(self.floor_tiers) is not tuple or any(
            type(tier) is not SellerFloorTier for tier in self.floor_tiers
        ):
            raise TypeError("floor_tiers must be a tuple of SellerFloorTier")
        min_seats = tuple(tier.min_seats for tier in self.floor_tiers)
        _validate_tier_sequence(
            min_seats, tuple(tier.floor_per_seat for tier in self.floor_tiers), "floor"
        )
        if min_seats[-1] > self.capacity_seats:
            raise ValueError("a floor tier starts above the offer capacity")

    def floor_tier_for(self, seats: int) -> SellerFloorTier:
        _require_seat_count(seats, "seats", self.capacity_seats)
        return self.floor_tiers[_tier_index(tuple(t.min_seats for t in self.floor_tiers), seats)]

    def floor_total(self, seats: int) -> Cents:
        return require_cents(seats * self.floor_tier_for(seats).floor_per_seat, name="floor_total")


@dataclass(frozen=True)
class SellerTermsBook:
    version: str
    sha256: str
    terms: tuple[SellerTerms, ...]

    def __post_init__(self):
        _require_identifier(self.version, "version")
        _require_sha256(self.sha256)
        if type(self.terms) is not tuple or any(type(t) is not SellerTerms for t in self.terms):
            raise TypeError("terms must be a tuple of SellerTerms")
        if not self.terms:
            raise ValueError("a seller terms book needs at least one entry")
        identifiers = tuple(entry.offer_id for entry in self.terms)
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("offer_id values must be unique")
        if identifiers != tuple(sorted(identifiers)):
            raise ValueError("seller terms must be sorted by offer_id")
        if any(entry.catalog_version != self.version for entry in self.terms):
            raise ValueError("every seller term must belong to the catalogue version")

    def get(self, offer_id: str) -> SellerTerms:
        for entry in self.terms:
            if entry.offer_id == offer_id:
                return entry
        raise KeyError(f"unknown offer {offer_id!r}")


def validate_seller_terms_against_catalog(catalog: OfferCatalog, book: SellerTermsBook) -> None:
    """Cross-check the private book against the public catalogue it was loaded with.

    The check lives here, not in either ``__post_init__``, so that the public types never
    hold a reference to the private ones.
    """
    if type(catalog) is not OfferCatalog or type(book) is not SellerTermsBook:
        raise TypeError("expected an OfferCatalog and a SellerTermsBook")
    if (catalog.version, catalog.sha256) != (book.version, book.sha256):
        raise ValueError("catalogue and seller terms come from different files or versions")
    if tuple(o.offer_id for o in catalog.offers) != tuple(t.offer_id for t in book.terms):
        raise ValueError("catalogue and seller terms must describe the same offers")
    for offer, terms in zip(catalog.offers, book.terms):
        if offer.capacity_seats != terms.capacity_seats:
            raise ValueError(f"{offer.offer_id}: capacity differs between catalogue and terms")
        if tuple(t.min_seats for t in offer.tiers) != tuple(t.min_seats for t in terms.floor_tiers):
            raise ValueError(f"{offer.offer_id}: price and floor tiers must share min_seats")
        for price, floor in zip(offer.tiers, terms.floor_tiers):
            if floor.floor_per_seat > price.list_per_seat:
                raise ValueError(
                    f"{offer.offer_id}: floor exceeds list price at {price.min_seats} seats"
                )
