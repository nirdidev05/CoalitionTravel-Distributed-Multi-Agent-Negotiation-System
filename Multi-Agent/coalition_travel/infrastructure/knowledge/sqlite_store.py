"""Persistent vector store using atomic document replacement and cosine similarity."""

import json
import math
import sqlite3

from coalition_travel.application.knowledge import (
    EmbeddingIdentity,
    EmbeddingSpace,
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

    @staticmethod
    def _metadata_table_exists(connection) -> bool:
        return (
            connection.execute(
                "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?)",
                ("knowledge_embedding_space",),
            ).fetchone()[0]
            == 1
        )

    @staticmethod
    def _create_embedding_metadata_table(connection) -> None:
        connection.execute(
            """CREATE TABLE knowledge_embedding_space (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                configuration_signature TEXT NOT NULL,
                dimension INTEGER NOT NULL CHECK (dimension > 0)
            )"""
        )

    def get_embedding_space(self) -> EmbeddingSpace | None:
        try:
            with self._connect() as connection:
                has_chunks = connection.execute(
                    "SELECT EXISTS(SELECT 1 FROM knowledge_chunks)"
                ).fetchone()[0]
                if not self._metadata_table_exists(connection):
                    if has_chunks:
                        raise KnowledgeRetrievalError(
                            "legacy vectors have no embedding identity; reindex into a new database"
                        )
                    return None
                row = connection.execute(
                    """SELECT provider, model, configuration_signature, dimension
                    FROM knowledge_embedding_space WHERE singleton = 1"""
                ).fetchone()
        except sqlite3.Error as exc:
            raise KnowledgeRetrievalError("could not read embedding metadata") from exc
        if row is None:
            if has_chunks:
                raise KnowledgeRetrievalError(
                    "legacy vectors have no embedding identity; reindex into a new database"
                )
            return None
        provider, model, signature, dimension = row
        return EmbeddingSpace(EmbeddingIdentity(provider, model, signature), dimension)

    def replace_document(
        self,
        document_id: str,
        chunks: list[tuple[KnowledgeChunk, list[float]]],
        identity: EmbeddingIdentity,
    ) -> None:
        if not chunks:
            raise ValueError("document replacement requires at least one chunk")
        vectors = [_validate_vector(vector) for _, vector in chunks]
        dimensions = {len(vector) for vector in vectors}
        if len(dimensions) != 1:
            raise KnowledgeRetrievalError("document embeddings have inconsistent dimensions")
        dimension = dimensions.pop()
        if any(chunk.document_id != document_id for chunk, _ in chunks):
            raise ValueError("all replacement chunks must belong to the requested document")

        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                has_chunks = connection.execute(
                    "SELECT EXISTS(SELECT 1 FROM knowledge_chunks)"
                ).fetchone()[0]
                has_metadata = self._metadata_table_exists(connection)
                if not has_metadata and has_chunks:
                    raise KnowledgeRetrievalError(
                        "legacy vectors have no embedding identity; reindex into a new database"
                    )
                if not has_metadata:
                    self._create_embedding_metadata_table(connection)
                current = connection.execute(
                    """SELECT provider, model, configuration_signature, dimension
                    FROM knowledge_embedding_space WHERE singleton = 1"""
                ).fetchone()
                if current is None and has_chunks:
                    raise KnowledgeRetrievalError(
                        "legacy vectors have no embedding identity; reindex into a new database"
                    )
                if current is not None:
                    expected = (identity.provider, identity.model, identity.configuration_signature)
                    if current[:3] != expected:
                        raise KnowledgeRetrievalError(
                            "embedding model or configuration differs from the indexed space"
                        )
                    if current[3] != dimension:
                        raise KnowledgeRetrievalError(
                            "embedding dimensions differ from the indexed space"
                        )
                else:
                    connection.execute(
                        """INSERT INTO knowledge_embedding_space
                        (singleton, provider, model, configuration_signature, dimension)
                        VALUES (1, ?, ?, ?, ?)""",
                        (
                            identity.provider,
                            identity.model,
                            identity.configuration_signature,
                            dimension,
                        ),
                    )

                connection.execute(
                    "DELETE FROM knowledge_chunks WHERE document_id = ?", (document_id,)
                )
                for (chunk, _), vector in zip(chunks, vectors):
                    self._insert_chunk(connection, chunk, vector)
        except KnowledgeRetrievalError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise KnowledgeRetrievalError("could not replace knowledge document") from exc

    @staticmethod
    def _insert_chunk(connection, chunk: KnowledgeChunk, vector: list[float]) -> None:
        connection.execute(
            """INSERT INTO knowledge_chunks
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

    def search(
        self,
        vector: list[float],
        top_k: int,
        identity: EmbeddingIdentity,
        filters: dict | None = None,
        min_score: float = 0.0,
    ) -> list[KnowledgeHit]:
        query = _validate_vector(vector)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """SELECT chunk_id, document_id, text, metadata, source, vector
                    FROM knowledge_chunks"""
                ).fetchall()
                if rows and self._metadata_table_exists(connection):
                    metadata = connection.execute(
                        """SELECT provider, model, configuration_signature, dimension
                        FROM knowledge_embedding_space WHERE singleton = 1"""
                    ).fetchone()
                else:
                    metadata = None
        except sqlite3.Error as exc:
            raise KnowledgeRetrievalError("could not read knowledge database") from exc

        if not rows:
            return []
        if metadata is None:
            raise KnowledgeRetrievalError(
                "legacy vectors have no embedding identity; reindex into a new database"
            )
        expected_identity = (identity.provider, identity.model, identity.configuration_signature)
        if metadata[:3] != expected_identity:
            raise KnowledgeRetrievalError(
                "query embedder differs from the model or configuration used for indexing"
            )
        if metadata[3] != len(query):
            raise KnowledgeRetrievalError(
                "query embedding dimension differs from the indexed space"
            )

        query_norm = math.hypot(*query)
        hits = []
        for chunk_id, document_id, text, metadata_json, source, vector_json in rows:
            try:
                chunk_metadata = json.loads(metadata_json)
                stored = _validate_vector(json.loads(vector_json))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise KnowledgeRetrievalError(
                    "stored knowledge vector or metadata is invalid"
                ) from exc
            if not isinstance(chunk_metadata, dict):
                raise KnowledgeRetrievalError("stored chunk metadata must be a JSON object")
            if filters and any(chunk_metadata.get(key) != value for key, value in filters.items()):
                continue
            if len(stored) != len(query):
                raise KnowledgeRetrievalError(
                    "stored embedding dimensions differ from the indexed space"
                )
            stored_norm = math.hypot(*stored)
            score = math.fsum(
                (left / query_norm) * (right / stored_norm) for left, right in zip(query, stored)
            )
            score = max(-1.0, min(1.0, score))
            if score >= min_score:
                chunk = KnowledgeChunk(chunk_id, document_id, text, chunk_metadata, source)
                hits.append(KnowledgeHit(chunk, score))
        return sorted(hits, key=lambda hit: (-hit.score, hit.chunk.chunk_id))[:top_k]


def _validate_vector(vector) -> list[float]:
    if not isinstance(vector, (list, tuple)) or not vector:
        raise KnowledgeRetrievalError("embedding must be a non-empty vector")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vector):
        raise KnowledgeRetrievalError("embedding must contain finite numeric values")
    try:
        values = [float(value) for value in vector]
    except (OverflowError, ValueError) as exc:
        raise KnowledgeRetrievalError("embedding must contain finite numeric values") from exc
    if any(not math.isfinite(value) for value in values):
        raise KnowledgeRetrievalError("embedding must contain finite numeric values")
    if not any(value != 0.0 for value in values):
        raise KnowledgeRetrievalError("zero vectors are not valid for cosine similarity")
    return values
