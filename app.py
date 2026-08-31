"""AI Governance & Risk Triage Agent — Streamlit demo.

Internal intake tool for employees proposing a new AI use case:
structured questionnaire -> deterministic risk-tier scoring -> required
controls -> draft RACI -> decision-log entry -> review packet.

Run with:
    streamlit run app.py

Runs fully in MOCK_MODE (default) with zero API keys required. See README.md
for switching to live mode.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from src.engine import (
    assess,
    load_control_catalog,
    load_decision_log,
    log_decision,
)
from src.llm import generate_review_packet_narrative
from src.models import (
    AUTOMATION_LEVELS,
    DATA_SENSITIVITY_LEVELS,
    DECISION_IMPACT_LEVELS,
    INTENDED_USERS_OPTIONS,
    RACI_ROLES,
    RACI_VALUES,
    RISK_TIERS,
    TIER_DISPLAY_NAMES,
    IntakeRequest,
)

# Verified by running `pytest -v` in this repo and counting the passing
# tests (see docs/evaluation-plan.md). Update this literal only after
# re-running the suite and confirming the new count.
VERIFIED_TEST_COUNT = 62

APP_DIR = Path(__file__).resolve().parent
SAMPLE_USE_CASES_PATH = APP_DIR / "data" / "synthetic" / "sample_use_cases.json"

st.set_page_config(page_title="AI Governance & Risk Triage Agent", page_icon="🛡️", layout="wide")

FIELD_DEFAULTS = {
    "use_case_name": "",
    "business_owner": "",
    "model_provider": "",
    "data_sensitivity": DATA_SENSITIVITY_LEVELS[1],  # "internal"
    "intended_users": INTENDED_USERS_OPTIONS[0],     # "internal"
    "automation_level": AUTOMATION_LEVELS[0],        # "assistive"
    "decision_impact": DECISION_IMPACT_LEVELS[0],    # "low"
    "human_review_present": True,
    "external_data_sharing": False,
    "evaluation_method": "",
}

TIER_COLOR = {
    "minimal": "green",
    "low": "blue",
    "moderate": "orange",
    "high": "red",
    "restricted": "violet",
}


def _mock_mode() -> bool:
    return os.environ.get("MOCK_MODE", "true").strip().lower() not in ("false", "0", "no")


@st.cache_data
def load_sample_use_cases() -> list[dict]:
    with open(SAMPLE_USE_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_defaults() -> None:
    for key, value in FIELD_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    for key in ("assessment", "request", "raci_df", "log_confirmation", "packet_md"):
        if key not in st.session_state:
            st.session_state[key] = None
    if "decision_log_view_cleared" not in st.session_state:
        st.session_state["decision_log_view_cleared"] = False


def _clear_downstream_state() -> None:
    """Clears the computed assessment/packet whenever the form contents
    change out from under it (a new preset loaded, or a manual reset)."""
    st.session_state["assessment"] = None
    st.session_state["request"] = None
    st.session_state["raci_df"] = None
    st.session_state["log_confirmation"] = None
    st.session_state["packet_md"] = None


def apply_preset(preset: dict) -> None:
    """Pushes one seeded sample use case's fields into session_state so the
    intake form widgets pick them up on the next render."""
    st.session_state["use_case_name"] = preset["use_case_name"]
    st.session_state["business_owner"] = preset["business_owner"]
    st.session_state["model_provider"] = preset["model_provider"]
    st.session_state["data_sensitivity"] = preset["data_sensitivity"]
    st.session_state["intended_users"] = preset["intended_users"]
    st.session_state["automation_level"] = preset["automation_level"]
    st.session_state["decision_impact"] = preset["decision_impact"]
    st.session_state["human_review_present"] = preset["human_review_present"]
    st.session_state["external_data_sharing"] = preset["external_data_sharing"]
    st.session_state["evaluation_method"] = preset["evaluation_method"]
    _clear_downstream_state()


def on_preset_change() -> None:
    choice = st.session_state.get("preset_choice")
    if choice and choice != "Manual entry":
        presets = {p["use_case_name"]: p for p in load_sample_use_cases()}
        if choice in presets:
            apply_preset(presets[choice])


def reset_state() -> None:
    """'Reset state' button: restores the intake form to blank defaults,
    clears any generated assessment/packet, and clears the in-session
    decision-log VIEW only. The committed data/synthetic/decision_log.json
    file on disk is never touched by this -- the next assessment logged
    will still append to (not replace) its existing seeded entries."""
    for key, value in FIELD_DEFAULTS.items():
        st.session_state[key] = value
    st.session_state["preset_choice"] = "Manual entry"
    _clear_downstream_state()
    st.session_state["decision_log_view_cleared"] = True


def _build_review_packet_markdown(request: IntakeRequest, assessment, raci: dict) -> str:
    """Assembles the full markdown review packet. Every table below is
    rendered directly from the structured RiskAssessment / edited RACI dict;
    only the opening narrative paragraph may come from src/llm.py, and it is
    never allowed to change the tier, controls, or RACI values themselves."""

    narrative = generate_review_packet_narrative(request, assessment)
    tier_display = TIER_DISPLAY_NAMES.get(assessment.risk_tier, assessment.risk_tier)

    factors_md = "\n".join(f"- {f}" for f in assessment.risk_factors)
    controls_md = "\n".join(f"- **{cid}** — {name}" for cid, name in zip(
        assessment.required_control_ids, assessment.required_controls
    ))
    raci_md = "\n".join(f"| {role} | {raci.get(role, 'I')} |" for role in RACI_ROLES)

    return f"""# AI Use Case Review Packet — {request.use_case_name}

**Business owner:** {request.business_owner}
**Model / provider:** {request.model_provider}
**Prepared:** {pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

## Summary

{narrative}

## Risk assessment

**Risk tier: {tier_display}** (rubric score: {assessment.risk_score})

Risk factors:

{factors_md}

## Required controls ({len(assessment.required_control_ids)})

{controls_md}

## RACI

| Role | Assignment |
|------|------------|
{raci_md}

*R = Responsible, A = Accountable, C = Consulted, I = Informed.*

## Intake answers on file

| Field | Value |
|---|---|
| Data sensitivity | {request.data_sensitivity} |
| Intended users | {request.intended_users} |
| Automation level | {request.automation_level} |
| External data sharing | {request.external_data_sharing} |
| Decision impact on individuals | {request.decision_impact} |
| Human review present | {request.human_review_present} |
| Evaluation method | {request.evaluation_method} |

---
*This packet is a governance operating-model demonstration using synthetic data. It is not legal, privacy, or security advice. This tier assignment is decision support, not a legal, privacy, or security determination -- a qualified human reviewer must confirm it.*
"""


ensure_defaults()

st.title("🛡️ AI Governance & Risk Triage Agent")
st.caption("**Public portfolio prototype · Synthetic data**")
st.caption(
    "Internal intake tool: proposal → deterministic risk tier → required controls → RACI → review packet → decision log."
)
st.caption(f"Mode: **{'MOCK (deterministic, no API calls)' if _mock_mode() else 'LIVE (Claude narrates the packet)'}**")

st.warning(
    "**Decision support, not a legal, privacy, or security determination.** This tool assigns a risk "
    "tier and suggests controls using an illustrative, transparent rubric. It is **not legal, privacy, "
    "or security advice**, and does not replace review by your organization's actual Legal, Privacy, "
    "or Security teams. There is no real authentication in this app -- every role shown is a display "
    "label, not an access control.",
    icon="⚠️",
)

with st.expander("What this is / isn't", expanded=False):
    st.markdown(
        "This is a portfolio demonstration of an AI-governance *operating model* — how an "
        "organization might triage AI use-case proposals. **It is not legal, privacy, or "
        "security advice**, and the scoring rubric below is illustrative, not a real company's "
        "adopted policy. All data is synthetic."
    )

metric_col1, metric_col2, metric_col3 = st.columns(3)
metric_col1.metric("Seeded use cases", len(load_sample_use_cases()))  # len() of data/synthetic/sample_use_cases.json
metric_col2.metric("Risk tiers", len(RISK_TIERS))                     # len() of src/models.py RISK_TIERS
metric_col3.metric("Automated tests", VERIFIED_TEST_COUNT)            # verified `pytest -v` count, see docs/evaluation-plan.md

st.header("1. Intake questionnaire")

presets = load_sample_use_cases()
preset_names = ["Manual entry"] + [p["use_case_name"] for p in presets]
st.selectbox(
    "Load a seeded sample use case (or fill in the form manually)",
    preset_names,
    key="preset_choice",
    on_change=on_preset_change,
    help="Loads one of the 20 fictional intake examples in data/synthetic/sample_use_cases.json, spanning all five risk tiers.",
)

reset_col, _spacer = st.columns([1, 4])
reset_col.button(
    "Reset state",
    on_click=reset_state,
    help="Clears the intake form, any generated assessment/packet, and the decision-log view for this session. Does not delete data/synthetic/decision_log.json.",
)

with st.form("intake_form"):
    col1, col2 = st.columns(2)
    with col1:
        st.text_input("Use case name", key="use_case_name", placeholder="e.g. Resume screening assistant")
        st.text_input("Business owner", key="business_owner", placeholder="e.g. Jordan Reyes")
        st.text_input("Model / provider", key="model_provider", placeholder="e.g. Anthropic Claude")
        st.selectbox("Data sensitivity", DATA_SENSITIVITY_LEVELS, key="data_sensitivity")
        st.selectbox("Intended users", INTENDED_USERS_OPTIONS, key="intended_users")
        st.selectbox("Automation level", AUTOMATION_LEVELS, key="automation_level")
    with col2:
        st.selectbox(
            "Decision impact on individuals",
            DECISION_IMPACT_LEVELS,
            key="decision_impact",
            help="Does this use case influence a consequential decision about a person (hiring, credit, access, discipline, etc.)?",
        )
        st.checkbox("Human review present before outputs are used", key="human_review_present")
        st.checkbox("Involves external data sharing (in or out)", key="external_data_sharing")
        st.text_area(
            "Evaluation method",
            key="evaluation_method",
            placeholder="How will output quality/accuracy be checked before and after launch?",
        )

    submitted = st.form_submit_button("Assess risk")

if submitted:
    request = IntakeRequest(
        use_case_name=st.session_state["use_case_name"],
        business_owner=st.session_state["business_owner"],
        data_sensitivity=st.session_state["data_sensitivity"],
        intended_users=st.session_state["intended_users"],
        automation_level=st.session_state["automation_level"],
        external_data_sharing=st.session_state["external_data_sharing"],
        model_provider=st.session_state["model_provider"] or "unspecified",
        decision_impact=st.session_state["decision_impact"],
        human_review_present=st.session_state["human_review_present"],
        evaluation_method=st.session_state["evaluation_method"],
    )
    errors = request.validate()
    if errors:
        st.error(
            "This intake can't be assessed yet -- please fix the following before resubmitting:"
        )
        for e in errors:
            st.error(e)
    else:
        assessment = assess(request)
        st.session_state.request = request
        st.session_state.assessment = assessment
        st.session_state.raci_df = pd.DataFrame(
            {"Role": list(RACI_ROLES), "Assignment": [assessment.raci[r] for r in RACI_ROLES]}
        )
        entry = log_decision(request, assessment)
        st.session_state.log_confirmation = entry["timestamp"]
        st.session_state.packet_md = None
        st.session_state.decision_log_view_cleared = False

if st.session_state.assessment is not None:
    request = st.session_state.request
    assessment = st.session_state.assessment

    st.header("2. Risk tier — transparent, not a black box")

    tier_display = TIER_DISPLAY_NAMES.get(assessment.risk_tier, assessment.risk_tier)
    tier_color = TIER_COLOR.get(assessment.risk_tier, "gray")
    st.markdown(
        f"### Risk tier: :{tier_color}[{tier_display}]  \n"
        f"Rubric score: **{assessment.risk_score}** "
        f"(0-2 minimal · 3-6 low · 7-10 moderate · 11-14 high · 15-19 restricted pending formal review)"
    )
    if assessment.risk_tier == "restricted":
        st.error(
            "This use case is **pending formal review** -- it must go through the governance "
            "committee review and independent assessment controls below before any further work "
            "proceeds, in addition to every control a High-tier request already requires.",
            icon="🛑",
        )
    st.markdown("**Why this tier — every contributing factor:**")
    for factor in assessment.risk_factors:
        st.markdown(f"- {factor}")

    st.header("3. Required controls")
    catalog = {c["id"]: c for c in load_control_catalog()}
    controls_rows = [
        {
            "ID": cid,
            "Control": name,
            "Description": catalog.get(cid, {}).get("description", ""),
        }
        for cid, name in zip(assessment.required_control_ids, assessment.required_controls)
    ]
    st.dataframe(pd.DataFrame(controls_rows), width='stretch', hide_index=True)

    st.header("4. RACI — editable")
    st.caption(
        "Defaults escalate with risk tier -- e.g. Security and Legal move from Consulted to "
        "Accountable at High, and at Restricted pending formal review, Data Privacy also becomes "
        "Accountable and End Users move from Informed to Consulted. Edit any cell before generating "
        "the packet."
    )
    edited_raci_df = st.data_editor(
        st.session_state.raci_df,
        column_config={
            "Role": st.column_config.TextColumn("Role", disabled=True),
            "Assignment": st.column_config.SelectboxColumn("Assignment", options=list(RACI_VALUES)),
        },
        hide_index=True,
        width='stretch',
        key="raci_editor",
    )
    st.session_state.raci_df = edited_raci_df
    current_raci = dict(zip(edited_raci_df["Role"], edited_raci_df["Assignment"]))

    if st.session_state.log_confirmation:
        st.success(
            f"Assessment appended to the decision log at {st.session_state.log_confirmation}."
        )

    st.header("5. Review packet")
    if st.button("Generate review packet"):
        packet_md = _build_review_packet_markdown(request, assessment, current_raci)
        st.session_state.packet_md = packet_md

    if st.session_state.get("packet_md"):
        st.markdown(st.session_state.packet_md)
        st.download_button(
            "Download packet (.md)",
            st.session_state.packet_md,
            file_name=f"review_packet_{request.use_case_name.replace(' ', '_').lower()}.md",
            mime="text/markdown",
        )
else:
    st.caption("Submit the intake questionnaire above (or load a seeded sample use case) to see a risk assessment.")

st.header("Decision log")
if st.session_state.get("decision_log_view_cleared"):
    st.caption(
        "Decision log view cleared for this session by **Reset state**. The committed "
        "`data/synthetic/decision_log.json` file on disk is unchanged -- submitting a new "
        "assessment will show the full log again, including prior entries."
    )
else:
    log_entries = load_decision_log()
    if log_entries:
        log_df = pd.DataFrame(log_entries)[
            ["timestamp", "use_case_name", "business_owner", "risk_tier", "risk_score", "summary"]
        ].sort_values("timestamp", ascending=False)
        st.dataframe(log_df, width='stretch', hide_index=True)
    else:
        st.caption("No assessments logged yet.")
