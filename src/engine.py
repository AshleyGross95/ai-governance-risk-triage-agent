"""Deterministic risk-triage engine for the AI Governance & Risk Triage Agent.

This is the "brain" of the demo: a transparent, configurable, points-based
rubric that maps an `IntakeRequest` to a risk tier, the specific factors that
drove that tier, the controls the catalog requires, and a default RACI table.
None of this calls an LLM. It is a small table of factor -> points plus two
thresholds, so any reviewer can re-derive the tier by hand from the intake
answers alone.

Scoring rubric
--------------
Each factor on the intake form contributes points independently. The points
are summed into a single risk_score, which is then bucketed into a tier.

    Factor                  | Value              | Points
    -------------------------|--------------------|-------
    data_sensitivity         | public             | 0
                              | internal           | 1
                              | confidential       | 2
                              | restricted         | 4
    intended_users           | internal           | 0
                              | both               | 1
                              | external           | 2
    automation_level         | assistive          | 0
                              | semi_autonomous    | 2
                              | fully_autonomous   | 4
    decision_impact          | low                | 0
                              | medium             | 2
                              | high               | 4
    human_review_present     | True               | 0
                              | False              | +3
    external_data_sharing    | False              | 0
                              | True               | +2

    Maximum possible score: 19

Thresholds (on the summed risk_score), bucketed into five tiers:

    0-2    -> Minimal
    3-6    -> Low
    7-10   -> Moderate
    11-14  -> High
    15-19  -> Restricted pending formal review

Five tiers (rather than three) give the rubric room to distinguish "no
material risk factors present" (Minimal) from "some risk factors, still
low stakes" (Low), and to carve out a top band, Restricted pending formal
review, for the small set of requests that combine the most severe factors
(restricted data, full autonomy, high decision impact, no human review) and
should not proceed through the standard High-tier control path alone —
they require a named governance-committee review before anything else.

Independently of the score, `external_data_sharing=True` always pulls the
Data Processing Agreement (DPA) review control into `required_controls`,
regardless of which tier the request lands in (per the control catalog's
`required_if_external_data_sharing` flag) — this mirrors real governance
practice where certain controls are triggered by a specific fact pattern
rather than by overall risk level.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from src.models import RACI_ROLES, RiskAssessment, IntakeRequest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
CONTROL_CATALOG_PATH = os.path.join(_REPO_ROOT, "data", "synthetic", "control_catalog.json")
DECISION_LOG_PATH = os.path.join(_REPO_ROOT, "data", "synthetic", "decision_log.json")

# --- Rubric tables (kept as plain dicts so they're easy to read, audit, and
# tune without touching the scoring logic below) --------------------------

_DATA_SENSITIVITY_POINTS = {"public": 0, "internal": 1, "confidential": 2, "restricted": 4}
_INTENDED_USERS_POINTS = {"internal": 0, "both": 1, "external": 2}
_AUTOMATION_LEVEL_POINTS = {"assistive": 0, "semi_autonomous": 2, "fully_autonomous": 4}
_DECISION_IMPACT_POINTS = {"low": 0, "medium": 2, "high": 4}
_NO_HUMAN_REVIEW_POINTS = 3
_EXTERNAL_DATA_SHARING_POINTS = 2

MINIMAL_LOW_THRESHOLD = 3        # score >= this -> at least low
LOW_MODERATE_THRESHOLD = 7       # score >= this -> at least moderate
MODERATE_HIGH_THRESHOLD = 11     # score >= this -> at least high
HIGH_RESTRICTED_THRESHOLD = 15   # score >= this -> restricted pending formal review


def score_risk(request: IntakeRequest) -> Tuple[str, int, List[str]]:
    """Applies the rubric above to one IntakeRequest.

    Returns (risk_tier, risk_score, risk_factors) where risk_factors is an
    ordered list of human-readable strings explaining every factor that
    contributed a non-zero number of points, so the tier is never a black box.
    """
    score = 0
    factors: List[str] = []

    ds_points = _DATA_SENSITIVITY_POINTS[request.data_sensitivity]
    score += ds_points
    if ds_points:
        factors.append(
            f"Data sensitivity is '{request.data_sensitivity}' (+{ds_points} pts)."
        )

    iu_points = _INTENDED_USERS_POINTS[request.intended_users]
    score += iu_points
    if iu_points:
        factors.append(
            f"Intended users are '{request.intended_users}' (+{iu_points} pts)."
        )

    al_points = _AUTOMATION_LEVEL_POINTS[request.automation_level]
    score += al_points
    if al_points:
        factors.append(
            f"Automation level is '{request.automation_level}' (+{al_points} pts)."
        )

    di_points = _DECISION_IMPACT_POINTS[request.decision_impact]
    score += di_points
    if di_points:
        factors.append(
            f"Decision impact on individuals is '{request.decision_impact}' (+{di_points} pts)."
        )

    if not request.human_review_present:
        score += _NO_HUMAN_REVIEW_POINTS
        factors.append(
            f"No human review is present before outputs are used (+{_NO_HUMAN_REVIEW_POINTS} pts)."
        )

    if request.external_data_sharing:
        score += _EXTERNAL_DATA_SHARING_POINTS
        factors.append(
            f"Data is shared with or sourced from an external party (+{_EXTERNAL_DATA_SHARING_POINTS} pts)."
        )

    if score >= HIGH_RESTRICTED_THRESHOLD:
        tier = "restricted"
    elif score >= MODERATE_HIGH_THRESHOLD:
        tier = "high"
    elif score >= LOW_MODERATE_THRESHOLD:
        tier = "moderate"
    elif score >= MINIMAL_LOW_THRESHOLD:
        tier = "low"
    else:
        tier = "minimal"

    if not factors:
        factors.append("No elevated-risk factors were flagged on any intake question.")

    return tier, score, factors


def load_control_catalog(path: str = CONTROL_CATALOG_PATH) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_required_controls(
    risk_tier: str,
    external_data_sharing: bool,
    catalog: List[dict] | None = None,
) -> Tuple[List[str], List[str]]:
    """Filters the control catalog down to what this assessment requires.

    A control is required if the assessed tier appears in its `required_tiers`
    list, OR if `external_data_sharing` is True and the control is flagged
    `required_if_external_data_sharing` (this applies regardless of tier).

    Returns (control_ids, control_names), both in catalog order.
    """
    if catalog is None:
        catalog = load_control_catalog()

    ids: List[str] = []
    names: List[str] = []
    for control in catalog:
        tier_match = risk_tier in control.get("required_tiers", [])
        external_match = external_data_sharing and control.get(
            "required_if_external_data_sharing", False
        )
        if tier_match or external_match:
            ids.append(control["id"])
            names.append(control["name"])
    return ids, names


# Default RACI per risk tier. Note this intentionally deviates from strict
# single-"Accountable" RACI convention: accountability escalates step by step
# as the tier rises, and at the top two tiers more than one role carries "A"
# alongside the Business Owner, representing that governance requires their
# independent sign-off before launch, not just consultation.
#
# Escalation ladder, by role, across the five tiers:
#   Business Owner - Accountable at every tier (always owns the use case).
#   Data Privacy   - Informed -> Consulted -> Consulted -> Consulted -> Accountable
#   Security       - Informed -> Informed  -> Consulted -> Accountable -> Accountable
#   Legal          - Informed -> Informed  -> Consulted -> Accountable -> Accountable
#   IT             - Responsible at every tier (always builds/operates it).
#   End Users      - Informed -> Informed  -> Informed  -> Informed  -> Consulted
#
# At Restricted pending formal review, Data Privacy joins Security and Legal
# as Accountable (four accountable sign-offs total, alongside the Business
# Owner) and End Users move from Informed to Consulted, reflecting that a
# request at this tier needs input from those affected before it can proceed
# -- the most conservative RACI the rubric produces. All of this is editable
# by the reviewer in the Streamlit UI before the review packet is generated.
_DEFAULT_RACI: Dict[str, Dict[str, str]] = {
    "minimal": {
        "Business Owner": "A",
        "Data Privacy": "I",
        "Security": "I",
        "Legal": "I",
        "IT": "R",
        "End Users": "I",
    },
    "low": {
        "Business Owner": "A",
        "Data Privacy": "C",
        "Security": "I",
        "Legal": "I",
        "IT": "R",
        "End Users": "I",
    },
    "moderate": {
        "Business Owner": "A",
        "Data Privacy": "C",
        "Security": "C",
        "Legal": "C",
        "IT": "R",
        "End Users": "I",
    },
    "high": {
        "Business Owner": "A",
        "Data Privacy": "C",
        "Security": "A",
        "Legal": "A",
        "IT": "R",
        "End Users": "I",
    },
    "restricted": {
        "Business Owner": "A",
        "Data Privacy": "A",
        "Security": "A",
        "Legal": "A",
        "IT": "R",
        "End Users": "C",
    },
}


def build_raci(risk_tier: str) -> Dict[str, str]:
    """Returns a sensible default RACI dict for the given tier. Callers
    (the Streamlit UI) may let the user edit this before it's finalized."""
    defaults = _DEFAULT_RACI.get(risk_tier, _DEFAULT_RACI["moderate"])
    return {role: defaults.get(role, "I") for role in RACI_ROLES}


def assess(request: IntakeRequest, catalog: List[dict] | None = None) -> RiskAssessment:
    """Runs the full deterministic pipeline: score -> tier -> controls -> RACI."""
    tier, score, factors = score_risk(request)
    control_ids, control_names = get_required_controls(
        tier, request.external_data_sharing, catalog
    )
    raci = build_raci(tier)
    return RiskAssessment(
        risk_tier=tier,
        risk_score=score,
        risk_factors=factors,
        required_controls=control_names,
        required_control_ids=control_ids,
        raci=raci,
    )


def load_decision_log(path: str = DECISION_LOG_PATH) -> List[dict]:
    """Reads the decision log, returning an empty list if it doesn't exist yet."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return []
        return json.loads(content)


def log_decision(
    request: IntakeRequest,
    assessment: RiskAssessment,
    path: str = DECISION_LOG_PATH,
) -> dict:
    """Appends one completed assessment to the decision log as a timestamped
    entry and returns the entry that was written. Creates the log file (and
    its parent directory) if it doesn't exist yet."""
    entries = load_decision_log(path)

    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "use_case_name": request.use_case_name,
        "business_owner": request.business_owner,
        "risk_tier": assessment.risk_tier,
        "risk_score": assessment.risk_score,
        "summary": (
            f"{request.automation_level.replace('_', '-')} use of "
            f"{request.data_sensitivity} data for {request.intended_users} users "
            f"(decision impact: {request.decision_impact}, human review present: "
            f"{request.human_review_present}, external data sharing: "
            f"{request.external_data_sharing}). Assessed as {assessment.risk_tier} risk; "
            f"{len(assessment.required_control_ids)} controls required."
        ),
        "required_control_ids": assessment.required_control_ids,
    }
    entries.append(entry)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)
        f.write("\n")

    return entry
