"""Deterministic destination keys shared by travel units and offers.

Until the P7 normalizer exists, a destination key is the NFC-normalized, stripped and
case-folded spelling. No linguistic alias is applied: "Lisbonne" and "Lisbon" remain two
different keys.
"""

import unicodedata


def normalize_destination_key(value: str) -> str:
    """Return the canonical comparison key of a destination spelling.

    A final NFC pass makes the function idempotent: case folding can decompose a few
    characters, and the key must equal its own normalization.
    """
    if not isinstance(value, str):
        raise TypeError("destination must be a string")
    key = unicodedata.normalize("NFC", unicodedata.normalize("NFC", value).strip().casefold())
    if not key:
        raise ValueError("destination must not be blank")
    return key
