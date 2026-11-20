"""I3-C: plan_travel_request and the command coalition-travel-plan (scope review §6, §9).

Most scenarios run the command in a subprocess (specification §10.4, I3-A11); the
interruption test sends a real SIGINT (T-SIGINT). The counters of I3-A13 are checked at
function level, through ``plan_trip.run`` with a counting market.
"""

import hashlib
import io
import json
import os
import select
import signal
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import plan_trip
import pytest
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.travel_workflow import (
    TravelPlanningResult,
    plan_travel_request,
)
from coalition_travel.application.trip_proposal import (
    build_trip_proposal,
    draft_json_extraction,
    replay_extraction,
)
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.llm.replay import ReplayStructuredRequestExtractor
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from coalition_travel.infrastructure.presentation.json_renderer import (
    canonical_json,
    validate_status_document,
)
from coalition_travel.infrastructure.presentation.vocabulary import forbidden_words_in
from p4_support import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Multi-Agent" / "plan_trip.py"
CATALOG_PATH = ROOT / "data/catalog/catalog_v1.json"
POOL_PATH = ROOT / "data/demand/demand_pool_v1.jsonl"
DATE = ["--reference-date", "2026-11-19"]
E3 = {"destination": "Tokyo", "travellers": 8, "budget_per_person": "500"}
MISSING_BUDGET = {"destination": "Tokyo", "travellers": 8}
REQUEST_QUESTION = "Décrivez votre demande de voyage"
VALIDATION_QUESTION = "Valider cette demande et lancer la simulation ? [o/N]"
POSIX = os.name == "posix"


def environment(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("OLLAMA_")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.update(extra)
    return env


def cli(tmp_path, *args, stdin="", env=None):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=tmp_path,
        env=env or environment(),
        timeout=180,
        check=False,
    )


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content), "utf-8")
    return path


def check_clean(result):
    """No forbidden word and no traceback in any output of the command (T-LEX)."""
    for text in (result.stdout, result.stderr):
        assert not forbidden_words_in(text)
    assert "Traceback" not in result.stderr


@pytest.fixture(scope="module")
def e3_json(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("e3")
    path = write(tmp_path, "e3.json", E3)
    result = cli(tmp_path, "--draft-json", path, *DATE, "--yes", "--json")
    assert result.returncode == 0, result.stderr
    return result


# --- plan_travel_request (§6.1) --------------------------------------------------------------


def test_plan_travel_request_returns_the_plan_and_its_proposal():
    pool = load_demand_pool(POOL_PATH)
    draft = TravelRequestDraft(**E3)
    market = open_simulated_market(CATALOG_PATH, REFERENCE)
    result = plan_travel_request(
        draft, market=market, pool=pool, reference_date=REFERENCE, extraction=replay_extraction()
    )
    assert result.plan.status == "planned"
    assert result.proposal == build_trip_proposal(
        result.plan, request_id="user", draft=draft, extraction=replay_extraction()
    )
    assert result.proposal.allocation.payment_cents == 380_100


def test_plan_travel_request_rejected_has_no_proposal():
    pool = load_demand_pool(POOL_PATH)
    market = open_simulated_market(CATALOG_PATH, REFERENCE)
    result = plan_travel_request(
        TravelRequestDraft(destination="Tokyo", travellers=2),
        market=market,
        pool=pool,
        reference_date=REFERENCE,
        extraction=draft_json_extraction(),
    )
    assert result.proposal is None and result.plan.status == "request_rejected"
    rejection = result.plan.rejections[0]
    assert (rejection.reason, rejection.status) == ("request_not_ready", "needs_clarification")
    with pytest.raises(ValueError):
        TravelPlanningResult(result.plan, object())


# --- I3-A11: scenarios by subprocess -----------------------------------------------------------


def test_draft_json_end_to_end_e3(e3_json):
    data = json.loads(e3_json.stdout)
    assert e3_json.stdout == canonical_json(data)  # one JSON document and nothing else
    assert data["status"]["code"] == "served_in_coalition"
    assert data["allocation"]["payment_cents"] == 380_100
    assert sorted(t["amount_cents"] for t in data["travellers"]) == [47_512] * 4 + [47_513] * 4
    assert [m["label"] for m in data["block"]["members"]] == [
        "vous",
        "autre demande 1",
        "autre demande 2",
        "autre demande 3",
    ]
    assert data["provenance"]["extraction"] == {
        "model": None,
        "provider": None,
        "source": "draft-json",
    }
    assert data["provenance"]["reference_date"] == "2026-11-19"
    assert "Demande comprise :" in e3_json.stderr and VALIDATION_QUESTION not in e3_json.stderr
    check_clean(e3_json)


def test_output_is_identical_byte_for_byte_across_runs(tmp_path, e3_json):
    path = write(tmp_path, "e3.json", E3)
    again = cli(tmp_path, "--draft-json", path, *DATE, "--yes", "--json")
    assert again.stdout == e3_json.stdout
    text_1 = cli(tmp_path, "--draft-json", path, *DATE, "--yes")
    text_2 = cli(tmp_path, "--draft-json", path, *DATE, "--yes")
    assert text_1.returncode == 0 and text_1.stdout == text_2.stdout
    assert text_1.stdout.startswith("Proposition simulée : catalogue et vendeurs fictifs.")
    check_clean(text_1)


@pytest.mark.parametrize("answer", ["o\n", "oui\n", "  OUI  \n"])
def test_validation_accepted(tmp_path, answer):
    path = write(tmp_path, "e3.json", E3)
    result = cli(tmp_path, "--draft-json", path, *DATE, stdin=answer)
    assert result.returncode == 0
    assert VALIDATION_QUESTION in result.stderr
    assert "Paiement de votre demande : 3 801,00 €" in result.stdout


@pytest.mark.parametrize(
    ("answer", "reason"),
    [("non\n", "refused"), ("y\n", "refused"), ("\n", "empty_answer"), ("", "end_of_input")],
)
def test_validation_not_given_is_exit_4(tmp_path, answer, reason):
    path = write(tmp_path, "e3.json", E3)
    text = cli(tmp_path, "--draft-json", path, *DATE, stdin=answer)
    assert (text.returncode, text.stdout) == (4, "")
    assert "aucune simulation n'a été lancée" in text.stderr
    result = cli(tmp_path, "--draft-json", path, *DATE, "--json", stdin=answer)
    document = json.loads(result.stdout)
    assert result.returncode == validate_status_document(document) == 4
    assert document["reason"] == reason
    check_clean(result)


def test_prompt_with_the_replay_extractor(tmp_path, e3_json):
    replay = write(tmp_path, "r1.json", [E3])
    result = cli(
        tmp_path,
        "--prompt",
        "Tokyo pour huit",
        "--extractor-replay",
        replay,
        *DATE,
        "--yes",
        "--json",
    )
    assert result.returncode == 0, result.stderr
    data, reference = json.loads(result.stdout), json.loads(e3_json.stdout)
    assert data["provenance"].pop("extraction") == {
        "model": "replay-v1",
        "provider": "replay",
        "source": "replay",
    }
    reference["provenance"].pop("extraction")
    assert data == reference


def test_interactive_input(tmp_path):
    replay = write(tmp_path, "r1.json", [E3])
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, stdin="Tokyo pour huit\no\n")
    assert result.returncode == 0, result.stderr
    assert REQUEST_QUESTION in result.stderr
    assert "Tokyo pour huit" not in result.stdout + result.stderr  # never copied (B9)


def test_clarification_with_scripted_input(tmp_path):
    replay = write(tmp_path, "r.json", [MISSING_BUDGET, E3])
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, stdin="Tokyo\n500 euros\no\n")
    assert result.returncode == 0, result.stderr
    assert result.stderr.count("Précision 1/3 : Quel est le budget par personne, en euros ?") == 1


def test_three_rounds_at_most_and_a_fourth_answer_is_never_read(tmp_path):
    """I3-A12: a fifth, complete draft would be used if a fourth round took place."""
    replay = write(tmp_path, "r.json", [MISSING_BUDGET] * 4 + [E3])
    answers = "Tokyo\n" + "".join(f"réponse {k}\n" for k in range(1, 5)) + "o\n"
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, "--json", stdin=answers)
    assert result.returncode == 2
    document = json.loads(result.stdout)
    assert (document["rounds"], document["missing_fields"]) == (3, ["budget_per_person"])
    assert result.stderr.count("Précision ") == 3
    assert validate_status_document(document) == 2


def test_end_of_input_during_clarification_is_exit_2(tmp_path):
    replay = write(tmp_path, "r.json", [MISSING_BUDGET, E3])
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, "--json", stdin="Tokyo\n")
    assert result.returncode == 2
    assert json.loads(result.stdout)["rounds"] == 0


def test_reference_date_changes_admissibility_and_is_shown(tmp_path):
    path = write(tmp_path, "e3.json", E3)
    later = cli(tmp_path, "--draft-json", path, "--reference-date", "2027-03-11", "--yes", "--json")
    assert later.returncode == 0, later.stderr
    data = json.loads(later.stdout)
    assert data["provenance"]["reference_date"] == "2027-03-11"
    northstar = next(o for o in data["offers"] if o["offer_id"] == "tyo-northstar-20270310")
    assert [v["reason"] for v in northstar["violations"]] == ["offer_departs_before_reference_date"]
    today = cli(tmp_path, "--draft-json", path, "--yes", "--json")
    stamp = (
        json.loads(today.stdout)["provenance"]["reference_date"] if today.returncode == 0 else None
    )
    assert today.returncode in (0, 3) and (stamp is None or stamp == date.today().isoformat())


# --- exit codes (§6.3) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("draft", "reason"),
    [
        (
            {"destination": "Tokyo", "travellers": 1, "budget_per_person": "0.001"},
            "budget_below_one_cent",
        ),
        (
            {"destination": "Tokyo", "travellers": 1, "budget_per_person": "2000000000"},
            "budget_out_of_range",
        ),
        (
            {"destination": "Tokyo", "travellers": 20, "budget_per_person": "600000000"},
            "budget_total_out_of_range",
        ),
    ],
)
def test_request_rejected_reasons_reachable_by_draft_json(tmp_path, draft, reason):
    path = write(tmp_path, "d.json", draft)
    result = cli(tmp_path, "--draft-json", path, *DATE, "--yes", "--json")
    document = json.loads(result.stdout)
    assert result.returncode == validate_status_document(document) == 3
    assert (document["status"], document["reason"]) == ("request_rejected", reason)
    assert "Demande non retenue." in result.stderr
    check_clean(result)


def test_invalid_requests_are_exit_3(tmp_path):
    cases = {
        "pydantic": ({"destination": "Tokyo", "travellers": "huit"}, ["travellers: int_type"]),
        "malformed": ("{", ["$: json_invalid"]),
        "past": (
            dict(E3, departure_after="2026-01-01"),
            ["departure_after must not be before the reference date"],
        ),
    }
    for name, (draft, errors) in cases.items():
        path = write(tmp_path, f"{name}.json", draft)
        result = cli(tmp_path, "--draft-json", path, *DATE, "--yes", "--json")
        document = json.loads(result.stdout)
        assert result.returncode == 3 and document["errors"] == errors, name
        assert "huit" not in result.stdout + result.stderr


def test_needs_clarification_by_draft_json_is_exit_2(tmp_path):
    path = write(tmp_path, "d.json", MISSING_BUDGET)
    result = cli(tmp_path, "--draft-json", path, *DATE, "--json")
    assert result.returncode == 2
    assert json.loads(result.stdout) == {
        "missing_fields": ["budget_per_person"],
        "reference_date": "2026-11-19",
        "rounds": 0,
        "schema": "trip-request-status-v1",
        "source": "draft-json",
        "status": "needs_clarification",
    }
    assert VALIDATION_QUESTION not in result.stderr


def test_a_blank_interactive_request_is_exit_3(tmp_path):
    replay = write(tmp_path, "r1.json", [E3])
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, "--json", stdin="\n")
    assert result.returncode == 3
    assert json.loads(result.stdout)["errors"] == ["request text must not be blank"]


@pytest.mark.parametrize(
    "args",
    [
        ["--unknown-option"],
        ["--prompt", "x", "--draft-json", "d.json"],
        ["--reference-date", "19/11/2026"],
        ["--reference-date", "2026-02-30"],
        ["--draft-json", "absent.json"],
        ["--draft-json", "d.json", "--extractor-replay", "d.json"],
        ["--prompt", "voyage"],  # no OLLAMA_MODEL and no replay
        ["--draft-json"],
    ],
)
def test_incorrect_usage_is_exit_64(tmp_path, args):
    write(tmp_path, "d.json", E3)
    result = cli(tmp_path, *args)
    assert (result.returncode, result.stdout) == (64, "")
    assert result.stderr.startswith("Usage incorrect : ")
    assert "Traceback" not in result.stderr


def test_technical_errors_are_exit_1(tmp_path):
    empty = write(tmp_path, "r0.json", [])
    exhausted = cli(tmp_path, "--prompt", "voyage", "--extractor-replay", empty, *DATE, "--json")
    assert (exhausted.returncode, exhausted.stdout) == (1, "")
    assert "ExtractorContractError" in exhausted.stderr
    unreachable = cli(
        tmp_path,
        "--prompt",
        "voyage",
        *DATE,
        env=environment(OLLAMA_MODEL="modele-local", OLLAMA_BASE_URL="http://127.0.0.1:9"),
    )
    assert (unreachable.returncode, unreachable.stdout) == (1, "")
    assert unreachable.stderr.startswith("Erreur technique : ")


# --- T-REPLAY (§9.1) -------------------------------------------------------------------------------


def test_t_replay_provenance_does_not_depend_on_the_file(tmp_path):
    other = {"destination": "Tokyo", "travellers": 1, "budget_per_person": "777.77"}
    r1 = write(tmp_path, "r1.json", [E3])
    r2 = write(tmp_path, "r2.json", [E3, other])
    outputs = {}
    for name, path in (("r1", r1), ("r2", r2)):
        for mode in ("--json", None):
            args = ["--prompt", "voyage", "--extractor-replay", path, *DATE, "--yes"]
            result = cli(tmp_path, *(args + ([mode] if mode else [])))
            assert result.returncode == 0, result.stderr
            outputs[(name, mode)] = result
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            for text in (result.stdout, result.stderr):
                assert digest not in text and str(path) not in text and str(tmp_path) not in text
    assert outputs[("r1", "--json")].stdout == outputs[("r2", "--json")].stdout
    assert outputs[("r1", None)].stdout == outputs[("r2", None)].stdout
    extraction = json.loads(outputs[("r1", "--json")].stdout)["provenance"]["extraction"]
    assert extraction == {"model": "replay-v1", "provider": "replay", "source": "replay"}


def test_t_replay_errors_never_show_the_path_or_the_content(tmp_path):
    marked = tmp_path / "zq-chemin-prive"
    marked.mkdir()
    empty = write(marked, "r0.json", [])
    result = cli(tmp_path, "--prompt", "voyage", "--extractor-replay", empty, *DATE)
    assert result.returncode == 1
    assert "zq-chemin-prive" not in result.stderr and str(tmp_path) not in result.stderr
    absent = cli(tmp_path, "--draft-json", marked / "absent.json", *DATE)
    assert absent.returncode == 64
    assert "Fichier de --draft-json introuvable ou illisible." in absent.stderr
    assert "zq-chemin-prive" not in absent.stderr


def unreadable_cases(marked: Path):
    cases = [("directory", marked / "dossier.json")]
    cases[0][1].mkdir()
    if POSIX and os.geteuid() != 0:
        locked = write(marked, "verrou.json", [E3])
        locked.chmod(0)
        cases.append(("no read permission", locked))
    return cases


def test_t_replay_an_unreadable_file_is_a_usage_error(tmp_path):
    marked = tmp_path / "zq-chemin-prive"
    marked.mkdir()
    cases = unreadable_cases(marked)
    try:
        for name, path in cases:
            result = cli(tmp_path, "--extractor-replay", path, *DATE, stdin="Tokyo\no\n")
            assert (result.returncode, result.stdout) == (64, ""), name
            assert "Fichier de --extractor-replay introuvable ou illisible." in result.stderr
            assert REQUEST_QUESTION not in result.stderr  # before any question
            for fragment in ("zq-chemin-prive", str(tmp_path), "Permission denied", "Errno"):
                assert fragment not in result.stderr, (name, fragment)
    finally:
        for _, path in cases:
            if path.is_file():
                path.chmod(0o600)
    if not (POSIX and os.geteuid() != 0):
        pytest.skip("the permission case needs a POSIX system and a non-root user")


# --- T-SIGINT (§9.1) -------------------------------------------------------------------------------


def interrupt_at(tmp_path, args, marker):
    process = subprocess.Popen(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=tmp_path,
        env=environment(),
    )
    seen = b""
    deadline = time.monotonic() + 120
    while marker.encode("utf-8") not in seen:
        assert time.monotonic() < deadline, seen.decode("utf-8", "replace")
        ready, _, _ = select.select([process.stderr], [], [], 1.0)
        if ready:
            chunk = os.read(process.stderr.fileno(), 4096)
            assert chunk, seen.decode("utf-8", "replace")
            seen += chunk
    process.send_signal(signal.SIGINT)
    stdout, stderr = process.communicate(timeout=60)
    return process.returncode, stdout, (seen + stderr).decode("utf-8")


@pytest.mark.skipif(not POSIX, reason="SIGINT is not delivered this way on Windows")
def test_t_sigint_at_the_validation_question(tmp_path):
    path = write(tmp_path, "e3.json", E3)
    code, stdout, stderr = interrupt_at(
        tmp_path, ["--draft-json", path, *DATE], VALIDATION_QUESTION
    )
    assert (code, stdout) == (130, b"")
    assert "Traceback" not in stderr and "Interruption" in stderr


@pytest.mark.skipif(not POSIX, reason="SIGINT is not delivered this way on Windows")
def test_t_sigint_during_interactive_input(tmp_path):
    replay = write(tmp_path, "r1.json", [E3])
    code, stdout, stderr = interrupt_at(
        tmp_path, ["--extractor-replay", replay, *DATE, "--json"], REQUEST_QUESTION
    )
    assert (code, stdout) == (130, b"")
    assert "Traceback" not in stderr


# --- T-LEX on the command (§9.1) -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("draft", "path", "word"),
    [
        (dict(E3, destination="Ville Billet"), "destination", "billet"),
        (
            dict(E3, profiles=[{"profile_id": "billets", "traveller_count": 8}]),
            "profiles[0].profile_id",
            "billets",
        ),
        (dict(E3, excluded_suppliers=["Réservé Air"]), "excluded_suppliers[0]", "réservé"),
    ],
)
def test_t_lex_a_forbidden_word_in_a_user_string_is_exit_3(tmp_path, draft, path, word):
    file = write(tmp_path, "d.json", draft)
    result = cli(tmp_path, "--draft-json", file, *DATE, "--json")
    document = json.loads(result.stdout)
    assert result.returncode == 3
    assert document["errors"] == [f"forbidden_term: {path}"]
    assert f"Le champ {path} contient un terme" in result.stderr
    assert word not in (result.stdout + result.stderr).casefold()
    assert VALIDATION_QUESTION not in result.stderr
    check_clean(result)


def test_t_lex_a_forbidden_word_from_the_extractor_is_refused_before_any_question(tmp_path):
    replay = write(tmp_path, "r.json", [{"destination": "Billet Ville", "travellers": 2}])
    result = cli(tmp_path, "--prompt", "voyage", "--extractor-replay", replay, *DATE)
    assert result.returncode == 3
    assert "Précision" not in result.stderr and "billet" not in result.stderr.casefold()


# --- I3-A13: nothing is negotiated before the validation (function level) ----------------------


class CountingMarket:
    def __init__(self, market):
        self.market, self.sessions = market, []

    def __getattr__(self, name):
        return getattr(self.market, name)

    def open_session(self):
        session = self.market.open_session()
        self.sessions.append(session)
        return session


class InterruptingInput(io.StringIO):
    def readline(self, *args):
        raise KeyboardInterrupt


def run_counting(tmp_path, stdin, *args):
    path = write(tmp_path, "e3.json", E3)
    markets = []

    def open_market(catalog, reference_date):
        markets.append(CountingMarket(open_simulated_market(catalog, reference_date)))
        return markets[-1]

    stdout, stderr = io.StringIO(), io.StringIO()
    code = plan_trip.run(
        ["--draft-json", str(path), *DATE, *args],
        stdin=stdin,
        stdout=stdout,
        stderr=stderr,
        environ={},
        open_market=open_market,
    )
    return code, markets[0], stdout.getvalue()


def test_no_negotiation_before_validation(tmp_path):
    code, market, stdout = run_counting(tmp_path, io.StringIO("non\n"))
    assert (code, market.sessions, stdout) == (4, [], "")
    code, market, stdout = run_counting(tmp_path, InterruptingInput())
    assert (code, market.sessions, stdout) == (130, [], "")
    code, market, _ = run_counting(tmp_path, io.StringIO("o\n"))
    assert code == 0 and len(market.sessions) == 1 and market.sessions[0].oracle_calls > 0


def test_the_replay_extractor_reads_its_file_once(tmp_path):
    path = write(tmp_path, "r.json", [E3, MISSING_BUDGET])
    extractor = ReplayStructuredRequestExtractor(path)
    path.unlink()
    assert extractor.size == 2 and (extractor.provider_name, extractor.model) == (
        "replay",
        "replay-v1",
    )
