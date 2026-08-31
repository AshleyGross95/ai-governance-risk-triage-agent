"""Domain data models for the AI Governance & Risk Triage Agent.

Plain dataclasses (no ORM, no framework) describing the shape of one AI-use-case
intake: the structured questionnaire answers an employee submits, and the
assessment the deterministic engine (`src/engine.py`) computes from them.
Keeping these as typed structures keeps `src/engine.py` testable and keeps
`app.py` from passing loose dicts around.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


# Fixed vocabularies for the intake questionnaire. app.py uses these directly
# to populate its Streamlit selectboxes, so the UI and the engine can never
# drift out of sync with each other.
DATA_SENSITIVITY_LEVELS = ("public", "internal", "confidential", "restricted")
INTENDED_USERS_OPTIONS = ("internal", "external", "both")
AUTOMATION_LEVELS = ("assistive", "semi_autonomous", "fully_autonomous")
DECISION_IMPACT_LEVELS = ("low", "medium", "high")
RISK_TIERS = ("minimal", "low", "moderate", "high", "restricted")

# Human-facing label for each tier key. Every tier key is displayed via this
# map rather than `.upper()`-ing the key directly, because the most severe
# tier's display name is a phrase ("Restricted pending formal review"), not
# a single word.
TIER_DISPLAY_NAMES = {
    "minimal": "Minimal",
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "restricted": "Restricted pending formal review",
}

# Fixed set of stakeholder roles every RACI table covers, in display order.
RACI_ROLES = ("Business Owner", "Data Privacy", "Security", "Legal", "IT", "End Users")
RACI_VALUES = ("R", "A", "C", "I")


@dataclass
class IntakeRequest:
    """Everything the Streamlit intake form collects for one proposed AI use case."""

    use_case_name: str
    business_owner: str

    data_sensitivity: str          # public | internal | confidential | restricted
    intended_users: str            # internal | external | both
    automation_level: str          # assistive | semi_autonomous | fully_autonomous
    external_data_sharing: bool    # is data shared with/sourced from an external party?
    model_provider: str            # free-text, e.g. "Anthropic Claude", "internal fine-tune"
    decision_impact: str           # low | medium | high — does this affect a consequential
                                    # decision about a person (hiring, credit, access, etc.)?
    human_review_present: bool     # is there a human in the loop before action/output is used?
    evaluation_method: str         # free-text description of how outputs are checked for quality

    def validate(self) -> List[str]:
        """Returns a list of human-readable validation errors, empty if valid."""
        errors: List[str] = []
        if not self.use_case_name.strip():
            errors.append("Use case name is required.")
        if not self.business_owner.strip():
            errors.append("Business owner is required.")
        if self.data_sensitivity not in DATA_SENSITIVITY_LEVELS:
            errors.append(f"data_sensitivity must be one of {DATA_SENSITIVITY_LEVELS}.")
        if self.intended_users not in INTENDED_USERS_OPTIONS:
            errors.append(f"intended_users must be one of {INTENDED_USERS_OPTIONS}.")
        if self.automation_level not in AUTOMATION_LEVELS:
            errors.append(f"automation_level must be one of {AUTOMATION_LEVELS}.")
        if self.decision_impact not in DECISION_IMPACT_LEVELS:
            errors.append(f"decision_impact must be one of {DECISION_IMPACT_LEVELS}.")
        if not self.evaluation_method.strip():
            errors.append("Evaluation method is required.")
        return errors


@dataclass
class RiskAssessment:
    """Output of the deterministic scoring engine for one IntakeRequest."""

    risk_tier: str                          # minimal | low | moderate | high | restricted
    risk_score: int                         # raw points total, for transparency/audit
    risk_factors: List[str]                 # human-readable reasons that drove the tier
    required_controls: List[str]            # control names pulled from the catalog
    required_control_ids: List[str] = field(default_factory=list)
    raci: Dict[str, str] = field(default_factory=dict)  # role -> R/A/C/I
