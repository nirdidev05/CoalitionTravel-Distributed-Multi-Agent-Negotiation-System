"""Run reproducible retrieval sweeps against local Ollama embeddings."""

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

from coalition_travel.application.knowledge import (
    KnowledgeDocument,
    KnowledgeRetrievalError,
    KnowledgeService,
)
from coalition_travel.infrastructure.evaluation.provenance import create_run_metadata
from coalition_travel.infrastructure.evaluation.retrieval_metrics import score_query

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS = ROOT / "data/eval/rag/corpus_v1.jsonl"
DEFAULT_QUERIES = ROOT / "data/eval/rag/queries_v1.jsonl"


def read_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if line.strip():
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict):
                        raise TypeError("record must be an object")
                    records.append(record)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
    if not records:
        raise ValueError(f"dataset is empty: {path}")
    return records


def validate_inputs(corpus_path: Path, queries_path: Path) -> tuple[list[dict], list[dict]]:
    corpus, queries = read_jsonl(corpus_path), read_jsonl(queries_path)
    corpus_ids = [item.get("document_id") for item in corpus]
    query_ids = [item.get("query_id") for item in queries]
    if any(not isinstance(value, str) or not value for value in corpus_ids) or len(
        set(corpus_ids)
    ) != len(corpus_ids):
        raise ValueError("corpus document_id values must be unique non-empty strings")
    if any(not isinstance(value, str) or not value for value in query_ids) or len(
        set(query_ids)
    ) != len(query_ids):
        raise ValueError("query_id values must be unique non-empty strings")
    known_documents = set(corpus_ids)
    for item in corpus:
        if (
            not isinstance(item.get("text"), str)
            or not item["text"].strip()
            or not isinstance(item.get("source"), str)
            or not item["source"].strip()
            or not isinstance(item.get("metadata", {}), dict)
            or not isinstance(item.get("metadata", {}).get("domain"), str)
            or item.get("metadata", {}).get("domain")
            not in {
                "business_knowledge",
                "supplier_knowledge",
                "negotiation_knowledge",
            }
        ):
            raise ValueError(f"invalid corpus document: {item.get('document_id')}")
    for query in queries:
        if query.get("domain") not in {
            "business_knowledge",
            "supplier_knowledge",
            "negotiation_knowledge",
        }:
            raise ValueError(f"unsupported or missing query domain: {query.get('query_id')}")
        if not isinstance(query.get("query"), str) or not query["query"].strip():
            raise ValueError(f"query text is missing: {query.get('query_id')}")
        if not isinstance(query.get("query_type"), str) or not query["query_type"].strip():
            raise ValueError(f"query_type is missing: {query.get('query_id')}")
        judgments = query.get("relevant_chunks")
        if not isinstance(judgments, list) or not judgments:
            raise ValueError(f"relevant_chunks must be a non-empty list: {query['query_id']}")
        seen = set()
        for judgment in judgments:
            if not isinstance(judgment, dict):
                raise TypeError(f"invalid judgment object in {query['query_id']}")
            chunk_id, grade = judgment.get("chunk_id"), judgment.get("grade")
            if not isinstance(chunk_id, str):
                raise TypeError(f"judgment chunk_id must be a string in {query['query_id']}")
            document_id, separator, chunk_index = chunk_id.rpartition(":")
            if not separator or not chunk_index.isdigit() or document_id not in known_documents:
                raise ValueError(f"unknown annotated chunk {chunk_id!r} in {query['query_id']}")
            if chunk_id in seen:
                raise ValueError(f"duplicate judgment for {chunk_id!r} in {query['query_id']}")
            if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= 3:
                raise ValueError(f"grade must be an integer from 0 to 3 in {query['query_id']}")
            seen.add(chunk_id)
    return corpus, queries


def run_sweep(service, corpus, queries, top_ks, thresholds):
    index_started = time.perf_counter()
    indexed_chunks = 0
    for item in corpus:
        indexed_chunks += service.index_document(
            KnowledgeDocument(
                item["document_id"], item["text"], item.get("metadata", {}), item["source"]
            )
        )
    indexing_seconds = time.perf_counter() - index_started
    sweeps = []
    for top_k in top_ks:
        for threshold in thresholds:
            per_query = []
            for query in queries:
                started = time.perf_counter()
                try:
                    hits = service.retrieve(
                        query["query"],
                        top_k=top_k,
                        filters={"domain": query["domain"]},
                        min_score=threshold,
                    )
                except KnowledgeRetrievalError as exc:
                    latency_ms = (time.perf_counter() - started) * 1000
                    per_query.append(
                        {
                            "query_id": query["query_id"],
                            "domain": query["domain"],
                            "query_type": query["query_type"],
                            "latency_ms": latency_ms,
                            "error": type(exc).__name__,
                        }
                    )
                    continue
                latency_ms = (time.perf_counter() - started) * 1000
                # The fixtures annotate one passage per document. Collapse retrieved
                # chunks to their source passage so chunk-size sweeps remain comparable.
                grades = {
                    item["chunk_id"].rpartition(":")[0]: item["grade"]
                    for item in query["relevant_chunks"]
                }
                ranked_documents = list(dict.fromkeys(hit.chunk.document_id for hit in hits))
                metrics = score_query(ranked_documents, grades, top_k)
                per_query.append(
                    {
                        "query_id": query["query_id"],
                        "domain": query["domain"],
                        "query_type": query["query_type"],
                        "latency_ms": latency_ms,
                        **metrics,
                    }
                )
            successful = [row for row in per_query if "error" not in row]
            summary = {
                key: statistics.mean(row[key] for row in successful) if successful else None
                for key in ("precision", "recall", "reciprocal_rank", "ndcg", "latency_ms")
            }
            by_domain = {}
            for domain in sorted({row["domain"] for row in per_query}):
                domain_rows = [
                    row for row in per_query if row["domain"] == domain and "error" not in row
                ]
                by_domain[domain] = {
                    key: statistics.mean(row[key] for row in domain_rows) if domain_rows else None
                    for key in ("precision", "recall", "reciprocal_rank", "ndcg", "latency_ms")
                }
            sweeps.append(
                {
                    "top_k": top_k,
                    "min_score": threshold,
                    "summary": summary,
                    "by_domain": by_domain,
                    "errors": sum("error" in row for row in per_query),
                    "queries": per_query,
                }
            )
    return {
        "indexing_seconds": indexing_seconds,
        "indexed_documents": len(corpus),
        "indexed_chunks": indexed_chunks,
        "sweeps": sweeps,
    }


def _integers(value):
    parsed = [int(part) for part in value.split(",")]
    if not parsed or any(number < 1 for number in parsed):
        raise argparse.ArgumentTypeError("values must be positive comma-separated integers")
    return sorted(set(parsed))


def _floats(value):
    try:
        parsed = [float(part) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("values must be comma-separated numbers") from exc
    if not parsed or any(not -1 <= number <= 1 for number in parsed):
        raise argparse.ArgumentTypeError("thresholds must be between -1 and 1")
    return sorted(set(parsed))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--model", default=os.getenv("OLLAMA_EMBEDDING_MODEL"))
    parser.add_argument("--model-digest", help="Immutable Ollama model digest when available")
    parser.add_argument(
        "--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    parser.add_argument(
        "--database", type=Path, help="New, model-specific SQLite index path (must not exist)"
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--chunk-size", type=int, default=1200)
    parser.add_argument("--overlap", type=int, default=0)
    parser.add_argument("--top-k", type=_integers, default=[1, 3, 5])
    parser.add_argument("--thresholds", type=_floats, default=[0.0, 0.2, 0.4])
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        corpus, queries = validate_inputs(args.corpus, args.queries)
        if args.chunk_size < 1 or args.overlap < 0 or args.overlap >= args.chunk_size:
            raise ValueError("chunk size must be positive and overlap smaller than chunk size")
        if args.validate_only:
            print(
                json.dumps(
                    {"valid": True, "corpus_documents": len(corpus), "queries": len(queries)}
                )
            )
            return 0
        if not args.model or not args.database:
            parser.error("provide --model and a new --database path (or use --validate-only)")
        if args.database.exists():
            raise ValueError(f"refusing to overwrite existing index: {args.database}")
        if not args.database.parent.exists():
            raise ValueError(f"database parent directory does not exist: {args.database.parent}")

        from coalition_travel.infrastructure.knowledge.ollama_embeddings import OllamaEmbedder
        from coalition_travel.infrastructure.knowledge.sqlite_store import SQLiteVectorStore

        signature = "/api/embed-default-options-v1"
        if args.model_digest:
            signature += f";digest={args.model_digest}"
        embedder = OllamaEmbedder(args.model, args.base_url, configuration_signature=signature)
        store = SQLiteVectorStore(str(args.database))
        service = KnowledgeService(embedder, store, args.chunk_size, args.overlap)
        result = run_sweep(service, corpus, queries, args.top_k, args.thresholds)
        result["run"] = create_run_metadata(
            "rag_retrieval",
            args.queries,
            {
                "provider": "ollama",
                "model": args.model,
                "model_digest": args.model_digest,
                "embedding_signature": signature,
                "dimension": store.get_embedding_space().dimension,
                "corpus_path": str(args.corpus),
                "chunk_size": args.chunk_size,
                "overlap": args.overlap,
                "top_k": args.top_k,
                "thresholds": args.thresholds,
            },
            corpus_path=args.corpus,
        )
        if any(sweep["errors"] for sweep in result["sweeps"]):
            result["run"]["status"] = "partial"
        rendered = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 1 if result["run"]["status"] == "partial" else 0
    except KnowledgeRetrievalError as exc:
        run = create_run_metadata(
            "rag_retrieval",
            args.queries,
            {
                "provider": "ollama",
                "model": args.model,
                "model_digest": args.model_digest,
                "corpus_path": str(args.corpus),
                "chunk_size": args.chunk_size,
                "overlap": args.overlap,
                "top_k": args.top_k,
                "thresholds": args.thresholds,
            },
            corpus_path=args.corpus,
        )
        run["status"] = "failed"
        failure = {"run": run, "errors": [{"error": type(exc).__name__}]}
        rendered = json.dumps(failure, indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Retrieval evaluation could not start: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
