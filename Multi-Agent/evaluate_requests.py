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
from typing import Literal

from coalition_travel.application.evaluation import score_extractions
from coalition_travel.application.request_contracts import (
    TravelerProfileDraft,
    TravelRequestDraft,
)
from coalition_travel.application.request_understanding import (
    RequestExtractionError,
    validate_request_draft,
)
from coalition_travel.infrastructure.evaluation.provenance import create_run_metadata
from coalition_travel.infrastructure.llm.ollama import (
    EXTRACTION_PROMPT_VERSION,
    SCHEMA_TRANSPORT_VERSION,
    OllamaStructuredRequestExtractor,
)

DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "data/eval"
DEFAULT_DATASET = DATA_DIRECTORY / "request_extraction_v2.jsonl"
REQUEST_STATUSES = {"ready", "needs_clarification", "invalid"}


def load_dataset(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as dataset_file:
        for line_number, line in enumerate(dataset_file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise TypeError("record must be a JSON object")
                if not isinstance(record.get("id"), str) or not record["id"].strip():
                    raise ValueError("id must be a non-empty string")
                if not isinstance(record.get("text"), str) or not record["text"].strip():
                    raise ValueError("text must be a non-empty string")
                if not isinstance(record.get("reference_date"), str):
                    raise TypeError("reference_date must be an ISO date string")
                record["reference_date"] = date.fromisoformat(record["reference_date"])
                record["expected"] = TravelRequestDraft.model_validate(record["expected"])
                if (
                    "expected_status" in record
                    and record["expected_status"] not in REQUEST_STATUSES
                ):
                    raise ValueError(
                        "expected_status must be ready, needs_clarification or invalid"
                    )
                records.append(record)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid evaluation record on line {line_number}: {exc}") from exc
    if not records:
        raise ValueError("evaluation dataset contains no records")
    return records


def load_profile_dataset(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as dataset_file:
        for line_number, line in enumerate(dataset_file, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or not all(
                    isinstance(record.get(key), str) and record[key].strip()
                    for key in ("id", "text")
                ):
                    raise ValueError("id and text must be non-empty strings")
                profiles = [
                    TravelerProfileDraft.model_validate(item)
                    for item in record["expected_profiles"]
                ]
                total = sum(profile.traveller_count for profile in profiles)
                record["expected"] = TravelRequestDraft(
                    destination="profile-evaluation-fixture",
                    travellers=max(1, total),
                    budget_per_person=1,
                    profiles=profiles,
                )
                record["reference_date"] = date(2026, 11, 18)
                record["expected_status"] = "ready"
                records.append(record)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"invalid profile evaluation record on line {line_number}: {exc}"
                ) from exc
    if not records:
        raise ValueError("profile evaluation dataset contains no records")
    return records


async def evaluate(records, extractor):
    predictions = []
    errors = []
    latencies = []
    examples = []
    successful_calls = 0
    status_labels = (*sorted(REQUEST_STATUSES), "extraction_error")
    confusion = {label: {candidate: 0 for candidate in status_labels} for label in status_labels}
    expected_statuses = []
    actual_statuses = []
    for record in records:
        started = asyncio.get_running_loop().time()
        expected_status = (
            record.get("expected_status")
            or validate_request_draft(record["expected"], record["reference_date"]).status
        )
        try:
            prediction = await extractor.extract(record["text"], record["reference_date"])
            predictions.append(prediction)
            successful_calls += 1
            actual_status = validate_request_draft(prediction, record["reference_date"]).status
            actual_dump = prediction.model_dump(mode="json")
        except RequestExtractionError as exc:
            # Continue the batch so the report identifies every failed example.
            predictions.append(None)
            errors.append({"id": record["id"], "error": type(exc).__name__})
            actual_status = "extraction_error"
            actual_dump = None
        finally:
            latency_ms = (asyncio.get_running_loop().time() - started) * 1000
            latencies.append(latency_ms)
        confusion[expected_status][actual_status] += 1
        expected_statuses.append(expected_status)
        actual_statuses.append(actual_status)
        examples.append(
            {
                "id": record["id"],
                "expected_status": expected_status,
                "actual_status": actual_status,
                "expected": record["expected"].model_dump(mode="json"),
                "actual": actual_dump,
                "latency_ms": latency_ms,
            }
        )

    metrics = score_extractions([record["expected"] for record in records], predictions)
    status_matches = sum(
        expected == actual for expected, actual in zip(expected_statuses, actual_statuses)
    )

    def binary_status_metrics(label: Literal["needs_clarification", "invalid"]):
        true_positive = confusion[label][label]
        expected_positive = sum(confusion[label].values())
        predicted_positive = sum(confusion[row][label] for row in status_labels)
        return {
            "precision": true_positive / predicted_positive if predicted_positive else 0.0,
            "recall": true_positive / expected_positive if expected_positive else 0.0,
        }

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
            "status_exact_match": status_matches / len(records),
            "status_confusion_matrix": confusion,
            "clarification_metrics": binary_status_metrics("needs_clarification"),
            "invalid_request_metrics": binary_status_metrics("invalid"),
            "examples": examples,
        }
    )
    return metrics


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--task", choices=("extraction", "profiles"), default="extraction")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL"))
    parser.add_argument("--model-digest", help="Immutable Ollama model digest when available")
    parser.add_argument(
        "--base-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if not args.model and not args.validate_only:
        parser.error("provide --model or set OLLAMA_MODEL")

    try:
        dataset_path = args.dataset
        if args.task == "profiles" and dataset_path == DEFAULT_DATASET:
            dataset_path = DATA_DIRECTORY / "request_profiles_v1.jsonl"
        records = (
            load_profile_dataset(dataset_path)
            if args.task == "profiles"
            else load_dataset(dataset_path)
        )
        if args.validate_only:
            print(json.dumps({"dataset": str(dataset_path), "examples": len(records)}))
            return 0
        extractor = OllamaStructuredRequestExtractor(
            model=args.model,
            base_url=args.base_url,
            timeout_seconds=args.timeout,
            temperature=args.temperature,
            seed=args.seed,
        )
        result = asyncio.run(evaluate(records, extractor))
        if args.task == "profiles":
            result["metrics"] = {
                key: result[key]
                for key in (
                    "profile_count_exact_match",
                    "profile_traveller_counts_exact_match",
                    "profile_constraints_exact_match",
                    "profile_exact_match",
                )
            }
        result["run"] = create_run_metadata(
            f"request_{args.task}",
            dataset_path,
            {
                "provider": extractor.provider_name,
                "model": extractor.model,
                "model_digest": args.model_digest,
                "prompt_version": EXTRACTION_PROMPT_VERSION,
                "schema_transport": SCHEMA_TRANSPORT_VERSION,
                "inference_parameters": extractor.inference_parameters,
                "timeout_seconds": extractor.timeout_seconds,
            },
        )
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
