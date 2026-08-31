# Data model

All shapes below are plain Python `@dataclass` definitions in `src/models.py`
(no ORM, no framework) plus the two seeded JSON files in `data/synthetic/`.
This file documents both so the intake form, the engine, and the seeded data
can never silently drift apart.

## `IntakeRequest` (`src/models.py`)

Everything the Streamlit intake form collects for one proposed AI use case.

| Field | Type | Notes |
|---|---|---|
| `use_case_name` | `str` | Required (non-blank after `.strip()`). |
| `business_owner` | `str` | Required (non-blank after `.strip()`). |
| `data_sensitivity` | `str` | One of `DATA_SENSITIVITY_LEVELS`: `public`, `internal`, `confidential`, `restricted`. |
| `intended_users` | `str` | One of `INTENDED_USERS_OPTIONS`: `internal`, `external`, `both`. |
| `automation_level` | `str` | One of `AUTOMATION_LEVELS`: `assistive`, `semi_autonomous`, `fully_autonomous`. |
| `external_data_sharing` | `bool` | Is data shared with, or sourced from, an external party? |
| `model_provider` | `str` | Free text, e.g. `"Anthropic Claude"`, `"internal fine-tune"`. Not validated (not a required field). |
| `decision_impact` | `str` | One of `DECISION_IMPACT_LEVELS`: `low`, `medium`, `high`. Does this affect a consequential decision about a person? |
| `human_review_present` | `bool` | Is there a human in the loop before the output/action is used? |
| `evaluation_method` | `str` | Required (non-blank after `.strip()`) free-text description of how output quality is checked. |

`IntakeRequest.validate()` returns a list of human-readable error strings
(empty list = valid). It checks the two free-text required fields, the four
enum fields against their fixed vocabularies, and the evaluation-method
field — **seven checks total**, matching the seven `if` branches in the
method body. `app.py` calls this immediately after constructing the request
and never calls `assess()` if it returns any errors (see
`docs/evaluation-plan.md` and `tests/test_intake_validation.py`).

## `RiskAssessment` (`src/models.py`)

Output of the deterministic scoring engine (`src/engine.py::assess`) for one
`IntakeRequest`.

| Field | Type | Notes |
|---|---|---|
| `risk_tier` | `str` | One of the five `RISK_TIERS`: `minimal`, `low`, `moderate`, `high`, `restricted`. |
| `risk_score` | `int` | Raw points total (0-19), for transparency/audit. |
| `risk_factors` | `List[str]` | Human-readable reasons that drove the tier — one entry per non-zero-point answer, or a single "no elevated-risk factors" message if the score is 0. |
| `required_controls` | `List[str]` | Control names pulled from `control_catalog.json`, in catalog order. |
| `required_control_ids` | `List[str]` | The matching control IDs (`UC-01` … `UC-15`), same order. |
| `raci` | `Dict[str, str]` | Role -> `R`/`A`/`C`/`I`, one entry per `RACI_ROLES`. |

## Fixed vocabularies (`src/models.py`)

`app.py` imports these directly to populate its Streamlit selectboxes, so
the UI and the engine can never drift out of sync with each other:

```python
DATA_SENSITIVITY_LEVELS = ("public", "internal", "confidential", "restricted")
INTENDED_USERS_OPTIONS  = ("internal", "external", "both")
AUTOMATION_LEVELS       = ("assistive", "semi_autonomous", "fully_autonomous")
DECISION_IMPACT_LEVELS  = ("low", "medium", "high")
RISK_TIERS              = ("minimal", "low", "moderate", "high", "restricted")
RACI_ROLES = ("Business Owner", "Data Privacy", "Security", "Legal", "IT", "End Users")
RACI_VALUES = ("R", "A", "C", "I")
```

`TIER_DISPLAY_NAMES` maps each `RISK_TIERS` key to the human-facing label
used in the UI and the review packet — every tier is a single capitalized
word except the most severe one, which is a full phrase:

```python
TIER_DISPLAY_NAMES = {
    "minimal": "Minimal",
    "low": "Low",
    "moderate": "Moderate",
    "high": "High",
    "restricted": "Restricted pending formal review",
}
```

## Seeded record shapes (`data/synthetic/`)

### `sample_use_cases.json` (exactly 20 entries)

Each entry is a preset the "Load a seeded sample use case" dropdown can push
into the intake form. Every field except `expected_tier` maps one-to-one to
an `IntakeRequest` constructor argument (see `app.py::apply_preset`);
`expected_tier` is test/documentation metadata only (the tier the rubric is
expected to produce for that preset) and is not read by the app.

```json
{
  "use_case_name": "AI resume-screening assistant",
  "business_owner": "Kendra Okonkwo",
  "data_sensitivity": "restricted",
  "intended_users": "external",
  "automation_level": "fully_autonomous",
  "external_data_sharing": false,
  "model_provider": "Third-party HR-tech vendor",
  "decision_impact": "high",
  "human_review_present": false,
  "evaluation_method": "No human review before a rejection is sent; the vendor's own accuracy claims have not been independently validated.",
  "expected_tier": "restricted"
}
```

The 20 presets are distributed exactly 4-4-4-4-4 across the five tiers —
verified by `tests/test_presets.py::test_sample_use_cases_cover_all_five_risk_tiers_not_clustered`
and, individually, by `test_each_seeded_preset_scores_to_its_expected_tier`.

### `control_catalog.json` (exactly 15 entries)

Each entry is one governance control the engine can pull into an
assessment's `required_controls`.

```json
{
  "id": "UC-14",
  "name": "Governance committee review and named executive sign-off",
  "description": "A cross-functional AI governance committee ... formally reviews the request ...",
  "required_tiers": ["restricted"],
  "required_if_external_data_sharing": false
}
```

- `id` — stable identifier (`UC-01` … `UC-15`), referenced in the decision
  log and the review packet.
- `required_tiers` — list of `RISK_TIERS` keys this control applies to. A
  control matches an assessment if the assessed tier appears in this list.
- `required_if_external_data_sharing` — if `true`, this control is also
  pulled in whenever `IntakeRequest.external_data_sharing` is `True`,
  **regardless of tier** (this is how `UC-03`, the DPA review, works — its
  own `required_tiers` is empty).

`UC-14` and `UC-15` are the only two controls scoped exclusively to the
`restricted` tier, giving the "pending formal review" tier name a concrete
meaning: two additional controls that no other tier requires. See
`docs/governance.md` for the full ownership and change-control model for
this catalog.

### `decision_log.json` (append-only)

Every completed assessment appends one entry here
(`src/engine.py::log_decision`); nothing is ever removed or rewritten. The
committed file ships with 5 seeded entries, one per risk tier, so the log
viewer has representative data on first load.

```json
{
  "timestamp": "2026-08-14T11:38:00Z",
  "use_case_name": "AI resume-screening assistant",
  "business_owner": "Kendra Okonkwo",
  "risk_tier": "restricted",
  "risk_score": 17,
  "summary": "Fully-autonomous use of restricted data for external users, ...",
  "required_control_ids": ["UC-01", "UC-02", "..."]
}
```

The **"Reset state"** button in the UI clears only the in-session *view* of
this file (see `docs/workflow.md`); it never deletes or truncates the file
on disk, and the next assessment logged still appends after the seeded
entries.
