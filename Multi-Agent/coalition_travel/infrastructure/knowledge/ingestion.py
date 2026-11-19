"""Offline batch ingestion for supported document files."""

from pathlib import Path

from coalition_travel.application.knowledge import KnowledgeService
from coalition_travel.infrastructure.knowledge.source_loader import (
    SUPPORTED_SUFFIXES,
    load_document,
)


class KnowledgeIngestionPipeline:
    def __init__(self, service: KnowledgeService):
        self.service = service

    def index_path(self, path: str | Path, metadata: dict | None = None) -> dict[str, int]:
        source = Path(path)
        files = (
            sorted(item for item in source.rglob("*") if item.suffix.lower() in SUPPORTED_SUFFIXES)
            if source.is_dir()
            else [source]
        )
        indexed = {}
        for file_path in files:
            document = load_document(file_path, metadata)
            indexed[document.document_id] = self.service.index_document(document)
        return indexed
