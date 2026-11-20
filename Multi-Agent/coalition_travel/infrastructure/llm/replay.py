"""Replay extractor: recorded drafts instead of a language model (D-I3-10, step I3-C).

A tool for tests and offline demonstrations, never used by default. The file holds a
JSON list of ``TravelRequestDraft`` objects; the n-th extraction returns the n-th draft,
validated by ``model_validate``. Beyond the list, the extractor raises
``ExtractorContractError`` (exit code 1).

The provenance is ``provider = "replay"`` and ``model = "replay-v1"``: a constant that
never depends on the file content (revision 3). The file is read once, at construction,
so an unreadable file is reported while the options are read (exit code 64). No message
quotes the path or the content of the file.
"""

import json
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.request_understanding import ExtractorContractError
from coalition_travel.application.trip_proposal import REPLAY_FORMAT_VERSION, REPLAY_PROVIDER


class ReplayStructuredRequestExtractor:
    provider_name = REPLAY_PROVIDER
    model = REPLAY_FORMAT_VERSION

    def __init__(self, path: str | Path):
        raw = Path(path).read_bytes()  # OSError propagates: the caller reports it (code 64)
        try:
            entries = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ExtractorContractError("the replay file is not a JSON document") from None
        if not isinstance(entries, list):
            raise ExtractorContractError("the replay file must hold a JSON list of drafts")
        self._entries = tuple(entries)
        self.calls = 0

    @property
    def size(self) -> int:
        return len(self._entries)

    async def extract(self, text: str, reference_date: date) -> TravelRequestDraft:
        if self.calls >= len(self._entries):
            raise ExtractorContractError(
                f"the replay file is exhausted after {len(self._entries)} draft(s)"
            )
        index = self.calls
        self.calls += 1
        try:
            return TravelRequestDraft.model_validate(self._entries[index])
        except ValidationError:
            raise ExtractorContractError(
                f"replay entry {index} is not a valid TravelRequestDraft"
            ) from None
