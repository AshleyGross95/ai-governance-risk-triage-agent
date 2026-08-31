# Production path: prototype -> pilot -> production

Expands the README's Roadmap section with more concrete detail on what
each stage would actually require.

## Prototype (this repo, today)

- Deterministic 5-tier rubric (`src/engine.py`), static 15-control catalog,
  editable RACI, template/live review packet, append-only JSON decision
  log, 20 seeded intake presets.
- Runs locally via `streamlit run app.py`; no authentication, no database,
  no real directory integration.
- Verified by 62 automated tests (`pytest -v`) plus a manual click-through
  of every UI state.
- Intended audience: a portfolio reviewer evaluating the *operating model*
  (how intake, scoring, controls, accountability, and logging fit
  together), not a team ready to triage real AI use cases with it yet.

## Pilot

Goal: run this with a real team's real (but low-stakes) intake volume,
without yet trusting it for anything binding.

- **Connect intake to the real requester directory.** Replace the free-text
  `business_owner` field with a lookup against the organization's actual
  HRIS/directory, so ownership is verifiable rather than self-reported.
- **Move the control catalog and rubric thresholds under real ownership.**
  Per `docs/governance.md`, assign a named control-catalog owner (typically
  a governance/legal function) and put `control_catalog.json` and the
  rubric's threshold constants under change review — even a lightweight
  PR-approval process is a meaningful upgrade from "anyone can edit the
  file."
- **Route `restricted`-tier submissions to a real ticketing queue** (e.g.
  Jira, ServiceNow) instead of just appending to a local JSON file, so the
  governance committee review that tier's name promises (`UC-14`) has an
  actual assignee and SLA.
- **Add basic access control** — at minimum, gate who can submit an intake
  and who can view the decision log behind the organization's existing SSO,
  even if the RACI itself stays advisory.
- **Track a small set of pilot metrics**: intake volume by department,
  time from submission to a completed review packet, and — critically —
  how often a human reviewer overrides the engine's suggested tier or RACI
  (a high override rate is a signal the rubric's weights need revisiting).

## Production

Goal: the tool's output can be relied on as the actual system of record
for AI governance decisions.

- **Version and change-control the rubric and control catalog themselves.**
  Every change to a threshold, a point value, or a control's
  `required_tiers` should be its own reviewable, dated change with a named
  approver — not a silent edit to a JSON file. See `docs/governance.md` for
  a proposed versioning scheme.
- **Require dual sign-off before a tier or control-mapping change ships**,
  mirroring the same principle the rubric already applies to `restricted`-
  tier *use cases* (multiple named Accountable roles), applied instead to
  changes in the rubric that decides those tiers.
- **Add access controls and immutability to the decision log.** Move it off
  a local JSON file onto a real datastore with row-level access control and
  write-once (or cryptographically-chained) storage, so the log can serve
  as actual audit evidence, not just a UI convenience.
- **Add real authentication**, replacing every RACI "role" display label
  with an actual identity, so "Accountable" corresponds to a specific,
  attributable person at the time of sign-off.
- **Close the loop from decisions to outcomes.** Track, for use cases that
  launched, whether the assigned tier's controls were actually completed
  before launch and whether any post-launch incident should have changed
  the original tier assignment — feeding that back into periodic rubric
  reviews (see the governance cadence in `docs/governance.md`).

## Rollout & adoption measurement (ongoing, all stages)

- Intake volume by department and by tier, over time.
- Average time-to-sign-off, broken out by tier (restricted should take
  measurably longer than minimal, by design — if it doesn't, the formal
  review gate likely isn't being honored).
- Rate of use cases escalated or blocked at each control gate, and the
  rate of manual RACI overrides, as an early-warning signal for rubric
  drift.
