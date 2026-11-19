"""Small persistent vector store using SQLite and cosine similarity."""

import json
import math
import sqlite3

from coalition_travel.application.knowledge import (
    KnowledgeChunk,
    KnowledgeHit,
    KnowledgeRetrievalError,
)


class SQLiteVectorStore:
    def __init__(self, database_path: str):
        self.database_path = database_path
        try:
            with self._connect() as connection:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS knowledge_chunks (
                        chunk_id TEXT PRIMARY KEY,
                        document_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        metadata TEXT NOT NULL,
                        source TEXT NOT NULL,
                        vector TEXT NOT NULL
                    )"""
                )
        except sqlite3.Error as exc:
            raise KnowledgeRetrievalError("could not initialize knowledge database") from exc

    def _connect(self):
        return sqlite3.connect(self.database_path)

    def upsert(self, chunk: KnowledgeChunk, vector: list[float]) -> None:
        if not vector or any(not math.isfinite(value) for value in vector):
            raise ValueError("embedding must contain finite values")
        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT OR REPLACE INTO knowledge_chunks
                    (chunk_id, document_id, text, metadata, source, vector)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.text,
                        json.dumps(chunk.metadata),
                        chunk.source,
                        json.dumps(vector),
                    ),
                )
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise KnowledgeRetrievalError("could not store knowledge chunk") from exc

    def search(
        self, vector: list[float], top_k: int, filters: dict | None = None
    ) -> list[KnowledgeHit]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT chunk_id, document_id, text, metadata, source, vector FROM knowledge_chunks"
                ).fetchall()
        except sqlite3.Error as exc:
            raise KnowledgeRetrievalError("could not read knowledge database") from exc
        hits = []
        query_norm = math.sqrt(sum(value * value for value in vector))
        for chunk_id, document_id, text, metadata_json, source, vector_json in rows:
            metadata = json.loads(metadata_json)
            if filters and any(metadata.get(key) != value for key, value in filters.items()):
                continue
            stored = json.loads(vector_json)
            if len(stored) != len(vector):
                raise KnowledgeRetrievalError(
                    "embedding dimensions differ; index and query must use the same model"
                )
            stored_norm = math.sqrt(sum(value * value for value in stored))
            score = (
                sum(left * right for left, right in zip(vector, stored))
                / (query_norm * stored_norm)
                if query_norm and stored_norm
                else 0.0
            )
            chunk = KnowledgeChunk(chunk_id, document_id, text, metadata, source)
            hits.append(KnowledgeHit(chunk, score))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:top_k]
