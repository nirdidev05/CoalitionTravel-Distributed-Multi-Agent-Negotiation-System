"""Closed directory of the places of catalogue v2, with their aliases (ID-11, plan §6.5).

This is not the general normalizer planned for later (P7): it only knows the places of
the catalogue. A spelling is compared after NFC, case folding and stripping (the
destination key), and resolves to the canonical name of exactly one place, or to
nothing. The v1 path never uses it.
"""

from dataclasses import dataclass

from coalition_travel.domain.destination import normalize_destination_key


class PlaceDirectoryError(ValueError):
    """The directory is inconsistent: a blank name or two places sharing a spelling."""


@dataclass(frozen=True)
class Place:
    name: str
    aliases: tuple[str, ...]

    def __post_init__(self):
        if type(self.name) is not str or not self.name or self.name != self.name.strip():
            raise PlaceDirectoryError("a place name must be a non-blank, stripped string")
        if type(self.aliases) is not tuple or any(type(a) is not str for a in self.aliases):
            raise PlaceDirectoryError("aliases must be a tuple of strings")

    @property
    def spellings(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass(frozen=True)
class PlaceDirectory:
    version: str
    places: tuple[Place, ...]

    def __post_init__(self):
        if type(self.version) is not str or not self.version.strip():
            raise PlaceDirectoryError("version must be a non-blank string")
        if type(self.places) is not tuple or not self.places:
            raise PlaceDirectoryError("a directory needs at least one place")
        if any(type(place) is not Place for place in self.places):
            raise PlaceDirectoryError("places must be Place instances")
        names = tuple(place.name for place in self.places)
        if names != tuple(sorted(names)):
            raise PlaceDirectoryError("places must be sorted by name")
        index: dict[str, str] = {}
        for place in self.places:
            for spelling in place.spellings:
                try:
                    key = normalize_destination_key(spelling)
                except ValueError as exc:
                    raise PlaceDirectoryError("a spelling must not be blank") from exc
                owner = index.setdefault(key, place.name)
                if owner != place.name:
                    raise PlaceDirectoryError(f"{place.name} and {owner} share a spelling")
        object.__setattr__(self, "_index", index)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(place.name for place in self.places)

    def resolve(self, spelling: str) -> str | None:
        """Canonical name of the place written ``spelling``, or None when unknown."""
        if type(spelling) is not str or not spelling.strip():
            return None
        return self._index.get(normalize_destination_key(spelling))
