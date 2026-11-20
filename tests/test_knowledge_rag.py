import json
from io import BytesIO
from pathlib import Path

import pytest
from coalition_travel.application.knowledge import (
    EmbeddingIdentity,
    KnowledgeDocument,
    KnowledgeRetrievalError,
    KnowledgeService,
)
from coalition_travel.infrastructure.knowledge.ingestion import KnowledgeIngestionPipeline
from coalition_travel.infrastructure.knowledge.ollama_embeddings import OllamaEmbedder
from coalition_travel.infrastructure.knowledge.source_loader import load_document
from coalition_travel.infrastructure.knowledge.sqlite_store import SQLiteVectorStore


class FakeEmbedder:
    identity = EmbeddingIdentity("fake", "lexical-test-v1", "counts-v1")

    def embed(self, text):
        lowered = text.lower()
        return [
            float(lowered.count("business")),
            float(lowered.count("supplier")),
            float(lowered.count("negotiation")),
            float(len(lowered)),
        ]


def test_rag_chunks_indexes_embeddings_searches_top_k_and_keeps_sources(tmp_path):
    service = KnowledgeService(
        FakeEmbedder(), SQLiteVectorStore(str(tmp_path / "kb.sqlite")), chunk_size=40, overlap=5
    )
    document = KnowledgeDocument(
        "doc-1",
        "business rule one. business rule two. supplier rule three.",
        {"domain": "business_knowledge", "document_type": "policy"},
        "policy.md",
    )

    indexed = service.index_document(document)
    hits = service.retrieve("business rule", top_k=2, filters={"domain": "business_knowledge"})
    augmented = service.augment_prompt("business rule", filters={"domain": "business_knowledge"})

    assert indexed > 1
    assert len(hits) == 2
    assert all(hit.chunk.source == "policy.md" for hit in hits)
    assert "document_id=doc-1" in augmented
    assert "not live inventory" in augmented


def test_rag_filters_metadata_and_returns_top_k(tmp_path):
    service = KnowledgeService(FakeEmbedder(), SQLiteVectorStore(str(tmp_path / "kb.sqlite")))
    service.index_document(
        KnowledgeDocument(
            "business", "business travel policy", {"domain": "business_knowledge"}, "business.md"
        )
    )
    service.index_document(
        KnowledgeDocument(
            "supplier",
            "supplier baggage policy",
            {"domain": "supplier_knowledge", "supplier_id": "S1"},
            "supplier.md",
        )
    )

    hits = service.retrieve("supplier policy", top_k=1, filters={"domain": "supplier_knowledge"})
    assert len(hits) == 1
    assert hits[0].chunk.document_id == "supplier"


def test_offline_ingestion_indexes_supported_files_in_a_directory(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "business.md").write_text("business policy", encoding="utf-8")
    (docs / "supplier.txt").write_text("supplier policy", encoding="utf-8")
    (docs / "ignored.pdf").write_bytes(b"not parsed")
    service = KnowledgeService(FakeEmbedder(), SQLiteVectorStore(str(tmp_path / "kb.sqlite")))

    result = KnowledgeIngestionPipeline(service).index_path(docs, {"domain": "business_knowledge"})

    assert {Path(key).name for key in result} == {"business.md", "supplier.txt"}
    assert all(count == 1 for count in result.values())


def test_rag_rejects_empty_documents_and_invalid_queries(tmp_path):
    service = KnowledgeService(FakeEmbedder(), SQLiteVectorStore(str(tmp_path / "kb.sqlite")))
    with pytest.raises(ValueError, match="must not be empty"):
        service.index_document(KnowledgeDocument("empty", "  ", {}, "empty.md"))
    with pytest.raises(ValueError, match="query must not be blank"):
        service.retrieve(" ")


def test_source_loader_reads_markdown_and_rejects_empty_or_unsupported(tmp_path):
    source = tmp_path / "rules.md"
    source.write_text("Travel rule", encoding="utf-8")
    assert load_document(source, {"domain": "business_knowledge"}).text == "Travel rule"
    empty = tmp_path / "empty.txt"
    empty.write_text(" ", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_document(empty)
    with pytest.raises(ValueError, match="unsupported"):
        load_document(tmp_path / "file.pdf")


def test_vector_store_failure_is_reported_as_infrastructure_error(tmp_path):
    with pytest.raises(KnowledgeRetrievalError):
        SQLiteVectorStore(str(tmp_path / "missing" / "kb.sqlite"))


def test_ollama_embedding_adapter_uses_embed_endpoint_and_response(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return BytesIO(json.dumps({"embeddings": [[0.1, 0.2, 0.3]]}).encode())

    monkeypatch.setattr(
        "coalition_travel.infrastructure.knowledge.ollama_embeddings.urlopen", fake_urlopen
    )
    vector = OllamaEmbedder("embedding-model", timeout_seconds=7).embed("policy text")

    assert vector == [0.1, 0.2, 0.3]
    assert captured["url"] == "http://localhost:11434/api/embed"
    assert captured["body"] == {"model": "embedding-model", "input": "policy text"}
    assert captured["timeout"] == 7
    assert OllamaEmbedder("embedding-model").identity.provider == "ollama"
    assert OllamaEmbedder("embedding-model").identity.model == "embedding-model"


def test_ollama_embedding_adapter_rejects_non_finite_values(monkeypatch):
    monkeypatch.setattr(
        "coalition_travel.infrastructure.knowledge.ollama_embeddings.urlopen",
        lambda request, timeout: BytesIO(json.dumps({"embeddings": [[float("inf")]]}).encode()),
    )

    with pytest.raises(KnowledgeRetrievalError, match="non-finite"):
        OllamaEmbedder("embedding-model").embed("policy text")


def _stored_chunks(database_path, document_id):
    import sqlite3

    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            "SELECT chunk_id, text, source FROM knowledge_chunks WHERE document_id = ? ORDER BY chunk_id",
            (document_id,),
        ).fetchall()


class LengthEmbedder:
    identity = EmbeddingIdentity("test", "length-v1", "fixed-v1")

    def __init__(self, fail_on=None):
        self.fail_on = fail_on

    def embed(self, text):
        if self.fail_on and self.fail_on in text:
            raise RuntimeError("synthetic embedding failure")
        return [float(len(text)), 1.0]


def test_reindexing_with_fewer_chunks_removes_obsolete_tail_chunks(tmp_path):
    path = tmp_path / "replace.sqlite"
    service = KnowledgeService(
        LengthEmbedder(), SQLiteVectorStore(str(path)), chunk_size=10, overlap=0
    )
    service.index_document(KnowledgeDocument("doc", "a" * 100, {}, "source.md"))
    service.index_document(KnowledgeDocument("doc", "b" * 40, {}, "source.md"))

    rows = _stored_chunks(path, "doc")
    assert len(rows) == 4
    assert [row[0] for row in rows] == [f"doc:{i}" for i in range(4)]
    assert all("b" in row[1] for row in rows)


def test_reindexing_with_more_chunks_adds_full_new_version(tmp_path):
    path = tmp_path / "replace.sqlite"
    service = KnowledgeService(
        LengthEmbedder(), SQLiteVectorStore(str(path)), chunk_size=10, overlap=0
    )
    service.index_document(KnowledgeDocument("doc", "a" * 40, {}, "source.md"))
    service.index_document(KnowledgeDocument("doc", "b" * 100, {}, "source.md"))

    assert len(_stored_chunks(path, "doc")) == 10


def test_reindexing_identical_document_does_not_duplicate_chunks(tmp_path):
    path = tmp_path / "replace.sqlite"
    service = KnowledgeService(
        LengthEmbedder(), SQLiteVectorStore(str(path)), chunk_size=10, overlap=0
    )
    document = KnowledgeDocument("doc", "same text " * 4, {}, "source.md")

    first_count = service.index_document(document)
    second_count = service.index_document(document)

    assert second_count == first_count
    assert len(_stored_chunks(path, "doc")) == first_count


def test_embedding_failure_keeps_previous_document_version(tmp_path):
    path = tmp_path / "replace.sqlite"
    embedder = LengthEmbedder()
    service = KnowledgeService(embedder, SQLiteVectorStore(str(path)), chunk_size=10, overlap=0)
    service.index_document(KnowledgeDocument("doc", "old " * 10, {}, "old.md"))
    previous = _stored_chunks(path, "doc")
    embedder.fail_on = "FAIL"

    with pytest.raises(RuntimeError, match="synthetic embedding failure"):
        service.index_document(KnowledgeDocument("doc", "new FAIL content", {}, "new.md"))

    assert _stored_chunks(path, "doc") == previous


def test_sqlite_failure_rolls_back_document_replacement(tmp_path):
    import sqlite3

    path = tmp_path / "replace.sqlite"
    service = KnowledgeService(
        LengthEmbedder(), SQLiteVectorStore(str(path)), chunk_size=10, overlap=0
    )
    service.index_document(KnowledgeDocument("doc", "old " * 10, {}, "old.md"))
    previous = _stored_chunks(path, "doc")
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TRIGGER fail_second_chunk BEFORE INSERT ON knowledge_chunks
            WHEN NEW.chunk_id = 'doc:1' BEGIN SELECT RAISE(ABORT, 'synthetic write failure'); END"""
        )

    with pytest.raises(KnowledgeRetrievalError, match="could not replace"):
        service.index_document(KnowledgeDocument("doc", "new " * 20, {}, "new.md"))

    assert _stored_chunks(path, "doc") == previous


def test_reindexing_one_document_does_not_change_another(tmp_path):
    path = tmp_path / "replace.sqlite"
    service = KnowledgeService(
        LengthEmbedder(), SQLiteVectorStore(str(path)), chunk_size=10, overlap=0
    )
    service.index_document(KnowledgeDocument("first", "a" * 40, {}, "first.md"))
    service.index_document(KnowledgeDocument("second", "z" * 30, {}, "second.md"))
    second_before = _stored_chunks(path, "second")

    service.index_document(KnowledgeDocument("first", "b" * 20, {}, "first-v2.md"))

    assert _stored_chunks(path, "second") == second_before
    assert all(row[2] == "first-v2.md" for row in _stored_chunks(path, "first"))


def test_embedding_identity_and_dimension_must_match_existing_index(tmp_path):
    path = tmp_path / "identity.sqlite"
    store = SQLiteVectorStore(str(path))
    service = KnowledgeService(LengthEmbedder(), store)
    service.index_document(KnowledgeDocument("doc", "known text", {}, "source.md"))
    space = store.get_embedding_space()
    assert space.identity == LengthEmbedder.identity
    assert space.dimension == 2
    other_model = LengthEmbedder()
    other_model.identity = EmbeddingIdentity("test", "different-model", "fixed-v1")
    other_configuration = LengthEmbedder()
    other_configuration.identity = EmbeddingIdentity("test", "length-v1", "changed-v1")
    other_dimension = LengthEmbedder()
    other_dimension.embed = lambda text: [1.0, 2.0, 3.0]

    with pytest.raises(KnowledgeRetrievalError, match="differs from the model"):
        KnowledgeService(other_model, store).retrieve("known text")
    with pytest.raises(KnowledgeRetrievalError, match="differs from the model"):
        KnowledgeService(other_configuration, store).retrieve("known text")
    with pytest.raises(KnowledgeRetrievalError, match="dimensions differ"):
        KnowledgeService(other_dimension, store).index_document(
            KnowledgeDocument("other", "new text", {}, "other.md")
        )


def test_legacy_vectors_without_identity_are_preserved_but_rejected(tmp_path):
    import sqlite3

    path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE knowledge_chunks (
            chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, text TEXT NOT NULL,
            metadata TEXT NOT NULL, source TEXT NOT NULL, vector TEXT NOT NULL)"""
        )
        connection.execute(
            "INSERT INTO knowledge_chunks VALUES (?, ?, ?, ?, ?, ?)",
            ("legacy:0", "legacy", "old", "{}", "old.md", "[1.0, 2.0]"),
        )
    service = KnowledgeService(LengthEmbedder(), SQLiteVectorStore(str(path)))

    with pytest.raises(KnowledgeRetrievalError, match="legacy vectors"):
        service.retrieve("query")
    assert len(_stored_chunks(path, "legacy")) == 1
    with sqlite3.connect(path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("knowledge_embedding_space",),
            ).fetchone()[0]
            == 0
        )


def test_relevance_threshold_filters_weak_hits_and_is_configurable(tmp_path):
    service = KnowledgeService(
        FakeEmbedder(), SQLiteVectorStore(str(tmp_path / "threshold.sqlite"))
    )
    service.index_document(KnowledgeDocument("doc", "business travel policy", {}, "source.md"))

    assert service.retrieve("unrelated supplier", min_score=1.0) == []
    assert service.retrieve("business travel policy", min_score=1.0)
    assert service.retrieve("business travel policy", min_score=1.0, top_k=1)
    configured = KnowledgeService(
        FakeEmbedder(),
        SQLiteVectorStore(str(tmp_path / "threshold.sqlite")),
        min_relevance_score=1.0,
    )
    assert configured.retrieve("unrelated supplier") == []
    with pytest.raises(ValueError, match="between -1 and 1"):
        service.retrieve("business travel policy", min_score=1.1)


def test_zero_query_embedding_is_rejected_before_cosine_search(tmp_path):
    class ZeroQueryEmbedder(LengthEmbedder):
        def embed(self, text):
            if text == "zero query":
                return [0.0, 0.0]
            return super().embed(text)

    service = KnowledgeService(
        ZeroQueryEmbedder(), SQLiteVectorStore(str(tmp_path / "zero.sqlite"))
    )
    service.index_document(KnowledgeDocument("doc", "known text", {}, "source.md"))

    with pytest.raises(KnowledgeRetrievalError, match="zero vectors"):
        service.retrieve("zero query")


@pytest.mark.parametrize("vector", [[], [0.0, 0.0], [float("nan")], [True, 1.0]])
def test_invalid_or_zero_document_embeddings_are_rejected_without_polluting_index(tmp_path, vector):
    class InvalidEmbedder:
        identity = EmbeddingIdentity("test", "invalid", "v1")

        def embed(self, text):
            return vector

    path = tmp_path / "invalid.sqlite"
    service = KnowledgeService(InvalidEmbedder(), SQLiteVectorStore(str(path)))
    with pytest.raises(KnowledgeRetrievalError):
        service.index_document(KnowledgeDocument("doc", "document", {}, "source.md"))
    assert _stored_chunks(path, "doc") == []
