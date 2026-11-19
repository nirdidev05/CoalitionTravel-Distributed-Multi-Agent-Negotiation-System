import json
from io import BytesIO
from pathlib import Path

import pytest
from coalition_travel.application.knowledge import (
    KnowledgeDocument,
    KnowledgeRetrievalError,
    KnowledgeService,
)
from coalition_travel.infrastructure.knowledge.ingestion import KnowledgeIngestionPipeline
from coalition_travel.infrastructure.knowledge.ollama_embeddings import OllamaEmbedder
from coalition_travel.infrastructure.knowledge.source_loader import load_document
from coalition_travel.infrastructure.knowledge.sqlite_store import SQLiteVectorStore


class FakeEmbedder:
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
