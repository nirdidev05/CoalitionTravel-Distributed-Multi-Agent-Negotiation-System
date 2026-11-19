"""Lightweight local experiment metadata; no tracking service or secrets are used."""

import hashlib
import json
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(dataset_path: Path) -> dict:
    manifest_path = dataset_path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        return {"version": "unversioned", "manifest_path": None}
    with manifest_path.open(encoding="utf-8") as manifest_file:
        manifest = json.load(manifest_file)
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def git_revision(root: Path | None = None) -> dict:
    cwd = root or Path.cwd()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "working_tree_dirty": None}
    return {"commit": commit, "working_tree_dirty": dirty}


def create_run_metadata(
    task: str,
    dataset_path: Path,
    configuration: dict,
    *,
    corpus_path: Path | None = None,
) -> dict:
    manifest = load_manifest(dataset_path)
    run = {
        "run_id": str(uuid.uuid4()),
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "task": task,
        "code": git_revision(_find_repository_root(dataset_path)),
        "dataset": {
            "path": str(dataset_path),
            "version": manifest.get("version", "unversioned"),
            "sha256": sha256_file(dataset_path),
            "manifest": manifest,
        },
        "configuration": configuration,
        "status": "completed",
    }
    if corpus_path is not None:
        corpus_manifest = load_manifest(corpus_path)
        run["corpus"] = {
            "path": str(corpus_path),
            "version": corpus_manifest.get("version", "unversioned"),
            "sha256": sha256_file(corpus_path),
            "manifest": corpus_manifest,
        }
    return run


def _find_repository_root(path: Path) -> Path:
    for parent in path.resolve().parents:
        if (parent / ".git").exists():
            return parent
    return Path.cwd()
