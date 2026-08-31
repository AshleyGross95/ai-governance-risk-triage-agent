# Workflow

Step-by-step user flow through `app.py`, matching the actual UI top to
bottom.

## 1. Land on the app

The main screen shows, in order:

1. Title and the **"Public portfolio prototype · Synthetic data"** line.
2. A one-line mode indicator: MOCK (default, deterministic, no API calls) or
   LIVE (Claude narrates the packet).
3. A prominent warning banner: **"Decision support, not a legal, privacy, or
   security determination"**, always visible without expanding anything.
4. A collapsed "What this is / isn't" expander with more detail.
5. A 3-metric panel: **Seeded use cases** (20, `len()` of
   `data/synthetic/sample_use_cases.json`), **Risk tiers** (5, `len()` of
   `src/models.py::RISK_TIERS`), **Automated tests** (the verified `pytest`
   count — see `docs/evaluation-plan.md`).

## 2. Fill out the intake questionnaire

Two ways in:

- **Load a seeded sample use case** — a dropdown above the form lists
  "Manual entry" plus all 20 presets from `sample_use_cases.json`. Picking
  one pushes every field into the form immediately (via a Streamlit
  `on_change` callback into `st.session_state`); the form remains fully
  editable afterward.
- **Fill in the form manually** — leave the dropdown on "Manual entry" and
  type into each field directly.

The form itself asks nine questions, matching `IntakeRequest` one-to-one:
use case name, business owner, model/provider, data sensitivity, intended
users, automation level, decision impact on individuals, human review
present (checkbox), external data sharing (checkbox), and evaluation
method (free text).

A **"Reset state"** button above the form clears every field back to blank
defaults, clears any assessment or packet already generated, and clears the
decision-log view for the current session — without touching the committed
`data/synthetic/decision_log.json` file (see step 6).

## 3. Submit -> validate -> score

Clicking **"Assess risk"**:

1. Builds an `IntakeRequest` from the form's current values.
2. Calls `request.validate()`. If it returns any errors (e.g. a required
   field left blank), the app shows each one with `st.error(...)` and
   **does not** call the scoring engine — the rubric never runs against
   invalid input (see `docs/evaluation-plan.md` and
   `tests/test_intake_validation.py`).
3. If valid, calls `src/engine.py::assess(request)`, which runs
   `score_risk` -> `get_required_controls` -> `build_raci` in one pass and
   returns a `RiskAssessment`.
4. Immediately appends the completed assessment to
   `data/synthetic/decision_log.json` via `log_decision(...)`.

## 4. Review the risk tier (transparent, not a black box)

Section 2 of the page shows:

- The tier name (one of `TIER_DISPLAY_NAMES`'s five values, color-coded) and
  the raw rubric score, with the full 0-2 / 3-6 / 7-10 / 11-14 / 15-19
  threshold legend printed alongside it.
- At the `restricted` tier specifically, an additional red banner explains
  the request is pending formal review and lists what that implies.
- Every non-zero-point factor that contributed to the score, as a plain
  English sentence (e.g. *"Data sensitivity is 'restricted' (+4 pts)."*).

## 5. Review the required controls

Section 3 renders a table of every control `get_required_controls` matched
for this tier and this request's `external_data_sharing` value: ID, name,
and full description, pulled straight from `control_catalog.json`.

## 6. Review and edit the RACI

Section 4 shows the tier's default RACI (`build_raci`) as an editable
`st.data_editor` table — one row per `RACI_ROLES` entry, with a dropdown
per cell restricted to `RACI_VALUES` (`R`/`A`/`C`/`I`). Edits here are held
in session state and used when the packet is generated; they are never
written back into the engine's defaults.

A success banner confirms the timestamp at which this assessment was
appended to the decision log.

## 7. Generate and download the review packet

Clicking **"Generate review packet"** assembles a single markdown document
(`app.py::_build_review_packet_markdown`) containing: the (optionally
Claude-polished) narrative paragraph, the risk tier and factors, the full
controls table, the (possibly edited) RACI table, the raw intake answers,
and the "not legal/privacy/security advice" disclaimer. A **"Download
packet (.md)"** button lets the user save it.

## 8. Review the decision log

The bottom of the page always shows the decision log — either every entry
in `data/synthetic/decision_log.json` (newest first), or, immediately after
a "Reset state" click, a note that the view has been cleared for this
session without touching the underlying file. Submitting a new assessment
un-clears the view and shows the full log again, including the new entry.
