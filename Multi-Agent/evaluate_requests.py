"""Run the synthetic request extraction evaluation set against local Ollama."""

import argparse
import asyncio
import json
import os
import statistics
import sys
from datetime import date
from math import ceil
from pathlib import Path

from coalition_travel.application.evaluation import score_extractions
from coalition_travel.application.request_understanding import RequestExtractionError
from coalition_travel.domain.request import TravelRequestDraft
from coalition_travel.infrastructure.llm.ollama import OllamaStructuredRequestExtractor

DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "data/eval/request_extraction.jsonl"


def load_dataset(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as dataset_file:
        for line_number, line in enumerate(dataset_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record.get("id"), str) or not record["id"].strip():
                    raise ValueError("id must be a non-empty string")
                if not isinstance(record.get("text"), str) or not record["text"].strip():
                    raise ValueError("text must be a non-empty string")
                if not isinstance(record.get("reference_date"), str):
                    raise TypeError("reference_date must be an ISO date string")
                record["reference_date"] = date.fromisoformat(record["reference_date"])
                record["expected"] = TravelRequestDraft.model_validate(record["expected"])
                records.append(record)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid evaluation record on line {line_number}: {exc}") from exc
    if not records:
        raise ValueError("evaluation dataset contains no records")
    return records


async def evaluate(records, extractor):
    predictions = []
    errors = []
    latencies = []
    successful_calls = 0
    for record in records:
        started = asyncio.get_running_loop().time()
        try:
            prediction = await extractor.extract(record["text"], record["reference_date"])
            predictions.append(prediction)
            successful_calls += 1
        except RequestExtractionError as exc:
            # Continue the batch so the report identifies every failed example.
            predictions.append(None)
            errors.append({"id": record["id"], "error": type(exc).__name__})
        finally:
            latencies.append((asyncio.get_running_loop().time() - started) * 1000)

    metrics = score_extractions([record["expected"] for record in records], predictions)
    ordered_latencies = sorted(latencies)
    p95_latency = (
        ordered_latencies[ceil(0.95 * len(ordered_latencies)) - 1] if ordered_latencies else None
    )
    metrics.update(
        {
            "provider": extractor.provider_name,
            "model": extractor.model,
            "successful_calls": successful_calls,
            "failed_calls": len(errors),
            "mean_latency_ms": sum(latencies) / len(latencies) if latencies else None,
            "p50_latency_ms": statistics.median(latencies) if latencies else None,
            "p95_latency_ms": p95_latency,
            "errors": errors,
        }
    )
    return metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL"))
    parser.add_argument(
        "--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if not args.model:
        parser.error("provide --model or set OLLAMA_MODEL")

    try:
        records = load_dataset(args.dataset)
        extractor = OllamaStructuredRequestExtractor(
            model=args.model,
            base_url=args.base_url,
            timeout_seconds=args.timeout,
        )
        result = asyncio.run(evaluate(records, extractor))
    except (OSError, ValueError) as exc:
        print(f"Evaluation could not start: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if result["failed_calls"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
