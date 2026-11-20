import math

import pytest
from coalition_travel.infrastructure.evaluation.retrieval_metrics import score_query
from evaluate_retrieval import DEFAULT_CORPUS, DEFAULT_QUERIES, main, validate_inputs


def test_synthetic_retrieval_fixtures_have_valid_documented_qrels():
    corpus, queries = validate_inputs(DEFAULT_CORPUS, DEFAULT_QUERIES)

    assert len(corpus) == 12
    assert len(queries) == 12
    assert {query["domain"] for query in queries} == {
        "business_knowledge",
        "supplier_knowledge",
        "negotiation_knowledge",
    }


def test_graded_retrieval_metrics_use_precision_recall_mrr_and_ndcg_definitions():
    result = score_query(["a", "b", "x"], {"a": 3, "b": 1, "c": 2}, top_k=3)

    assert result["precision"] == pytest.approx(2 / 3)
    assert result["recall"] == pytest.approx(2 / 3)
    assert result["reciprocal_rank"] == 1
    expected_dcg = 7 + 1 / math.log2(3)
    expected_idcg = 7 + 3 / math.log2(3) + 1 / 2
    assert result["ndcg"] == pytest.approx(expected_dcg / expected_idcg)


def test_retrieval_validate_only_does_not_need_or_contact_ollama(capsys):
    assert main(["--validate-only"]) == 0
    assert '"queries": 12' in capsys.readouterr().out


def test_retrieval_qrels_reject_unknown_chunk(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    queries = tmp_path / "queries.jsonl"
    corpus.write_text(
        '{"document_id":"doc","source":"fixture","metadata":{"domain":"business_knowledge"},"text":"text"}\n',
        encoding="utf-8",
    )
    queries.write_text(
        '{"query_id":"q","domain":"business_knowledge","query_type":"test","query":"q","relevant_chunks":[{"chunk_id":"missing:0","grade":3}]}\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown annotated chunk"):
        validate_inputs(corpus, queries)
