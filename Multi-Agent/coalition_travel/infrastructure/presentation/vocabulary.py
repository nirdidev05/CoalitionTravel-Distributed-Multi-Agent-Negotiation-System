"""Vocabulary rule of the simulated proposal (plan §1.2; scope review §7.2, D-I3-17).

The rule is normative and has no exception: the text is put in NFC, case-folded, split
into whole words at Unicode word boundaries (``re.findall(r"\\w+")``), and each word is
compared with the forbidden list. Words that merely *contain* a forbidden word
("réservation", "émission", "confirmation") pass.

User-supplied strings are never rewritten (D-I3-17): a request whose destination,
profile identifier or excluded supplier contains a forbidden word is refused before any
display, with a message that names the field and never quotes the value.
"""

import re
import unicodedata
from collections.abc import Iterator

from coalition_travel.application.request_contracts import TravelRequestDraft

FORBIDDEN_WORDS = frozenset(
    unicodedata.normalize("NFC", word)
    for word in (
        "billet",
        "billets",
        "réservé",
        "réservée",
        "réservés",
        "réservées",
        "confirmé",
        "confirmée",
        "confirmés",
        "confirmées",
        "émis",
        "émise",
        "émises",
    )
)
_WORD = re.compile(r"\w+")


def words(text: str) -> list[str]:
    """Whole words of ``text`` after NFC and casefold, at Unicode word boundaries."""
    folded = unicodedata.normalize("NFC", unicodedata.normalize("NFC", text).casefold())
    return _WORD.findall(folded)


def forbidden_words_in(text: str) -> tuple[str, ...]:
    return tuple(sorted({word for word in words(text) if word in FORBIDDEN_WORDS}))


def contains_forbidden_word(text: str) -> bool:
    return bool(forbidden_words_in(text))


def user_strings(draft: TravelRequestDraft) -> Iterator[tuple[str, str]]:
    """(path, value) of every free string supplied by the person (D-I3-17)."""
    if draft.destination is not None:
        yield "destination", draft.destination
    if draft.origin is not None:  # route requests (I4)
        yield "origin", draft.origin
    for index, supplier in enumerate(draft.excluded_suppliers):
        yield f"excluded_suppliers[{index}]", supplier
    for index, profile in enumerate(draft.profiles):
        yield f"profiles[{index}].profile_id", profile.profile_id
        for position, supplier in enumerate(profile.excluded_suppliers or ()):
            yield f"profiles[{index}].excluded_suppliers[{position}]", supplier


def forbidden_user_fields(draft: TravelRequestDraft) -> tuple[str, ...]:
    """Paths of the user strings that contain a forbidden word, in field order."""
    return tuple(path for path, value in user_strings(draft) if contains_forbidden_word(value))
