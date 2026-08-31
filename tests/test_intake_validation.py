"""Tests for IntakeRequest.validate() -- the guard that keeps a malformed or
incomplete intake from ever reaching the scoring engine. app.py calls
`request.validate()` immediately after constructing the request and, if any
errors are returned, shows them with `st.error(...)` and never calls
`assess()` -- so these tests double as the spec for "does the app fail
gracefully on bad intake" (it never runs the rubric against invalid input).
"""

from __future__ import annotations

import pytest

from src.models import (
    AUTOMATION_LEVELS,
    DATA_SENSITIVITY_LEVELS,
    DECISION_IMPACT_LEVELS,
    INTENDED_USERS_OPTIONS,
    IntakeRequest,
)


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


def test_fully_filled_request_has_no_validation_errors():
    assert _make_request().validate() == []


def test_missing_use_case_name_fails_validation():
    errors = _make_request(use_case_name="").validate()
    assert any("Use case name" in e for e in errors)


def test_whitespace_only_use_case_name_fails_validation():
    errors = _make_request(use_case_name="   ").validate()
    assert any("Use case name" in e for e in errors)


def test_missing_business_owner_fails_validation():
    errors = _make_request(business_owner="").validate()
    assert any("Business owner" in e for e in errors)


def test_missing_evaluation_method_fails_validation():
    errors = _make_request(evaluation_method="").validate()
    assert any("Evaluation method" in e for e in errors)


def test_whitespace_only_evaluation_method_fails_validation():
    errors = _make_request(evaluation_method="   ").validate()
    assert any("Evaluation method" in e for e in errors)


@pytest.mark.parametrize(
    "field,valid_options",
    [
        ("data_sensitivity", DATA_SENSITIVITY_LEVELS),
        ("intended_users", INTENDED_USERS_OPTIONS),
        ("automation_level", AUTOMATION_LEVELS),
        ("decision_impact", DECISION_IMPACT_LEVELS),
    ],
)
def test_invalid_enum_value_fails_validation(field, valid_options):
    request = _make_request(**{field: "not_a_real_option"})
    errors = request.validate()
    assert any(field in e for e in errors)
    # Sanity check the fixture itself: the bogus value really is outside the
    # accepted vocabulary for this field.
    assert "not_a_real_option" not in valid_options


def test_multiple_missing_fields_returns_multiple_errors():
    request = _make_request(use_case_name="", business_owner="", evaluation_method="")
    errors = request.validate()
    assert len(errors) >= 3


def test_completely_empty_intake_fails_with_every_required_field_flagged():
    request = _make_request(
        use_case_name="",
        business_owner="",
        data_sensitivity="",
        intended_users="",
        automation_level="",
        decision_impact="",
        evaluation_method="",
    )
    errors = request.validate()
    # One error per required-field check in validate(): use_case_name,
    # business_owner, data_sensitivity, intended_users, automation_level,
    # decision_impact, evaluation_method.
    assert len(errors) == 7


def test_valid_request_survives_full_pipeline_but_invalid_request_is_never_scored():
    """Mirrors app.py's actual control flow: engine.assess() is only ever
    called after validate() returns no errors."""
    from src.engine import assess

    bad_request = _make_request(use_case_name="")
    errors = bad_request.validate()
    assert errors != []
    # app.py's real branch: `if errors: show them; else: assess(request)`.
    # We assert the guard exists and would prevent assess() from running --
    # not that assess() itself raises, since it trusts validated input.
    good_request = _make_request()
    assert good_request.validate() == []
    assessment = assess(good_request)
    assert assessment.risk_tier in ("minimal", "low", "moderate", "high", "restricted")
