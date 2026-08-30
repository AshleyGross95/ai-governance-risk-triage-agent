"""Tests for the deterministic risk-triage rubric in src/engine.py.

These assert against the documented rubric in src/engine.py's module
docstring (also mirrored in README.md), not against implementation details,
so they double as a spec check: if the rubric ever changes, these fixtures
and their expected tiers should be updated together with the docs.
"""

from __future__ import annotations

import json

from src.engine import assess, load_decision_log, log_decision, score_risk
from src.models import IntakeRequest


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


# --- Tier fixtures ---------------------------------------------------------

def test_low_risk_fixture_scores_low():
    request = _make_request(
        data_sensitivity="public",
        intended_users="internal",
        automation_level="assistive",
        external_data_sharing=False,
        decision_impact="low",
        human_review_present=True,
    )
    tier, score, factors = score_risk(request)
    assert tier == "low"
    assert score == 0
    assert "No elevated-risk factors" in factors[0]


def test_medium_risk_fixture_scores_medium():
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
    assert tier == "medium"
    assert len(factors) == 4  # confidential, both, semi_autonomous, medium decision impact


def test_high_risk_fixture_scores_high():
    request = _make_request(
        data_sensitivity="restricted",         # +4
        intended_users="external",             # +2
        automation_level="fully_autonomous",   # +4
        external_data_sharing=False,           # +0 (kept separate from tier test below)
        decision_impact="high",                # +4
        human_review_present=False,            # +3
    )
    tier, score, factors = score_risk(request)
    assert score == 17
    assert tier == "high"
    assert any("No human review" in f for f in factors)


def test_tier_thresholds_are_contiguous_and_ordered():
    # Guards against an off-by-one in the threshold comparison: one point
    # below LOW_MEDIUM_THRESHOLD (5) must be low, and exactly at it must be
    # medium.
    just_below_medium = _make_request(
        data_sensitivity="confidential",     # +2
        intended_users="internal",           # +0
        automation_level="semi_autonomous",  # +2
        decision_impact="low",               # +0
    )
    tier, score, _ = score_risk(just_below_medium)
    assert score == 4
    assert tier == "low"

    exactly_medium = _make_request(
        data_sensitivity="confidential",     # +2
        intended_users="both",               # +1
        automation_level="semi_autonomous",  # +2
        decision_impact="low",               # +0
    )
    tier, score, _ = score_risk(exactly_medium)
    assert score == 5
    assert tier == "medium"


# --- Control catalog filtering ---------------------------------------------

def test_external_data_sharing_always_pulls_in_dpa_control_regardless_of_tier():
    low_request = _make_request(external_data_sharing=True)
    low_assessment = assess(low_request)
    assert low_assessment.risk_tier == "low"
    assert "UC-03" in low_assessment.required_control_ids

    high_request = _make_request(
        data_sensitivity="restricted",
        intended_users="external",
        automation_level="fully_autonomous",
        decision_impact="high",
        human_review_present=False,
        external_data_sharing=True,
    )
    high_assessment = assess(high_request)
    assert high_assessment.risk_tier == "high"
    assert "UC-03" in high_assessment.required_control_ids


def test_no_external_data_sharing_excludes_dpa_control():
    request = _make_request(external_data_sharing=False)
    assessment = assess(request)
    assert "UC-03" not in assessment.required_control_ids


def test_high_tier_requires_strictly_more_controls_than_low_tier():
    low_assessment = assess(_make_request())
    high_assessment = assess(
        _make_request(
            data_sensitivity="restricted",
            intended_users="external",
            automation_level="fully_autonomous",
            decision_impact="high",
            human_review_present=False,
        )
    )
    assert len(high_assessment.required_control_ids) > len(low_assessment.required_control_ids)


# --- RACI ---------------------------------------------------------

def test_high_tier_raci_escalates_security_and_legal_to_accountable():
    high_assessment = assess(
        _make_request(
            data_sensitivity="restricted",
            intended_users="external",
            automation_level="fully_autonomous",
            decision_impact="high",
            human_review_present=False,
        )
    )
    assert high_assessment.raci["Security"] == "A"
    assert high_assessment.raci["Legal"] == "A"

    medium_assessment = assess(
        _make_request(
            data_sensitivity="confidential",
            intended_users="both",
            automation_level="semi_autonomous",
            decision_impact="medium",
        )
    )
    assert medium_assessment.raci["Security"] == "C"
    assert medium_assessment.raci["Legal"] == "C"


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
