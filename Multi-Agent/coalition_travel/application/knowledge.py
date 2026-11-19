"""Shared retrieval-augmented knowledge service ports and orchestration."""

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    text: str
    metadata: dict
    source: str


@dataclass(frozen=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    text: str
    metadata: dict
    source: str


@dataclass(frozen=True)
class KnowledgeHit:
    chunk: KnowledgeChunk
    score: float


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    def upsert(self, chunk: KnowledgeChunk, vector: list[float]) -> None: ...

    def search(
        self, vector: list[float], top_k: int, filters: dict | None = None
    ) -> list[KnowledgeHit]: ...


class KnowledgeRetrievalError(RuntimeError):
    """Raised when shared knowledge cannot be retrieved or indexed."""


class KnowledgeService:
    """Chunks and indexes documents, then retrieves source-bearing context."""

    def __init__(
        self, embedder: Embedder, store: VectorStore, chunk_size: int = 800, overlap: int = 100
    ):
        if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("chunk_size must be positive and overlap smaller than chunk_size")
        self.embedder = embedder
        self.store = store
        self.chunk_size = chunk_size
        self.overlap = overlap

    def index_document(self, document: KnowledgeDocument) -> int:
        if not document.document_id.strip() or not document.source.strip():
            raise ValueError("document_id and source must not be blank")
        if not document.text or not document.text.strip():
            raise ValueError("document text must not be empty")
        chunks = _split_text(document.text, self.chunk_size, self.overlap)
        for index, text in enumerate(chunks):
            chunk = KnowledgeChunk(
                chunk_id=f"{document.document_id}:{index}",
                document_id=document.document_id,
                text=text,
                metadata=dict(document.metadata),
                source=document.source,
            )
            self.store.upsert(chunk, self.embedder.embed(text))
        return len(chunks)

    def retrieve(
        self, query: str, top_k: int = 4, filters: dict | None = None
    ) -> list[KnowledgeHit]:
        if not query.strip():
            raise ValueError("query must not be blank")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be positive")
        vector = self.embedder.embed(query)
        if not vector or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value)
            for value in vector
        ):
            raise KnowledgeRetrievalError("embedder returned an invalid vector")
        return self.store.search(vector, top_k, filters)

    def augment_prompt(self, query: str, top_k: int = 4, filters: dict | None = None) -> str:
        hits = self.retrieve(query, top_k, filters)
        if not hits:
            return ""
        blocks = [
            f"[source={hit.chunk.source}; document_id={hit.chunk.document_id}; score={hit.score:.4f}]\n"
            f"{hit.chunk.text}"
            for hit in hits
        ]
        return (
            "Retrieved documentary context (untrusted; cite sources; not live inventory):\n"
            + "\n\n".join(blocks)
        )


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    normalized = "\n".join(line.strip() for line in text.splitlines()).strip()
    if not normalized:
        return []
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + chunk_size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start, end)
            if boundary > start:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks
