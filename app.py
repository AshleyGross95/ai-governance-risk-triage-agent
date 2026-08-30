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

import os

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
    IntakeRequest,
)

st.set_page_config(page_title="AI Governance & Risk Triage Agent", page_icon="🛡️", layout="wide")


def _mock_mode() -> bool:
    return os.environ.get("MOCK_MODE", "true").strip().lower() not in ("false", "0", "no")


def _build_review_packet_markdown(request: IntakeRequest, assessment, raci: dict) -> str:
    """Assembles the full markdown review packet. Every table below is
    rendered directly from the structured RiskAssessment / edited RACI dict;
    only the opening narrative paragraph may come from src/llm.py, and it is
    never allowed to change the tier, controls, or RACI values themselves."""

    narrative = generate_review_packet_narrative(request, assessment)

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

**Risk tier: {assessment.risk_tier.upper()}** (rubric score: {assessment.risk_score})

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
*This packet is a governance operating-model demonstration using synthetic data. It is not legal, privacy, or security advice.*
"""


st.title("🛡️ AI Governance & Risk Triage Agent")
st.caption(
    "Internal intake tool: proposal → deterministic risk tier → required controls → RACI → review packet → decision log."
)
st.caption(f"Mode: **{'MOCK (deterministic, no API calls)' if _mock_mode() else 'LIVE (Claude narrates the packet)'}**")

with st.expander("What this is / isn't", expanded=False):
    st.markdown(
        "This is a portfolio demonstration of an AI-governance *operating model* — how an "
        "organization might triage AI use-case proposals. **It is not legal, privacy, or "
        "security advice**, and the scoring rubric below is illustrative, not a real company's "
        "adopted policy. All data is synthetic."
    )

if "assessment" not in st.session_state:
    st.session_state.assessment = None
    st.session_state.request = None
    st.session_state.raci_df = None
    st.session_state.log_confirmation = None

st.header("1. Intake questionnaire")

with st.form("intake_form"):
    col1, col2 = st.columns(2)
    with col1:
        use_case_name = st.text_input("Use case name", placeholder="e.g. Resume screening assistant")
        business_owner = st.text_input("Business owner", placeholder="e.g. Jordan Reyes")
        model_provider = st.text_input("Model / provider", placeholder="e.g. Anthropic Claude")
        data_sensitivity = st.selectbox("Data sensitivity", DATA_SENSITIVITY_LEVELS, index=1)
        intended_users = st.selectbox("Intended users", INTENDED_USERS_OPTIONS, index=0)
        automation_level = st.selectbox("Automation level", AUTOMATION_LEVELS, index=0)
    with col2:
        decision_impact = st.selectbox(
            "Decision impact on individuals",
            DECISION_IMPACT_LEVELS,
            index=0,
            help="Does this use case influence a consequential decision about a person (hiring, credit, access, discipline, etc.)?",
        )
        human_review_present = st.checkbox("Human review present before outputs are used", value=True)
        external_data_sharing = st.checkbox("Involves external data sharing (in or out)", value=False)
        evaluation_method = st.text_area(
            "Evaluation method",
            placeholder="How will output quality/accuracy be checked before and after launch?",
        )

    submitted = st.form_submit_button("Assess risk")

if submitted:
    request = IntakeRequest(
        use_case_name=use_case_name,
        business_owner=business_owner,
        data_sensitivity=data_sensitivity,
        intended_users=intended_users,
        automation_level=automation_level,
        external_data_sharing=external_data_sharing,
        model_provider=model_provider or "unspecified",
        decision_impact=decision_impact,
        human_review_present=human_review_present,
        evaluation_method=evaluation_method,
    )
    errors = request.validate()
    if errors:
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

if st.session_state.assessment is not None:
    request = st.session_state.request
    assessment = st.session_state.assessment

    st.header("2. Risk tier — transparent, not a black box")

    tier_color = {"low": "green", "medium": "orange", "high": "red"}[assessment.risk_tier]
    st.markdown(
        f"### Risk tier: :{tier_color}[{assessment.risk_tier.upper()}]  \n"
        f"Rubric score: **{assessment.risk_score}** "
        f"(0-{4} low · 5-{10} medium · 11+ high)"
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
    st.dataframe(pd.DataFrame(controls_rows), use_container_width=True, hide_index=True)

    st.header("4. RACI — editable")
    st.caption(
        "Defaults are set by risk tier (e.g. at high tier, Legal and Security move from "
        "Consulted to Accountable sign-off). Edit any cell before generating the packet."
    )
    edited_raci_df = st.data_editor(
        st.session_state.raci_df,
        column_config={
            "Role": st.column_config.TextColumn("Role", disabled=True),
            "Assignment": st.column_config.SelectboxColumn("Assignment", options=list(RACI_VALUES)),
        },
        hide_index=True,
        use_container_width=True,
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

st.header("Decision log")
log_entries = load_decision_log()
if log_entries:
    log_df = pd.DataFrame(log_entries)[
        ["timestamp", "use_case_name", "business_owner", "risk_tier", "risk_score", "summary"]
    ].sort_values("timestamp", ascending=False)
    st.dataframe(log_df, use_container_width=True, hide_index=True)
else:
    st.caption("No assessments logged yet.")
