"""I4-C: route requests through plan_travel_request and the command (Lyon-Alger).

The v1 outputs of the command are compared byte for byte with the outputs produced by
the code of I3 (SHA-256 recorded at the I3 installation check, before any I4 change).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.request_understanding import validate_request_draft
from coalition_travel.application.travel_workflow import plan_travel_request
from coalition_travel.application.trip_planning import DemandPoolSnapshot, PlanningRequest
from coalition_travel.application.trip_proposal import (
    TRIP_PROPOSAL_SCHEMA_V2,
    ProposalConsistencyError,
    contract_field_names,
    draft_json_extraction,
)
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from coalition_travel.infrastructure.presentation.json_renderer import (
    STATUS_SCHEMA_V2,
    StatusDocumentError,
    render_proposal_json,
    unknown_place_document,
    validate_status_document,
)
from coalition_travel.infrastructure.presentation.text_renderer import render_proposal_text
from coalition_travel.infrastructure.presentation.vocabulary import forbidden_words_in
from p4_support import REFERENCE

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "Multi-Agent" / "plan_trip.py"
CATALOG_V2 = ROOT / "data/catalog/catalog_v2.json"
POOL_V2 = ROOT / "data/demand/demand_pool_v2.jsonl"
DATE = ["--reference-date", "2026-11-19"]
HEX64 = re.compile(r"[0-9a-f]{64}")
E3_FILE = '{"destination": "Tokyo", "travellers": 8, "budget_per_person": "500"}\n'
# Recorded with the code of I3 (report I3, §16.2), before any I4 change.
I3_E3_JSON_STDOUT = "8ea8538128440e92de89ca5ac48fb01a04d68637180018d86d4c30316d53ff5c"
I3_E3_JSON_STDERR = "0295fb1041659e6b55a532720dd84baf077e871ae13be6767874ed4c518a9b19"
I3_E3_TEXT_STDOUT = "b4e97acc8ee9f455cd86e88cace7a5ee65903838f35c1413f795546a5db59483"
I3_E3_TEXT_STDERR = "53f161857ea9fd235f9dc371c8962335a80319e74c8803bcc21c6d70b5117456"
LYON_ALGER = {
    "origin": "Lyon",
    "destination": "Alger",
    "trip_type": "round_trip",
    "travellers": 2,
    "budget_per_person": "500",
    "departure_after": "2027-02-15",
    "departure_before": "2027-02-15",
    "return_after": "2027-02-25",
    "return_before": "2027-02-25",
}


def environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith("OLLAMA_")}
    return env | {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}


def cli(tmp_path, *args, stdin=""):
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *map(str, args)],
        input=stdin.encode("utf-8"),
        capture_output=True,
        cwd=tmp_path,
        env=environment(),
        timeout=180,
        check=False,
    )


def write(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content if isinstance(content, str) else json.dumps(content), "utf-8")
    return path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def status(result):
    document = json.loads(result.stdout)
    assert validate_status_document(document) == result.returncode
    return document


# --- K1 on the outputs: v1 requests produce the bytes of I3 --------------------------------


def test_v1_outputs_of_the_command_are_the_bytes_of_i3(tmp_path):
    path = write(tmp_path, "e3.json", E3_FILE)
    as_json = cli(tmp_path, "--draft-json", path, *DATE, "--yes", "--json")
    assert as_json.returncode == 0
    assert sha(as_json.stdout) == I3_E3_JSON_STDOUT
    assert sha(as_json.stderr) == I3_E3_JSON_STDERR
    as_text = cli(tmp_path, "--draft-json", path, *DATE, stdin="o\n")
    assert as_text.returncode == 0
    assert sha(as_text.stdout) == I3_E3_TEXT_STDOUT
    assert sha(as_text.stderr) == I3_E3_TEXT_STDERR


def test_v1_status_documents_keep_the_v1_schema(tmp_path):
    path = write(tmp_path, "d.json", {"destination": "Tokyo", "travellers": 2})
    result = cli(tmp_path, "--draft-json", path, *DATE, "--json")
    assert status(result)["schema"] == "trip-request-status-v1"
    malformed = write(tmp_path, "m.json", {"destination": "Tokyo", "travellers": "deux"})
    assert status(cli(tmp_path, "--draft-json", malformed, *DATE, "--json"))["schema"] == (
        "trip-request-status-v1"
    )


# --- I4-A1: Lyon-Alger end to end ------------------------------------------------------------


@pytest.fixture(scope="module")
def lyon_alger(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("lyon_alger")
    path = write(tmp_path, "lyon_alger.json", LYON_ALGER | {"destination": "Algiers"})
    as_json = cli(tmp_path, "--draft-json", path, *DATE, "--yes", "--json")
    as_text = cli(tmp_path, "--draft-json", path, *DATE, stdin="o\n")
    assert as_json.returncode == 0 and as_text.returncode == 0, as_json.stderr
    return tmp_path, path, as_json, as_text


def test_lyon_alger_produces_a_complete_v2_proposal(lyon_alger):
    _, _, as_json, _ = lyon_alger
    data = json.loads(as_json.stdout)
    assert data["schema"] == TRIP_PROPOSAL_SCHEMA_V2
    assert data["request"]["draft"]["destination"] == "Alger"  # Algiers, resolved (D-I4-9)
    assert (data["unit"]["origin_key"], data["unit"]["trip_type"]) == ("lyon", "round_trip")
    provenance = data["provenance"]
    assert (provenance["catalog_version"], provenance["pool_version"]) == (
        "catalog-v2",
        "demand-pool-v2",
    )
    assert data["status"]["code"] in {
        "served_in_coalition",
        "alone_no_beneficial_coalition",
        "alone_social_optimum",
    }
    assert data["block"] is not None and data["allocation"] is not None
    offers = {offer["offer_id"]: offer for offer in data["offers"]}
    assert offers["lys-alg-vlt-20270215"]["return"] is None
    assert offers["lys-alg-brs-20270215"]["outbound"]["leg_ref"] == "BRS-311-20270215"
    reasons = {
        offer_id: [v["reason"] for v in offer["violations"]] for offer_id, offer in offers.items()
    }
    assert reasons == {
        "lys-alg-brs-20270215": [],
        "lys-alg-clq-20270215": [],
        "lys-alg-orv-20270215": ["return_after_window"],
        "lys-alg-vlt-20270215": ["trip_type_mismatch"],
        "mrs-alg-orv-20270215": ["origin_mismatch"],
    }


def test_lyon_alger_outputs_are_closed_clean_and_deterministic(lyon_alger):
    tmp_path, path, as_json, as_text = lyon_alger
    data = json.loads(as_json.stdout)
    draft_keys = set(TravelRequestDraft.model_fields) | {"profile_id", "traveller_count"}
    allowed = contract_field_names(TRIP_PROPOSAL_SCHEMA_V2) | {"message"} | draft_keys

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    assert set(keys(data)) <= allowed
    for text in (as_json.stdout, as_text.stdout, as_json.stderr, as_text.stderr):
        decoded = text.decode("utf-8")
        assert not HEX64.search(decoded) and not forbidden_words_in(decoded)
        assert str(tmp_path) not in decoded
    again = cli(tmp_path, "--draft-json", path, *DATE, "--yes", "--json")
    assert again.stdout == as_json.stdout
    summary = as_text.stderr.decode("utf-8")
    assert "- départ de : Lyon\n- destination : Alger\n- type de trajet : aller-retour" in summary
    assert "Algiers" not in summary
    assert "retour : départ 2027-02-25" in as_text.stdout.decode("utf-8")


def test_v2_contract_field_names_extend_v1():
    v1, v2 = contract_field_names(), contract_field_names(TRIP_PROPOSAL_SCHEMA_V2)
    assert len(v1) == 107
    assert v2 - v1 == {"origin_key", "trip_type", "origin", "outbound", "return", "leg_ref"}


# --- unknown places (D-I4-9) ----------------------------------------------------------------


def test_an_unknown_place_by_draft_json_is_exit_2(tmp_path):
    path = write(tmp_path, "oran.json", LYON_ALGER | {"destination": "Oran"})
    result = cli(tmp_path, "--draft-json", path, *DATE, "--json")
    assert result.returncode == 2
    document = status(result)
    assert document == {
        "fields": ["destination"],
        "known_places": ["Alger", "Lyon", "Marseille"],
        "reference_date": "2026-11-19",
        "schema": "trip-request-status-v2",
        "source": "draft-json",
        "status": "unknown_place",
    }
    assert "oran" not in (result.stdout + result.stderr).decode("utf-8").casefold()
    assert "Lieux disponibles : Alger, Lyon, Marseille." in result.stderr.decode("utf-8")


def test_an_unknown_place_is_clarified_then_resolved(tmp_path):
    replay = write(tmp_path, "r.json", [LYON_ALGER | {"destination": "Oran"}, LYON_ALGER])
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, stdin="voyage\nAlger\no\n")
    assert result.returncode == 0, result.stderr
    stderr = result.stderr.decode("utf-8")
    assert "Précision 1/3 : Lieu non reconnu pour la destination." in stderr
    assert "oran" not in stderr.casefold()


def test_end_of_input_on_an_unknown_place_is_exit_2(tmp_path):
    replay = write(tmp_path, "r.json", [LYON_ALGER | {"origin": "Paris"}])
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, "--json", stdin="voyage\n")
    assert result.returncode == 2
    assert status(result)["fields"] == ["origin"]


# --- route clarification and status documents v2 ------------------------------------------


def test_route_fields_are_asked_one_round_at_a_time(tmp_path):
    missing = {key: value for key, value in LYON_ALGER.items() if key != "travellers"}
    replay = write(tmp_path, "r.json", [missing, LYON_ALGER])
    result = cli(tmp_path, "--extractor-replay", replay, *DATE, stdin="voyage\ndeux\no\n")
    assert result.returncode == 0
    assert "Précision 1/3 : Combien de personnes voyagent ?" in result.stderr.decode("utf-8")


def test_v2_status_documents_by_the_command(tmp_path):
    cases = {
        "missing": ({"origin": "Lyon", "destination": "Alger", "travellers": 2}, 2),
        "empty window": (LYON_ALGER | {"departure_after": "2027-02-16"}, 3),
        "malformed": (LYON_ALGER | {"travellers": "deux"}, 3),
        "budget": (LYON_ALGER | {"budget_per_person": "0.001"}, 3),
        "forbidden": (LYON_ALGER | {"origin": "Billet Ville"}, 3),
    }
    documents = {}
    for name, (draft, code) in cases.items():
        result = cli(
            tmp_path, "--draft-json", write(tmp_path, "d.json", draft), *DATE, "--yes", "--json"
        )
        assert result.returncode == code, name
        documents[name] = status(result)
        assert documents[name]["schema"] == STATUS_SCHEMA_V2, name
    assert documents["missing"]["missing_fields"] == [
        "budget_per_person",
        "trip_type",
        "departure_after",
        "departure_before",
    ]
    assert documents["empty window"]["errors"] == [
        "departure_after must not be after departure_before"
    ]
    assert documents["malformed"]["errors"] == ["travellers: int_type"]
    assert (documents["budget"]["status"], documents["budget"]["reason"]) == (
        "request_rejected",
        "budget_below_one_cent",
    )
    assert documents["forbidden"]["errors"] == ["forbidden_term: origin"]
    refused = cli(
        tmp_path,
        "--draft-json",
        write(tmp_path, "d.json", LYON_ALGER),
        *DATE,
        "--json",
        stdin="non\n",
    )
    assert refused.returncode == 4 and status(refused)["schema"] == STATUS_SCHEMA_V2


def test_v2_status_validator_negative_cases():
    base = unknown_place_document(
        source="draft-json",
        reference_date=REFERENCE,
        fields=["origin", "destination"],
        known_places=["Alger", "Lyon", "Marseille"],
    )
    assert validate_status_document(base) == 2
    refused = [
        base | {"fields": ["destination", "origin"]},
        base | {"fields": []},
        base | {"known_places": ["Lyon", "Alger"]},
        base | {"known_places": ["Alger", "Alger"]},
        base | {"extra": 1},
        base | {"schema": "trip-request-status-v1"},  # unknown_place is v2 only
        base | {"status": ["unknown_place"]},  # unhashable, refused cleanly
        {
            "schema": STATUS_SCHEMA_V2,
            "status": "invalid",
            "source": "llm",
            "reference_date": "2026-11-19",
            "errors": ["the return window is empty"],  # a profile form without its prefix
        },
        {
            "schema": STATUS_SCHEMA_V2,
            "status": "needs_clarification",
            "source": "llm",
            "reference_date": "2026-11-19",
            "missing_fields": ["trip_type", "origin"],
            "rounds": 1,
        },
    ]
    for document in refused:
        with pytest.raises(StatusDocumentError):
            validate_status_document(document)


# --- plan_travel_request on a route request, and T-CONF in v2 -------------------------------


def variant(pool, budget, request_id="pool-lys-alg-01"):
    requests = tuple(
        PlanningRequest(
            item.request_id,
            TravelRequestDraft.model_validate(
                item.draft.model_dump(mode="json") | {"budget_per_person": budget}
            ),
        )
        if item.request_id == request_id
        else item
        for item in pool.requests
    )
    digest = hashlib.sha256(budget.encode()).hexdigest()
    return DemandPoolSnapshot(pool.version, digest, pool.catalog_version, requests)


def plan_v2(pool):
    draft = TravelRequestDraft.model_validate(LYON_ALGER)
    return plan_travel_request(
        draft,
        market=open_simulated_market(CATALOG_V2, REFERENCE),
        pool=pool,
        reference_date=REFERENCE,
        extraction=draft_json_extraction(),
    )


def test_t_conf_1_in_v2_a_member_budget_does_not_reach_the_outputs():
    pool = load_demand_pool(POOL_V2)
    a, b = plan_v2(variant(pool, "340.00")), plan_v2(variant(pool, "340.37"))
    block = next(x for x in a.plan.formation.blocks if "user" in x.unit_ids)
    assert "pool-lys-alg-01" in block.unit_ids  # otherwise the test would prove nothing
    assert a.proposal == b.proposal
    assert render_proposal_json(a.proposal) == render_proposal_json(b.proposal)
    assert render_proposal_text(a.proposal) == render_proposal_text(b.proposal)
    assert a.plan.pool_sha256 != b.plan.pool_sha256
    assert a.plan.allocation.allocation_sha256 != b.plan.allocation.allocation_sha256


def test_a_v1_proposal_never_carries_route_fields():
    result = plan_v2(load_demand_pool(POOL_V2))
    proposal = result.proposal
    with pytest.raises(ProposalConsistencyError):
        replace(proposal, schema="trip-proposal-v1")
    assert proposal.schema == TRIP_PROPOSAL_SCHEMA_V2


# --- extraction dataset v3 and prompt v2 -----------------------------------------------------


def test_the_v3_dataset_is_valid_offline_and_labels_match_the_validation():
    dataset = ROOT / "data/eval/request_extraction_v3.jsonl"
    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "Multi-Agent/evaluate_requests.py"),
            "--validate-only",
            "--dataset",
            str(dataset),
        ],
        capture_output=True,
        text=True,
        env=environment(),
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["examples"] == 8
    for line in dataset.read_text("utf-8").splitlines():
        record = json.loads(line)
        draft = TravelRequestDraft.model_validate(record["expected"])
        result = validate_request_draft(draft, date.fromisoformat(record["reference_date"]))
        assert result.status == record["expected_status"], record["id"]
    manifest = json.loads(
        (ROOT / "data/eval/request_extraction_v3.manifest.json").read_text("utf-8")
    )
    assert manifest["records"] == 8


def test_the_prompt_is_versioned_v2():
    from coalition_travel.infrastructure.llm.ollama import EXTRACTION_PROMPT_VERSION

    assert EXTRACTION_PROMPT_VERSION == "travel-request-extraction-v2"
