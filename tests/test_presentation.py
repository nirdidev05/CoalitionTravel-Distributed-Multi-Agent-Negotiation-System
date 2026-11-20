"""I3-B: French messages, text and JSON renderers, vocabulary rule and status documents.

T-CONF-1 to T-CONF-3 are repeated here on the JSON and on the text (scope review §9.1);
T-LEX covers the renderers (the command is covered in tests/test_plan_trip_cli.py);
T-STATUS covers the closed schema of trip-request-status-v1, keys and values.
"""

import json
import re
import unicodedata
from dataclasses import replace
from datetime import date
from fractions import Fraction
from pathlib import Path

import pytest
from coalition_travel.application.coalition_candidates import FormationLimits
from coalition_travel.application.request_contracts import TravelRequestDraft
from coalition_travel.application.request_understanding import validate_request_draft
from coalition_travel.application.trip_planning import (
    DemandPoolSnapshot,
    PlanningInput,
    PlanningRequest,
    RequestRejection,
    plan_lot,
)
from coalition_travel.application.trip_proposal import (
    SIMULATION_NOTICE,
    Explanation,
    ProjectionActiveParams,
    contract_field_names,
)
from coalition_travel.infrastructure.demand.demand_pool import load_demand_pool
from coalition_travel.infrastructure.negotiation.market import open_simulated_market
from coalition_travel.infrastructure.presentation.explanations_fr import (
    euros,
    euros_exact,
    explanation_message,
    forbidden_term_message,
    needs_clarification_message,
    unknown_place_message,
)
from coalition_travel.infrastructure.presentation.json_renderer import (
    PresentationError,
    StatusDocumentError,
    canonical_json,
    error_path,
    forbidden_term_error,
    invalid_document,
    needs_clarification_document,
    not_validated_document,
    reduce_validation_error,
    render_proposal_json,
    render_status_json,
    request_rejected_document,
    validate_status_document,
)
from coalition_travel.infrastructure.presentation.text_renderer import (
    render_proposal_text,
    render_request_summary,
    render_status_text,
)
from coalition_travel.infrastructure.presentation.vocabulary import (
    FORBIDDEN_WORDS,
    contains_forbidden_word,
    forbidden_user_fields,
    forbidden_words_in,
)
from p4_support import REFERENCE
from pydantic import ValidationError
from test_trip_proposal import (
    E3_DRAFT,
    EXPECTED_EXCLUSIONS,
    HEX64,
    b8_values,
    b_private_values,
    draft,
    marked_pool,
    other_private_data,
    plan_for,
    private_digests,
    proposal_of,
    public_source_values,
    single,
    variant,
)

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data/catalog/catalog_v1.json"
POOL_PATH = ROOT / "data/demand/demand_pool_v1.jsonl"
AMOUNT = re.compile(r"\d{1,3}(?: \d{3})*,\d{2} €")
PROFILES_CAP = [
    {"profile_id": "p1", "traveller_count": 1, "budget_per_person": "300"},
    {"profile_id": "p2", "traveller_count": 3, "budget_per_person": "700"},
]


@pytest.fixture(scope="module")
def pool():
    return load_demand_pool(POOL_PATH)


@pytest.fixture(scope="module")
def scenarios(pool):
    """One real proposal per reachable code, keyed by a short name."""
    empty = DemandPoolSnapshot(pool.version, pool.sha256, pool.catalog_version, ())
    built = {
        "e3": single(E3_DRAFT, pool)[1],
        "social": single(draft("Tokyo", 2, "500"), pool)[1],
        "rome": single(draft("Rome", 3, "450"), pool)[1],
        "singleton": single(draft("Tokyo", 2, "500"), empty)[1],
        "alger": single(draft("Alger", 2, "500"), pool)[1],
        "poor": single(draft("Tokyo", 1, "100"), pool)[1],
        "too_large": single(draft("Tokyo", 1, "520"), pool, FormationLimits(max_component_units=4))[
            1
        ],
        "direct": single(
            draft("Tokyo", 1, "700", direct_flight="preferred", excluded_suppliers=["Northstar"]),
            pool,
        )[1],
        "cap": single(draft("Tokyo", 4, "600", profiles=PROFILES_CAP), pool)[1],
    }
    drafts = {"user": draft("Rome", 20, "400"), "user-2": draft("Rome", 20, "400")}
    built["h2"] = proposal_of(plan_for(drafts, pool), "user", drafts["user"])
    return built


def explanation(proposal, code):
    return next(item for item in proposal.explanations if item.code == code)


def json_keys(node, found=None):
    found = set() if found is None else found
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(key)
            json_keys(value, found)
    elif isinstance(node, list):
        for value in node:
            json_keys(value, found)
    return found


def json_leaves(node, path="$"):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from json_leaves(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from json_leaves(value, f"{path}[{index}]")
    else:
        yield path, node


def json_numbers(text):
    """Integers, and the value of every "p/q" string, of a JSON document."""
    values = set()
    for _, leaf in json_leaves(json.loads(text)):
        if isinstance(leaf, bool):
            continue
        if isinstance(leaf, int) or (isinstance(leaf, str) and re.fullmatch(r"-?\d+/\d+", leaf)):
            values.add(Fraction(leaf))
    return values


def text_amounts(text):
    return set(AMOUNT.findall(text))


# --- T-LEX: the vocabulary rule, both faces (§7.2) -------------------------------------------


def test_every_forbidden_word_is_refused_in_any_case_and_normal_form():
    assert len(FORBIDDEN_WORDS) == 13
    for word in FORBIDDEN_WORDS:
        for form in (word, word.upper(), word.capitalize()):
            for normal in ("NFC", "NFD"):
                text = f"Un mot : {unicodedata.normalize(normal, form)}, dans une phrase."
                assert contains_forbidden_word(text), (word, form, normal)
    assert forbidden_words_in("Aucun billet n'est émis.") == ("billet", "émis")


def test_words_that_only_contain_a_forbidden_word_pass():
    notice = render_status_text(
        not_validated_document(source="draft-json", reference_date=REFERENCE, reason="refused")
    )
    for text in (
        SIMULATION_NOTICE,
        "réservation",
        "émission",
        "confirmation",
        "billetterie",
        "RÉSERVATION",
        notice,
    ):
        assert not contains_forbidden_word(text), text


def test_the_catalogue_strings_pass_the_vocabulary_rule():
    def strings(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from strings(value)
        elif isinstance(node, list):
            for value in node:
                yield from strings(value)
        elif isinstance(node, str):
            yield node

    document = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert not [text for text in strings(document) if contains_forbidden_word(text)]


def test_every_rendered_output_passes_the_vocabulary_rule(scenarios):
    for name, proposal in scenarios.items():
        for text in (render_proposal_text(proposal), render_proposal_json(proposal)):
            assert not forbidden_words_in(text), name


def test_user_strings_with_a_forbidden_word_are_located_by_path():
    item = draft(
        "Tokyo",
        2,
        "500",
        excluded_suppliers=["Ok Air", "Réservé Air"],
        profiles=[
            {"profile_id": "billets", "traveller_count": 1},
            {"profile_id": "b", "traveller_count": 1, "excluded_suppliers": ["Émis Lines"]},
        ],
    )
    assert forbidden_user_fields(item) == (
        "excluded_suppliers[1]",
        "profiles[0].profile_id",
        "profiles[1].excluded_suppliers[0]",
    )
    assert forbidden_user_fields(draft("Billet Ville", 1, "500")) == ("destination",)
    assert forbidden_user_fields(E3_DRAFT) == ()
    message = forbidden_term_message("profiles[0].profile_id")
    assert "profiles[0].profile_id" in message and not contains_forbidden_word(message)


def test_a_renderer_refuses_a_text_with_a_forbidden_word(scenarios):
    proposal = scenarios["e3"]
    poisoned = replace(proposal, simulation=replace(proposal.simulation, notice="Billet émis."))
    with pytest.raises(PresentationError):
        render_proposal_text(poisoned)
    with pytest.raises(PresentationError):
        render_proposal_json(poisoned)


# --- messages: one test per code (§10.2) -----------------------------------------------------

LOADED_WORDS = re.compile(
    r"\b(meilleur|meilleure|meilleurs|meilleures|optimal|optimale|avantageux)\b"
)


def check_message(item):
    message = explanation_message(item)
    assert message == explanation_message(item)  # deterministic
    assert message and not contains_forbidden_word(message)
    return message


def test_served_in_coalition_message(scenarios):
    message = check_message(explanation(scenarios["e3"], "served_in_coalition"))
    assert "3 autres demandes" in message and "39,00 €" in message


def test_alone_no_beneficial_coalition_messages(scenarios):
    message = check_message(explanation(scenarios["singleton"], "alone_no_beneficial_coalition"))
    assert "aucune coalition n'a été évaluée" in message
    assert "toutes les coalitions possibles" not in message
    params = explanation(scenarios["singleton"], "alone_no_beneficial_coalition").params
    counted = Explanation(
        "alone_no_beneficial_coalition",
        "status",
        replace(
            params,
            component_units=3,
            singleton_component=False,
            evaluated=3,
            without_agreement=1,
            without_saving=2,
        ),
    )
    message = check_message(counted)
    assert "3 coalitions évaluées par P4" in message
    assert "1 n'ont abouti à aucun accord et 2 n'ont dégagé aucune économie" in message


def test_alone_social_optimum_message_never_says_alone_is_better(scenarios):
    for name in ("social", "rome"):
        message = check_message(explanation(scenarios[name], "alone_social_optimum"))
        assert not LOADED_WORDS.search(message.casefold())
        assert "maximise la valeur totale du groupe" in message
        assert "ne signifie pas qu'une coalition aurait été défavorable" in message
    social = check_message(explanation(scenarios["social"], "alone_social_optimum"))
    assert "même valeur totale" in social and "règle de départage" in social
    assert "écart 18,00 €" in social


def test_unallocated_status_messages(scenarios):
    assert "3 offres ont été écartées" in check_message(
        explanation(scenarios["alger"], "no_admissible_offer")
    )
    assert "2 négociations sans accord" in check_message(
        explanation(scenarios["poor"], "no_solo_reference")
    )
    assert "5 demandes" in check_message(explanation(scenarios["too_large"], "component_too_large"))
    assert "rom-cloudwing-20270405" in check_message(
        explanation(scenarios["h2"], "capacity_model_violated")
    )


def test_modifier_messages(scenarios):
    assert "p1" in check_message(explanation(scenarios["cap"], "budget_cap_active"))
    forced = Explanation(
        "projection_active", "modifier", ProjectionActiveParams(True, Fraction(-201, 2))
    )
    message = check_message(forced)
    assert "valeur exacte : -201/2 centimes" in message and "atteint une borne" in message


def test_offer_messages(scenarios):
    rejected = check_message(explanation(scenarios["e3"], "offer_rejected"))
    assert rejected.startswith("Offre rom-cloudwing-20270405 écartée : la destination")
    direct = check_message(explanation(scenarios["direct"], "direct_preference_not_met"))
    assert "tyo-skyways-20270312" in direct and "Aucune offre directe admissible" in direct


def test_request_level_messages():
    message = needs_clarification_message(("destination", "budget_per_person"))
    assert message == (
        "Il manque des informations pour traiter la demande : la destination, "
        "le budget par personne."
    )
    assert not contains_forbidden_word(unknown_place_message())


def test_amount_formatting():
    assert euros(380_100) == "3 801,00 €"
    assert euros(5) == "0,05 €" and euros(-100) == "-1,00 €"
    assert euros(100_000_000_000) == "1 000 000 000,00 €"
    assert euros_exact(Fraction(3_900)) == "39,00 €"
    assert euros_exact(Fraction(1, 3)) == "≈ 0,00 € (valeur exacte : 1/3 centimes)"
    with pytest.raises(TypeError):
        euros(1.5)


# --- JSON renderer (§7.1, §9.2) ---------------------------------------------------------------


def test_json_is_canonical_and_identical_byte_for_byte(pool, scenarios):
    text = render_proposal_json(scenarios["e3"])
    assert text.endswith("}\n")
    data = json.loads(text)
    assert canonical_json(data) == text
    assert json.dumps(data, sort_keys=True, ensure_ascii=False, indent=2) + "\n" == text
    assert "é" in text and "\\u00e9" not in text  # ensure_ascii=False
    again = single(E3_DRAFT, pool)[1]
    assert render_proposal_json(again) == text


def test_json_types_and_units(scenarios):
    data = json.loads(render_proposal_json(scenarios["e3"]))
    assert data["schema"] == "trip-proposal-v1"
    assert data["simulation"] == {
        "booking": False,
        "notice": scenarios["e3"].simulation.notice,
        "simulated_sellers": True,
        "synthetic_catalog": True,
    }
    assert data["allocation"]["phi_cents"] == "3900/1"
    assert data["allocation"]["payment_cents"] == 380_100
    assert data["provenance"]["reference_date"] == "2026-11-19"
    assert data["offers"][1]["departure_date"] == "2027-03-10"
    assert data["request"]["draft"]["budget_per_person"] == "500"
    for item in data["explanations"]:
        assert set(item) == {"code", "level", "params", "message"}
    assert data["block"]["negotiation"]["leader_initial_total_cents"] is None


def test_json_renderer_accepts_a_proposal_only(scenarios):
    with pytest.raises(TypeError):
        render_proposal_json(scenarios["e3"].block)
    with pytest.raises(TypeError):
        render_proposal_text(json.loads(render_proposal_json(scenarios["e3"])))


def test_t_conf_3_json_keys_are_closed(scenarios):
    draft_keys = set(TravelRequestDraft.model_fields) | {
        "profile_id",
        "traveller_count",
    }
    allowed = set(contract_field_names()) | {"message"} | draft_keys
    for name, proposal in scenarios.items():
        data = json.loads(render_proposal_json(proposal))
        keys = json_keys(data)
        assert keys <= allowed, (name, keys - allowed)
        forbidden = ("floor", "seller_terms", "request_key", "sha256", "run_id", "configuration")
        assert not [k for k in keys if any(fragment in k for fragment in forbidden)]
        budget_keys = {k for k in keys if "budget" in k}
        # the person's own fields, and the keys of the person's validated draft (§4.3)
        assert budget_keys <= {"budget_total_cents", "budget_cents", "budget_per_person"}


# --- text renderer (§9.1) --------------------------------------------------------------------


def test_text_shows_the_nine_elements_and_the_notice(scenarios):
    text = render_proposal_text(scenarios["e3"])
    assert text.startswith(scenarios["e3"].simulation.notice + "\nDate de référence : 2026-11-19\n")
    for fragment in (
        "== Offres du catalogue ==",  # (1)
        "- autre demande 3 : 1 place(s), paiement 510,00 €",  # (2)
        "== Négociations individuelles (simulation) ==",  # (3)
        "Offre commune : tyo-northstar-20270310",  # (4)
        "Prix catalogue : 5 280,00 €",  # (5)
        "Prix négocié (simulation) : 5 280,00 €",
        "Valeur créée (économie collective) : 90,00 €",  # (6)
        "Contribution à la valeur créée (Shapley) : 39,00 €",
        "Paiement de votre demande : 3 801,00 €",
        "- profil all, place 1 : 475,13 € (budget 500,00 €)",  # (7)
        "écartée : la destination de l'offre ne correspond pas à la demande",  # (8)
        "== Provenance ==",
    ):
        assert fragment in text, fragment
    assert "montant non publié" in text
    social = render_proposal_text(scenarios["social"])
    assert "Statut : demande traitée seule" in social and "même valeur totale" in social  # (9)


def test_text_is_identical_byte_for_byte(pool, scenarios):
    again = single(E3_DRAFT, pool)[1]
    assert render_proposal_text(again) == render_proposal_text(scenarios["e3"])


def test_request_summary_uses_validated_fields_only():
    summary = render_request_summary(draft("Tokyo", 4, "600", profiles=PROFILES_CAP))
    assert summary.startswith("Demande comprise :\n- destination : Tokyo\n")
    assert "- profil p1 : 1 voyageur(s), budget 300,00 €" in summary
    assert "ville de départ : non prise en compte dans cette version" in summary
    assert "budget par personne : 0,001 €" in render_request_summary(draft("Tokyo", 1, "0.001"))


# --- T-CONF on the JSON and the text (§9.1) ---------------------------------------------------


@pytest.fixture(scope="module")
def conf(pool):
    plans = {
        name: plan_for({"user": E3_DRAFT}, variant(pool, budget))
        for name, budget in (("A", "520.00"), ("B", "521.37"))
    }
    proposals = {name: proposal_of(plan, "user", E3_DRAFT) for name, plan in plans.items()}
    outputs = {
        name: (render_proposal_json(p), render_proposal_text(p)) for name, p in proposals.items()
    }
    return plans, outputs


def test_t_conf_1_json_and_text_identical_byte_for_byte(conf):
    _, outputs = conf
    assert outputs["A"] == outputs["B"]


def test_t_conf_2b_no_digest_in_json_or_text(conf):
    plans, outputs = conf
    for name in ("A", "B"):
        for text in outputs[name]:
            assert not HEX64.search(text)
            assert not [d for d in private_digests(plans[name]) if d in text]


def test_t_conf_2c_no_private_value_of_b_in_json_or_text(conf):
    plans, outputs = conf
    private = b_private_values(plans["B"])
    json_text, text = outputs["B"]
    assert not {Fraction(v) for v in private.values()} & json_numbers(json_text)
    assert not {euros(v) for v in private.values()} & text_amounts(text)


def test_t_conf_2d_seller_messages_in_json(conf):
    _, outputs = conf
    messages = json.loads(outputs["B"][0])["block"]["negotiation"]["messages"]
    assert [m["total_cents"] for m in messages if m["actor"] == "seller"] == [528_000]


def test_t_conf_2e_no_value_of_the_other_members_in_json_or_text(pool):
    snapshot = marked_pool(pool)
    plan = plan_for({"user": E3_DRAFT}, snapshot)
    proposal = proposal_of(plan, "user", E3_DRAFT)
    json_text, text = render_proposal_json(proposal), render_proposal_text(proposal)
    public, b8 = public_source_values(plan), b8_values(plan)
    exclusions, leaks = set(), []
    numbers, amounts = json_numbers(json_text), text_amounts(text)
    folded = (json_text.casefold(), text.casefold())
    for (rid, kind), value in other_private_data(snapshot, plan).items():
        if isinstance(value, int | Fraction):
            exact = Fraction(value)
            if exact == 0:
                exclusions.add((rid, kind, 3))
            elif exact in b8.get(rid, set()):
                exclusions.add((rid, kind, 1))
            elif exact in public:
                exclusions.add((rid, kind, 2))
            elif exact in numbers or (exact.denominator == 1 and euros(exact.numerator) in amounts):
                leaks.append((rid, kind))
        else:
            needle = value.isoformat() if isinstance(value, date) else value
            if any(needle.casefold() in haystack for haystack in folded):
                leaks.append((rid, kind))
    assert exclusions == EXPECTED_EXCLUSIONS
    assert not leaks


# --- T-STATUS: closed status documents, keys and values (§6.4) -------------------------------


def rejection_of(item):
    market = open_simulated_market(CATALOG_PATH, REFERENCE)
    plan = plan_lot(PlanningInput((PlanningRequest("user", item),), None, REFERENCE), market)
    assert plan.status == "request_rejected"
    return plan.rejections[0]


def test_status_documents_positive_cases():
    common = {"source": "draft-json", "reference_date": REFERENCE}
    cases = [
        (needs_clarification_document(missing_fields=["budget_per_person"], rounds=0, **common), 2),
        (
            needs_clarification_document(
                source="replay",
                reference_date=REFERENCE,
                missing_fields=["destination", "budget_per_person"],
                rounds=3,
            ),
            2,
        ),
        (
            invalid_document(
                errors=["departure_after must not be before the reference date"], **common
            ),
            3,
        ),
        (
            invalid_document(
                errors=["profile groupe 1: arrival_before is before reference date"], **common
            ),
            3,
        ),
        (invalid_document(errors=["request text must not be blank"], **common), 3),
        (invalid_document(errors=["request text exceeds 12000 characters"], **common), 3),
        (
            invalid_document(
                errors=["$: json_invalid", "profiles[0].?: extra_forbidden"], **common
            ),
            3,
        ),
        (
            invalid_document(
                errors=[forbidden_term_error("profiles[1].excluded_suppliers[0]")], **common
            ),
            3,
        ),
        (not_validated_document(reason="refused", **common), 4),
        (not_validated_document(reason="empty_answer", **common), 4),
        (not_validated_document(reason="end_of_input", **common), 4),
    ]
    for document, code in cases:
        assert validate_status_document(document) == code, document
        text, rendered_code = render_status_json(document)
        assert rendered_code == code and json.loads(text) == document
        assert canonical_json(document) == text


def test_request_rejected_rows_from_the_real_planner():
    """The five rows of §6.4: three budget reasons, two request_not_ready rows."""
    rows = {
        "below": (draft("Tokyo", 1, "0.001"), "budget_below_one_cent", 3),
        "per_person": (draft("Tokyo", 1, "2000000000"), "budget_out_of_range", 3),
        "total": (draft("Tokyo", 20, "600000000"), "budget_total_out_of_range", 3),
        "missing": (TravelRequestDraft(destination="Tokyo", travellers=2), "request_not_ready", 2),
        "past": (draft("Tokyo", 2, "500", departure_after="2026-01-01"), "request_not_ready", 3),
    }
    for item, reason, code in rows.values():
        if reason.startswith("budget"):
            assert validate_request_draft(item, REFERENCE).status == "ready"
        rejection = rejection_of(item)
        document = request_rejected_document(
            source="draft-json", reference_date=REFERENCE, rejection=rejection
        )
        assert document["reason"] == reason
        assert validate_status_document(document) == code
        message = render_status_text(document)
        assert not contains_forbidden_word(message)


def test_status_documents_negative_cases():
    base = request_rejected_document(
        source="draft-json",
        reference_date=REFERENCE,
        rejection=RequestRejection("user", "budget_out_of_range", None, (), ()),
    )
    assert validate_status_document(base) == 3
    refused = [
        base | {"reason": "invalid_request_id"},
        base | {"reason": "unknown_reason"},
        base | {"missing_fields": ["destination"]},
        base | {"errors": ["departure_after must not be before the reference date"]},
        base | {"rejection_status": "invalid"},
        base | {"reason": "request_not_ready", "rejection_status": "other"},
        base | {"extra": 1},
        {key: value for key, value in base.items() if key != "errors"},
        base | {"errors": None},
        base | {"schema": "trip-request-status-v2"},
        base | {"source": "file"},
        base | {"reference_date": "19/11/2026"},
        invalid_document(source="llm", reference_date=REFERENCE, errors=["something went wrong"]),
        invalid_document(source="llm", reference_date=REFERENCE, errors=["travellers: 'x' is bad"]),
        invalid_document(source="llm", reference_date=REFERENCE, errors=["destinationz: missing"]),
        invalid_document(source="llm", reference_date=REFERENCE, errors=[]),
        needs_clarification_document(
            source="llm", reference_date=REFERENCE, missing_fields=["origin"], rounds=1
        ),
        needs_clarification_document(
            source="llm",
            reference_date=REFERENCE,
            missing_fields=["budget_per_person", "destination"],
            rounds=1,
        ),
        needs_clarification_document(
            source="llm", reference_date=REFERENCE, missing_fields=["destination"], rounds=4
        ),
        needs_clarification_document(
            source="draft-json", reference_date=REFERENCE, missing_fields=["destination"], rounds=1
        ),
        not_validated_document(source="llm", reference_date=REFERENCE, reason="timeout"),
    ]
    for document in refused:
        with pytest.raises(StatusDocumentError):
            validate_status_document(document)
        with pytest.raises(StatusDocumentError):
            render_status_json(document)


def test_pydantic_errors_are_reduced_without_the_received_values():
    payload = (
        '{"destination": "Tokyo", "travellers": "huit", "secret_key": "valeur privée", '
        '"profiles": [{"profile_id": "a", "traveller_count": 1, "other": 2}]}'
    )
    with pytest.raises(ValidationError) as caught:
        TravelRequestDraft.model_validate_json(payload)
    lines = reduce_validation_error(caught.value)
    assert set(lines) == {
        "travellers: int_type",
        "?: extra_forbidden",
        "profiles[0].?: extra_forbidden",
    }
    assert not [line for line in lines if "huit" in line or "secret" in line or "privée" in line]
    with pytest.raises(ValidationError) as malformed:
        TravelRequestDraft.model_validate_json("{")
    assert reduce_validation_error(malformed.value) == ("$: json_invalid",)
    assert error_path(()) == "$" and error_path(("profiles", 2, "budget_per_person")) == (
        "profiles[2].budget_per_person"
    )
    document = invalid_document(source="draft-json", reference_date=REFERENCE, errors=lines)
    assert validate_status_document(document) == 3


def test_status_text_names_the_field_without_quoting_the_value():
    document = invalid_document(
        source="draft-json",
        reference_date=REFERENCE,
        errors=[forbidden_term_error("profiles[0].profile_id")],
    )
    text = render_status_text(document)
    assert "Le champ profiles[0].profile_id contient un terme" in text
    assert not contains_forbidden_word(text)
    clarification = render_status_text(
        needs_clarification_document(
            source="replay", reference_date=REFERENCE, missing_fields=["travellers"], rounds=3
        )
    )
    assert "le nombre de voyageurs" in clarification
    assert "aucune simulation" in render_status_text(
        not_validated_document(source="llm", reference_date=REFERENCE, reason="end_of_input")
    )
