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


@dataclass(frozen=True)
class EmbeddingIdentity:
    """Public identity of an embedding space; dimension is learned from its vectors."""

    provider: str
    model: str
    configuration_signature: str = "default"

    def __post_init__(self):
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.provider, self.model, self.configuration_signature)
        ):
            raise ValueError("embedding identity fields must not be blank")


@dataclass(frozen=True)
class EmbeddingSpace:
    identity: EmbeddingIdentity
    dimension: int


class Embedder(Protocol):
    @property
    def identity(self) -> EmbeddingIdentity: ...

    def embed(self, text: str) -> list[float]: ...


class VectorStore(Protocol):
    def replace_document(
        self,
        document_id: str,
        chunks: list[tuple[KnowledgeChunk, list[float]]],
        identity: EmbeddingIdentity,
    ) -> None: ...

    def search(
        self,
        vector: list[float],
        top_k: int,
        identity: EmbeddingIdentity,
        filters: dict | None = None,
        min_score: float = 0.0,
    ) -> list[KnowledgeHit]: ...


class KnowledgeRetrievalError(RuntimeError):
    """Raised when shared knowledge cannot be retrieved or indexed."""


class KnowledgeService:
    """Chunks and indexes documents, then retrieves source-bearing context."""

    def __init__(
        self,
        embedder: Embedder,
        store: VectorStore,
        chunk_size: int = 800,
        overlap: int = 100,
        min_relevance_score: float = 0.0,
    ):
        if chunk_size < 1 or overlap < 0 or overlap >= chunk_size:
            raise ValueError("chunk_size must be positive and overlap smaller than chunk_size")
        _validate_min_score(min_relevance_score)
        if not isinstance(embedder.identity, EmbeddingIdentity):
            raise TypeError("embedder.identity must be an EmbeddingIdentity")
        self.embedder = embedder
        self.store = store
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.min_relevance_score = min_relevance_score

    def index_document(self, document: KnowledgeDocument) -> int:
        if not document.document_id.strip() or not document.source.strip():
            raise ValueError("document_id and source must not be blank")
        if not document.text or not document.text.strip():
            raise ValueError("document text must not be empty")
        chunks = _split_text(document.text, self.chunk_size, self.overlap)
        embedded_chunks = []
        for index, text in enumerate(chunks):
            chunk = KnowledgeChunk(
                chunk_id=f"{document.document_id}:{index}",
                document_id=document.document_id,
                text=text,
                metadata=dict(document.metadata),
                source=document.source,
            )
            vector = _validate_vector(self.embedder.embed(text))
            embedded_chunks.append((chunk, vector))
        if not embedded_chunks:
            raise ValueError("document produced no indexable chunks")
        self.store.replace_document(document.document_id, embedded_chunks, self.embedder.identity)
        return len(chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        filters: dict | None = None,
        min_score: float | None = None,
    ) -> list[KnowledgeHit]:
        if not query.strip():
            raise ValueError("query must not be blank")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be positive")
        threshold = self.min_relevance_score if min_score is None else min_score
        _validate_min_score(threshold)
        vector = _validate_vector(self.embedder.embed(query))
        return self.store.search(vector, top_k, self.embedder.identity, filters, threshold)

    def augment_prompt(
        self,
        query: str,
        top_k: int = 4,
        filters: dict | None = None,
        min_score: float | None = None,
    ) -> str:
        hits = self.retrieve(query, top_k, filters, min_score)
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


def _validate_vector(vector) -> list[float]:
    if not isinstance(vector, (list, tuple)) or not vector:
        raise KnowledgeRetrievalError("embedder returned an empty or invalid vector")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector):
        raise KnowledgeRetrievalError("embedder returned a non-numeric or non-finite vector")
    try:
        normalized = [float(value) for value in vector]
    except (OverflowError, ValueError) as exc:
        raise KnowledgeRetrievalError(
            "embedder returned a non-numeric or non-finite vector"
        ) from exc
    if any(not isfinite(value) for value in normalized):
        raise KnowledgeRetrievalError("embedder returned a non-numeric or non-finite vector")
    if not any(value != 0.0 for value in normalized):
        raise KnowledgeRetrievalError("zero vectors are not valid for cosine similarity")
    return normalized


def _validate_min_score(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or not -1.0 <= value <= 1.0
    ):
        raise ValueError("min_score must be finite and between -1 and 1")


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
