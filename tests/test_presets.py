"""Tests for the 20 seeded intake presets in
data/synthetic/sample_use_cases.json.

These are the presets the Streamlit UI's "Load a sample use case" dropdown
offers. Every preset must (a) pass IntakeRequest.validate() cleanly, since
it's meant to be loadable straight into the form and assessed, and (b) score
to its own declared `expected_tier` under the current rubric in
src/engine.py, so the seeded data and the rubric can never silently drift
out of sync with each other.
"""

from __future__ import annotations

import json
import os

import pytest

from src.engine import score_risk
from src.models import IntakeRequest, RISK_TIERS

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
SAMPLE_USE_CASES_PATH = os.path.join(_REPO_ROOT, "data", "synthetic", "sample_use_cases.json")


def _load_presets() -> list[dict]:
    with open(SAMPLE_USE_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _preset_to_request(preset: dict) -> IntakeRequest:
    return IntakeRequest(
        use_case_name=preset["use_case_name"],
        business_owner=preset["business_owner"],
        data_sensitivity=preset["data_sensitivity"],
        intended_users=preset["intended_users"],
        automation_level=preset["automation_level"],
        external_data_sharing=preset["external_data_sharing"],
        model_provider=preset["model_provider"],
        decision_impact=preset["decision_impact"],
        human_review_present=preset["human_review_present"],
        evaluation_method=preset["evaluation_method"],
    )


_PRESETS = _load_presets()


def test_sample_use_cases_file_has_exactly_twenty_entries():
    assert len(_PRESETS) == 20


def test_sample_use_cases_have_unique_names():
    names = [p["use_case_name"] for p in _PRESETS]
    assert len(names) == len(set(names))


def test_sample_use_cases_cover_all_five_risk_tiers_not_clustered():
    tier_counts = {tier: 0 for tier in RISK_TIERS}
    for preset in _PRESETS:
        tier_counts[preset["expected_tier"]] += 1

    assert set(tier_counts.keys()) == set(RISK_TIERS)
    # Every tier must be represented, and no single tier may hold more than
    # half the presets, so the set is a genuine spread across the spectrum
    # rather than clustered at one end.
    for tier, count in tier_counts.items():
        assert count > 0, f"No seeded preset lands in the '{tier}' tier."
        assert count <= 10, f"Tier '{tier}' holds more than half of all 20 presets."


@pytest.mark.parametrize(
    "preset",
    _PRESETS,
    ids=[p["use_case_name"] for p in _PRESETS],
)
def test_each_seeded_preset_scores_to_its_expected_tier(preset):
    request = _preset_to_request(preset)
    assert request.validate() == [], f"Preset '{preset['use_case_name']}' fails intake validation."

    tier, score, _factors = score_risk(request)
    assert tier == preset["expected_tier"], (
        f"Preset '{preset['use_case_name']}' scored {score} points and landed in "
        f"'{tier}', expected '{preset['expected_tier']}'."
    )
