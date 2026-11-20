"""Aggregate the LLM matrix: one row per (model, prompt, dataset) and per case_type.

Usage: python -I llm_aggregate.py RUN_DIR REPO_DIR [RUN_DIR_2]
With a second run directory, also reports per-example output reproducibility.
"""

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

run_dir, repo = Path(sys.argv[1]), Path(sys.argv[2])
second = Path(sys.argv[3]) if len(sys.argv) > 3 else None


def case_types(dataset):
    path = repo / "data/eval" / f"{dataset}.jsonl"
    types = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            types[record["id"]] = record.get("case_type", "-")
    return types


def pct(value):
    return None if value is None else round(100 * value, 1)


rows, breakdown, reproducibility = [], defaultdict(lambda: [0, 0, 0]), []
for path in sorted(run_dir.glob("*.json")):
    model, prompt, dataset = path.stem.split("__")
    prompt = prompt.replace("prompt_", "")
    doc = json.loads(path.read_text(encoding="utf-8"))
    examples = doc["examples"]
    latencies = [e["latency_ms"] for e in examples]
    row = {
        "model": doc["run"]["configuration"]["model"],
        "prompt": prompt,
        "dataset": dataset,
        "n": len(examples),
        "request_exact_match": pct(doc.get("request_exact_match")),
        "status_exact_match": pct(doc.get("status_exact_match")),
        "clarification_precision": pct(doc.get("clarification_metrics", {}).get("precision")),
        "clarification_recall": pct(doc.get("clarification_metrics", {}).get("recall")),
        "invalid_precision": pct(doc.get("invalid_request_metrics", {}).get("precision")),
        "invalid_recall": pct(doc.get("invalid_request_metrics", {}).get("recall")),
        "profile_exact_match": pct(doc.get("profile_exact_match")),
        "profile_count_exact_match": pct(doc.get("profile_count_exact_match")),
        "traveller_count_exact_match": pct(doc.get("field_exact_match", {}).get("travellers")),
        "failed_calls": doc.get("failed_calls"),
        "errors": sorted({e["error"] for e in doc.get("errors", [])}),
        "p50_latency_ms": round(statistics.median(latencies)),
        "mean_latency_ms": round(statistics.fmean(latencies)),
        "field_exact_match": {k: pct(v) for k, v in doc.get("field_exact_match", {}).items()},
        "digest": doc["run"]["configuration"].get("model_digest"),
        "prompt_version": doc["run"]["configuration"].get("prompt_version"),
    }
    rows.append(row)
    types = case_types(dataset)
    for e in examples:
        key = (row["model"], prompt, dataset, types.get(e["id"], "-"))
        breakdown[key][0] += 1
        breakdown[key][1] += e["actual"] == e["expected"]
        breakdown[key][2] += e["actual_status"] == e["expected_status"]
    if second is not None and (second / path.name).exists():
        other = json.loads((second / path.name).read_text(encoding="utf-8"))["examples"]
        same = sum(a["actual"] == b["actual"] for a, b in zip(examples, other))
        reproducibility.append((row["model"], prompt, dataset, same, len(examples)))

print(json.dumps({"rows": rows}, indent=1, ensure_ascii=False))
print("\n# breakdown: model | prompt | dataset | case_type | n | request EM | status EM")
for key, (n, em, st) in sorted(breakdown.items()):
    print(" | ".join(map(str, key)), "|", n, "|", em, "|", st)
if reproducibility:
    print("\n# reproducibility: identical extracted drafts between the two passes")
    for item in reproducibility:
        print(" | ".join(map(str, item)))
