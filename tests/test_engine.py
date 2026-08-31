"""Tests for the deterministic risk-triage rubric in src/engine.py.

These assert against the documented rubric in src/engine.py's module
docstring (also mirrored in README.md), not against implementation details,
so they double as a spec check: if the rubric ever changes, these fixtures
and their expected tiers should be updated together with the docs.

The rubric buckets a summed risk_score into five tiers:
    0-2   -> minimal
    3-6   -> low
    7-10  -> moderate
    11-14 -> high
    15-19 -> restricted
"""

from __future__ import annotations

import json

import pytest

from src.engine import (
    assess,
    build_raci,
    get_required_controls,
    load_control_catalog,
    load_decision_log,
    log_decision,
    score_risk,
)
from src.models import RACI_ROLES, RISK_TIERS, IntakeRequest


def _make_request(**overrides) -> IntakeRequest:
    defaults = dict(
        use_case_name="Test use case",
        business_owner="Test Owner",
        data_sensitivity="public",
        intended_users="internal",
        automation_level="assistive",
        external_data_sharing=False,
        model_provider="Anthropic Claude",
        decision_impact="low",
        human_review_present=True,
        evaluation_method="Manual spot-check of a 10% sample weekly.",
    )
    defaults.update(overrides)
    return IntakeRequest(**defaults)


# --- Tier fixtures: one per each of the five tiers -------------------------

def test_minimal_risk_fixture_scores_minimal():
    request = _make_request()  # all-zero-point answers
    tier, score, factors = score_risk(request)
    assert tier == "minimal"
    assert score == 0
    assert "No elevated-risk factors" in factors[0]


def test_low_risk_fixture_scores_low():
    request = _make_request(
        data_sensitivity="internal",         # +1
        intended_users="internal",           # +0
        automation_level="semi_autonomous",  # +2
        decision_impact="low",               # +0
        human_review_present=True,           # +0
    )
    tier, score, factors = score_risk(request)
    assert score == 3
    assert tier == "low"
    assert len(factors) == 2  # internal data sensitivity, semi_autonomous


def test_moderate_risk_fixture_scores_moderate():
    request = _make_request(
        data_sensitivity="confidential",     # +2
        intended_users="both",               # +1
        automation_level="semi_autonomous",  # +2
        external_data_sharing=False,         # +0
        decision_impact="medium",            # +2
        human_review_present=True,           # +0
    )
    tier, score, factors = score_risk(request)
    assert score == 7
    assert tier == "moderate"
    assert len(factors) == 4  # confidential, both, semi_autonomous, medium decision impact


def test_high_risk_fixture_scores_high():
    request = _make_request(
        data_sensitivity="restricted",         # +4
        intended_users="external",             # +2
        automation_level="fully_autonomous",   # +4
        decision_impact="medium",              # +2
        human_review_present=True,             # +0
        external_data_sharing=False,           # +0
    )
    tier, score, factors = score_risk(request)
    assert score == 12
    assert tier == "high"


def test_restricted_risk_fixture_scores_restricted():
    request = _make_request(
        data_sensitivity="restricted",         # +4
        intended_users="external",             # +2
        automation_level="fully_autonomous",   # +4
        decision_impact="high",                # +4
        human_review_present=False,            # +3
        external_data_sharing=False,           # +0
    )
    tier, score, factors = score_risk(request)
    assert score == 17
    assert tier == "restricted"
    assert any("No human review" in f for f in factors)


# --- Threshold boundaries ----------------------------------------------------
# Guards against off-by-one errors at each of the four tier boundaries.

def test_minimal_low_boundary_is_contiguous():
    just_below_low = _make_request(
        data_sensitivity="internal",   # +1
        automation_level="assistive",  # +0
        decision_impact="low",         # +0
    )
    tier, score, _ = score_risk(just_below_low)
    assert score == 1
    assert tier == "minimal"

    at_low = _make_request(
        data_sensitivity="internal",         # +1
        automation_level="semi_autonomous",  # +2
        decision_impact="low",               # +0
    )
    tier, score, _ = score_risk(at_low)
    assert score == 3
    assert tier == "low"


def test_low_moderate_boundary_is_contiguous():
    just_below_moderate = _make_request(
        data_sensitivity="confidential",     # +2
        intended_users="internal",           # +0
        automation_level="semi_autonomous",  # +2
        decision_impact="low",               # +0
    )
    tier, score, _ = score_risk(just_below_moderate)
    assert score == 4
    assert tier == "low"

    at_moderate = _make_request(
        data_sensitivity="confidential",     # +2
        intended_users="both",               # +1
        automation_level="semi_autonomous",  # +2
        decision_impact="medium",            # +2
    )
    tier, score, _ = score_risk(at_moderate)
    assert score == 7
    assert tier == "moderate"


def test_moderate_high_boundary_is_contiguous():
    just_below_high = _make_request(
        data_sensitivity="restricted",       # +4
        intended_users="both",               # +1
        automation_level="assistive",        # +0
        decision_impact="medium",            # +2
        human_review_present=False,          # +3
    )
    tier, score, _ = score_risk(just_below_high)
    assert score == 10
    assert tier == "moderate"

    at_high = _make_request(
        data_sensitivity="restricted",        # +4
        intended_users="internal",            # +0
        automation_level="fully_autonomous",  # +4
        decision_impact="low",                # +0
        human_review_present=False,           # +3
    )
    tier, score, _ = score_risk(at_high)
    assert score == 11
    assert tier == "high"


def test_high_restricted_boundary_is_contiguous():
    just_below_restricted = _make_request(
        data_sensitivity="restricted",        # +4
        intended_users="both",                # +1
        automation_level="fully_autonomous",  # +4
        decision_impact="medium",             # +2
        human_review_present=False,           # +3
    )
    tier, score, _ = score_risk(just_below_restricted)
    assert score == 14
    assert tier == "high"

    at_restricted = _make_request(
        data_sensitivity="restricted",        # +4
        intended_users="internal",            # +0
        automation_level="fully_autonomous",  # +4
        decision_impact="high",               # +4
        human_review_present=False,           # +3
    )
    tier, score, _ = score_risk(at_restricted)
    assert score == 15
    assert tier == "restricted"


# --- Control catalog filtering ---------------------------------------------

def test_external_data_sharing_always_pulls_in_dpa_control_regardless_of_tier():
    minimal_request = _make_request(external_data_sharing=True)
    minimal_assessment = assess(minimal_request)
    assert minimal_assessment.risk_tier == "minimal"
    assert "UC-03" in minimal_assessment.required_control_ids

    restricted_request = _make_request(
        data_sensitivity="restricted",
        intended_users="external",
        automation_level="fully_autonomous",
        decision_impact="high",
        human_review_present=False,
        external_data_sharing=True,
    )
    restricted_assessment = assess(restricted_request)
    assert restricted_assessment.risk_tier == "restricted"
    assert "UC-03" in restricted_assessment.required_control_ids


def test_no_external_data_sharing_excludes_dpa_control():
    request = _make_request(external_data_sharing=False)
    assessment = assess(request)
    assert "UC-03" not in assessment.required_control_ids


def test_required_controls_count_increases_monotonically_across_tiers():
    tier_requests = {
        "minimal": _make_request(),
        "low": _make_request(
            data_sensitivity="internal", automation_level="semi_autonomous"
        ),
        "moderate": _make_request(
            data_sensitivity="confidential",
            intended_users="both",
            automation_level="semi_autonomous",
            decision_impact="medium",
        ),
        "high": _make_request(
            data_sensitivity="restricted",
            intended_users="external",
            automation_level="fully_autonomous",
            decision_impact="medium",
        ),
        "restricted": _make_request(
            data_sensitivity="restricted",
            intended_users="external",
            automation_level="fully_autonomous",
            decision_impact="high",
            human_review_present=False,
        ),
    }
    counts = {}
    for tier_name, request in tier_requests.items():
        assessment = assess(request)
        assert assessment.risk_tier == tier_name
        counts[tier_name] = len(assessment.required_control_ids)

    ordered = [counts[t] for t in RISK_TIERS]
    assert ordered == sorted(ordered)
    # Non-decreasing overall; minimal and low both require only the one
    # baseline control (no extra controls key off "low" specifically in the
    # catalog), then moderate/high/restricted each strictly add more --
    # restricted always adds UC-14 and UC-15 on top of everything high
    # already requires.
    assert counts["minimal"] <= counts["low"] < counts["moderate"] < counts["high"] < counts["restricted"]


@pytest.mark.parametrize(
    "risk_tier,expected_present,expected_absent",
    [
        ("minimal", {"UC-01"}, {"UC-02", "UC-05", "UC-14", "UC-15"}),
        ("low", {"UC-01"}, {"UC-02", "UC-05", "UC-14", "UC-15"}),
        ("moderate", {"UC-01", "UC-02", "UC-04", "UC-06", "UC-07", "UC-10", "UC-11", "UC-13"}, {"UC-05", "UC-08", "UC-09", "UC-12", "UC-14", "UC-15"}),
        ("high", {"UC-01", "UC-02", "UC-05", "UC-08", "UC-09", "UC-12"}, {"UC-14", "UC-15"}),
        ("restricted", {"UC-01", "UC-05", "UC-08", "UC-09", "UC-14", "UC-15"}, set()),
    ],
)
def test_control_catalog_filtering_at_each_tier(risk_tier, expected_present, expected_absent):
    catalog = load_control_catalog()
    ids, _names = get_required_controls(risk_tier, external_data_sharing=False, catalog=catalog)
    id_set = set(ids)
    assert expected_present.issubset(id_set)
    assert id_set.isdisjoint(expected_absent)


def test_get_required_controls_with_unknown_tier_only_matches_external_sharing():
    ids, names = get_required_controls("not_a_real_tier", external_data_sharing=False)
    assert ids == []
    assert names == []

    ids, names = get_required_controls("not_a_real_tier", external_data_sharing=True)
    assert ids == ["UC-03"]


# --- RACI ---------------------------------------------------------

@pytest.mark.parametrize(
    "risk_tier,expected",
    [
        ("minimal", {"Business Owner": "A", "Data Privacy": "I", "Security": "I", "Legal": "I", "IT": "R", "End Users": "I"}),
        ("low", {"Business Owner": "A", "Data Privacy": "C", "Security": "I", "Legal": "I", "IT": "R", "End Users": "I"}),
        ("moderate", {"Business Owner": "A", "Data Privacy": "C", "Security": "C", "Legal": "C", "IT": "R", "End Users": "I"}),
        ("high", {"Business Owner": "A", "Data Privacy": "C", "Security": "A", "Legal": "A", "IT": "R", "End Users": "I"}),
        ("restricted", {"Business Owner": "A", "Data Privacy": "A", "Security": "A", "Legal": "A", "IT": "R", "End Users": "C"}),
    ],
)
def test_raci_at_each_tier(risk_tier, expected):
    raci = build_raci(risk_tier)
    assert raci == expected
    assert set(raci.keys()) == set(RACI_ROLES)


def test_raci_restricted_tier_is_the_most_conservative():
    """Restricted pending formal review must never be less conservative
    (fewer Accountable sign-offs) than any other tier."""
    accountable_counts = {
        tier: sum(1 for v in build_raci(tier).values() if v == "A") for tier in RISK_TIERS
    }
    assert accountable_counts["restricted"] == max(accountable_counts.values())
    assert accountable_counts["restricted"] == 4  # Business Owner, Data Privacy, Security, Legal
    # End Users move off "Informed" only at the restricted tier.
    for tier in ("minimal", "low", "moderate", "high"):
        assert build_raci(tier)["End Users"] == "I"
    assert build_raci("restricted")["End Users"] == "C"


# --- Decision log accumulation ---------------------------------------------

def test_decision_log_accumulates_entries(tmp_path):
    log_path = tmp_path / "decision_log.json"

    request_one = _make_request(use_case_name="First use case")
    assessment_one = assess(request_one)
    log_decision(request_one, assessment_one, path=str(log_path))

    entries_after_one = load_decision_log(str(log_path))
    assert len(entries_after_one) == 1
    assert entries_after_one[0]["use_case_name"] == "First use case"
    assert entries_after_one[0]["risk_tier"] == assessment_one.risk_tier
    assert "timestamp" in entries_after_one[0]

    request_two = _make_request(use_case_name="Second use case", data_sensitivity="restricted")
    assessment_two = assess(request_two)
    log_decision(request_two, assessment_two, path=str(log_path))

    entries_after_two = load_decision_log(str(log_path))
    assert len(entries_after_two) == 2
    assert entries_after_two[0]["use_case_name"] == "First use case"
    assert entries_after_two[1]["use_case_name"] == "Second use case"

    # File on disk should be valid JSON matching what load_decision_log returned.
    with open(log_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    assert raw == entries_after_two


def test_decision_log_missing_file_returns_empty_list(tmp_path):
    missing_path = tmp_path / "does_not_exist.json"
    assert load_decision_log(str(missing_path)) == []
