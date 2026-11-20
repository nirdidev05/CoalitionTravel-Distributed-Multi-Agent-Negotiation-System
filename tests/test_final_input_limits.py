"""Bounded input files of the command (final mission, security review).

``--draft-json`` and ``--extractor-replay`` are read with a 1 000 000-byte limit: a
larger file, or a device that never ends, is a usage error (code 64) whose message never
quotes the path.
"""

import io
import os
from datetime import date

import plan_trip
import pytest
from coalition_travel.infrastructure.llm.replay import MAX_REPLAY_BYTES


def _run(*argv):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = plan_trip.run(
        list(argv),
        stdin=io.StringIO(""),
        stdout=stdout,
        stderr=stderr,
        environ={},
        today=lambda: date(2026, 11, 19),
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_the_limits_are_one_megabyte():
    assert plan_trip.MAX_INPUT_FILE_BYTES == MAX_REPLAY_BYTES == 1_000_000


def test_an_oversized_draft_is_a_usage_error_without_the_path(tmp_path):
    path = tmp_path / "secret-name-draft.json"
    path.write_bytes(b" " * plan_trip.MAX_INPUT_FILE_BYTES + b"{}")
    code, out, err = _run("--draft-json", str(path), "--yes", "--json")
    assert (code, out) == (plan_trip.EXIT_USAGE, "")
    assert "trop volumineux" in err and "secret-name" not in err and str(tmp_path) not in err


def test_a_draft_at_the_limit_is_read(tmp_path):
    draft = b'{"destination": "Tokyo", "travellers": 8, "budget_per_person": "500"}'
    path = tmp_path / "draft.json"
    path.write_bytes(draft + b" " * (plan_trip.MAX_INPUT_FILE_BYTES - len(draft)))
    code, _, err = _run("--draft-json", str(path), "--yes", "--json")
    assert code == plan_trip.EXIT_OK, err


@pytest.mark.skipif(not os.path.exists("/dev/zero"), reason="needs /dev/zero")
def test_an_endless_device_is_refused_without_reading_it_all():
    code, out, err = _run("--draft-json", "/dev/zero", "--yes")
    assert (code, out) == (plan_trip.EXIT_USAGE, "")
    assert "trop volumineux" in err and "/dev/zero" not in err


def test_an_oversized_replay_file_is_a_usage_error_without_the_path(tmp_path):
    path = tmp_path / "secret-name-replay.json"
    path.write_bytes(b"[" + b" " * MAX_REPLAY_BYTES + b"]")
    code, out, err = _run("--prompt", "voyage", "--extractor-replay", str(path), "--json")
    assert (code, out) == (plan_trip.EXIT_USAGE, "")
    assert "trop volumineux" in err and "secret-name" not in err


@pytest.mark.parametrize("value", ["abc", "0", "-5", "nan", "100000"])
def test_an_invalid_ollama_timeout_is_a_usage_error(value):
    stdout, stderr = io.StringIO(), io.StringIO()
    code = plan_trip.run(
        ["--prompt", "voyage", "--json"],
        stdin=io.StringIO(""),
        stdout=stdout,
        stderr=stderr,
        environ={"OLLAMA_MODEL": "modele-local", "OLLAMA_TIMEOUT_SECONDS": value},
        today=lambda: date(2026, 11, 19),
    )
    assert (code, stdout.getvalue()) == (plan_trip.EXIT_USAGE, "")
    assert "OLLAMA_TIMEOUT_SECONDS" in stderr.getvalue()


def test_the_default_ollama_timeout_fits_a_7b_model():
    assert plan_trip.DEFAULT_OLLAMA_TIMEOUT_SECONDS == 180.0
