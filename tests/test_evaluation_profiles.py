from datetime import date
from decimal import Decimal

from coalition_travel.application.evaluation import _normalize, score_extractions
from coalition_travel.application.request_contracts import (
    TravelerProfileDraft,
    TravelRequestDraft,
)


def _request(profiles):
    return TravelRequestDraft(
        destination="Tokyo",
        travellers=sum(profile.traveller_count for profile in profiles) or 1,
        budget_per_person=Decimal("800.00"),
        profiles=profiles,
    )


def _profile(profile_id, count=1, budget="500", direct="any"):
    return TravelerProfileDraft(
        profile_id=profile_id,
        traveller_count=count,
        budget_per_person=Decimal(budget),
        direct_flight=direct,
    )


def test_normalization_has_explicit_numeric_and_typed_null_policy():
    assert _normalize(500) == _normalize(500.0) == _normalize(Decimal("500.00"))
    assert _normalize(None) != _normalize("")
    assert _normalize(False) != _normalize(0)
    assert _normalize("required") != _normalize("preferred")
    assert _normalize(date(2027, 1, 1)) != _normalize("2027-01-01")
    assert _normalize(["a", {"value": Decimal("1.0")}]) == _normalize(["A", {"value": 1}])
    assert _normalize(_profile("one", budget="500")) == _normalize(_profile("one", budget="500.00"))


def test_single_profile_is_scored_and_profile_id_is_not_semantic():
    expected = _request([_profile("expected-id", count=2, budget="500")])
    actual = _request([_profile("different-id", count=2, budget="500.00")])

    metrics = score_extractions([expected], [actual])

    assert metrics["request_exact_match"] == 1.0
    assert metrics["profile_count_exact_match"] == 1.0
    assert metrics["profile_traveller_counts_exact_match"] == 1.0
    assert metrics["profile_constraints_exact_match"] == 1.0
    assert metrics["profile_exact_match"] == 1.0


def test_multiple_profiles_are_order_independent_and_keep_constraints_and_counts():
    expected = _request(
        [
            _profile("low", count=1, budget="400", direct="required"),
            _profile("high", count=2, budget="700", direct="preferred"),
        ]
    )
    actual = _request(
        [
            _profile("renamed-high", count=2, budget="700.0", direct="preferred"),
            _profile("renamed-low", count=1, budget="400.00", direct="required"),
        ]
    )

    metrics = score_extractions([expected], [actual])

    assert metrics["request_exact_match"] == 1.0
    assert metrics["field_exact_match"]["profiles"] == 1.0
    assert metrics["profile_count_exact_match"] == 1.0
    assert metrics["profile_traveller_counts_exact_match"] == 1.0
    assert metrics["profile_constraints_exact_match"] == 1.0
    assert metrics["profile_exact_match"] == 1.0


def test_effectif_and_constraint_changes_are_not_semantically_equal():
    expected = _request(
        [
            _profile("a", count=1, budget="400", direct="required"),
            _profile("b", count=2, budget="700", direct="preferred"),
        ]
    )
    changed_effectif = _request(
        [
            _profile("x", count=2, budget="400", direct="required"),
            _profile("y", count=1, budget="700", direct="preferred"),
        ]
    )
    changed_constraint = _request(
        [
            _profile("x", count=1, budget="400", direct="required"),
            _profile("y", count=2, budget="700", direct="any"),
        ]
    )

    effectif_metrics = score_extractions([expected], [changed_effectif])
    constraint_metrics = score_extractions([expected], [changed_constraint])

    assert effectif_metrics["profile_exact_match"] == 0.0
    assert effectif_metrics["profile_traveller_counts_exact_match"] == 1.0
    assert constraint_metrics["profile_constraints_exact_match"] == 0.0
    assert constraint_metrics["profile_exact_match"] == 0.0


def test_absent_profiles_match_empty_profiles():
    expected = TravelRequestDraft(destination="Rome", travellers=1, budget_per_person=400)
    actual = TravelRequestDraft(
        destination="Rome", travellers=1, budget_per_person=400, profiles=[]
    )

    metrics = score_extractions([expected], [actual])

    assert metrics["field_exact_match"]["profiles"] == 1.0
    assert metrics["profile_count_exact_match"] == 1.0
    assert metrics["profile_exact_match"] == 1.0


def test_batch_counts_failed_extractions_as_misses_for_profile_metrics():
    expected_with_profile = _request([_profile("a", count=1)])
    expected_without_profile = TravelRequestDraft(
        destination="Rome", travellers=1, budget_per_person=400
    )
    actual = _request([_profile("different-id", count=1)])

    metrics = score_extractions([expected_with_profile, expected_without_profile], [actual, None])

    assert metrics["samples"] == 2
    assert metrics["request_exact_match"] == 0.5
    assert metrics["field_exact_match"]["profiles"] == 0.5
    assert metrics["profile_count_exact_match"] == 0.5
    assert metrics["profile_exact_match"] == 0.5
