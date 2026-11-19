"""Offline text and Markdown document loading with explicit metadata."""

from pathlib import Path

from coalition_travel.application.knowledge import KnowledgeDocument

SUPPORTED_SUFFIXES = {".txt", ".md"}


def load_document(path: str | Path, metadata: dict | None = None) -> KnowledgeDocument:
    source = Path(path)
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"unsupported knowledge document type: {source.suffix}")
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"could not read knowledge document: {source}") from exc
    if not text.strip():
        raise ValueError("knowledge document is empty")
    return KnowledgeDocument(
        document_id=source.as_posix(),
        text=text,
        metadata=dict(metadata or {}),
        source=str(source),
    )
