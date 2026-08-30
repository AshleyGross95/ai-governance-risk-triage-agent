"""LLM adapter for the AI Governance & Risk Triage Agent.

The engine (`src/engine.py`) computes every fact in the review packet: the
risk tier, the risk score, the risk factors, the required controls, and the
RACI table. This module only ever turns those already-computed facts into
prose narrative for the packet's executive-summary paragraph. It never
changes the tier, adds/removes a control, or edits the RACI table — in both
mock and live mode, the narrative must be traceable back to the
`RiskAssessment` it was handed.

- MOCK_MODE=true (default): a deterministic, template-based narrative
  paragraph is generated locally. No network call, no API key required.
- MOCK_MODE=false and ANTHROPIC_API_KEY set: Claude (model `claude-sonnet-5`)
  is asked to polish that same paragraph from the same structured facts.
  If the live call fails for any reason, we fall back to the mock paragraph
  rather than showing an error, so the demo never breaks.
"""

from __future__ import annotations

import os
from typing import List

from src.models import IntakeRequest, RiskAssessment


def _is_mock_mode() -> bool:
    return os.environ.get("MOCK_MODE", "true").strip().lower() not in ("false", "0", "no")


def generate_mock_narrative(request: IntakeRequest, assessment: RiskAssessment) -> str:
    """Deterministic, template-based executive-summary paragraph. Every fact
    below is read directly from the engine's output — nothing here is invented."""

    factors_clause = " ".join(assessment.risk_factors)
    controls_count = len(assessment.required_control_ids)

    return (
        f"\"{request.use_case_name}\" was submitted by {request.business_owner} as a "
        f"{request.automation_level.replace('_', ' ')} AI use case using {request.model_provider}, "
        f"handling {request.data_sensitivity} data for {request.intended_users} users. "
        f"Based on the intake questionnaire, this request scores {assessment.risk_score} points "
        f"against the governance rubric and is assessed as {assessment.risk_tier.upper()} risk. "
        f"{factors_clause} As a result, {controls_count} control(s) from the standing control "
        f"catalog apply before this use case can proceed, and the RACI table below assigns "
        f"accountability across the affected stakeholder roles. This assessment should be "
        f"reviewed alongside the evaluation method described by the business owner "
        f"(\"{request.evaluation_method}\") before final sign-off."
    )


def _build_live_prompt(request: IntakeRequest, assessment: RiskAssessment) -> str:
    factors_bullets = "\n".join(f"- {f}" for f in assessment.risk_factors)
    controls_bullets = "\n".join(f"- {c}" for c in assessment.required_controls)
    raci_lines = "\n".join(f"- {role}: {value}" for role, value in assessment.raci.items())

    return (
        "You are narrating a completed AI governance risk-triage assessment for an internal "
        "review packet. All facts below were already computed by a deterministic rules engine — "
        "do NOT change the risk tier, add or remove a control, or alter the RACI assignments. "
        "Write a tight, professional 3-5 sentence executive-summary paragraph (no headers, no "
        "bullet points, no markdown) suitable for a governance review packet, using only the "
        "facts given.\n\n"
        f"Use case: {request.use_case_name}\n"
        f"Business owner: {request.business_owner}\n"
        f"Model/provider: {request.model_provider}\n"
        f"Data sensitivity: {request.data_sensitivity}\n"
        f"Intended users: {request.intended_users}\n"
        f"Automation level: {request.automation_level}\n"
        f"Decision impact on individuals: {request.decision_impact}\n"
        f"Human review present: {request.human_review_present}\n"
        f"External data sharing: {request.external_data_sharing}\n"
        f"Evaluation method: {request.evaluation_method}\n\n"
        f"Risk score: {assessment.risk_score}\n"
        f"Risk tier: {assessment.risk_tier}\n"
        f"Risk factors:\n{factors_bullets}\n\n"
        f"Required controls:\n{controls_bullets}\n\n"
        f"RACI:\n{raci_lines}\n"
    )


def generate_review_packet_narrative(request: IntakeRequest, assessment: RiskAssessment) -> str:
    """Public entry point used by app.py. Routes to mock or live narration
    depending on MOCK_MODE / ANTHROPIC_API_KEY, always falling back to the
    deterministic template on any failure. Returns only the narrative
    paragraph — app.py assembles the rest of the packet (tables, headers)
    from the structured RiskAssessment directly, so the tier/controls/RACI
    can never be altered by this function."""

    mock_narrative = generate_mock_narrative(request, assessment)

    if _is_mock_mode():
        return mock_narrative

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return mock_narrative

    try:
        import anthropic  # imported lazily so mock mode never needs this dependency

        client = anthropic.Anthropic(api_key=api_key)
        prompt = _build_live_prompt(request, assessment)
        message = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts: List[str] = [
            block.text for block in message.content if getattr(block, "type", None) == "text"
        ]
        live_text = "".join(text_parts).strip()
        return live_text or mock_narrative
    except Exception:
        # Never let a live-mode failure break the demo; fall back to the
        # deterministic narrative, which is always available.
        return mock_narrative
