# Evaluation plan

What "correct" means for this agent, and how the automated test suite
checks it.

## What "correct" means

1. **The risk tier is reproducible by hand.** Given any `IntakeRequest`, a
   reviewer can re-derive `risk_score` and `risk_tier` using only the
   rubric table in `src/engine.py`'s module docstring (mirrored in
   `README.md`) — no hidden logic, no model call. The tier is one of five
   fixed values (`minimal`, `low`, `moderate`, `high`, `restricted`),
   bucketed from the score by four fixed thresholds (3 / 7 / 11 / 15).
2. **The required-controls list is exactly reproducible from the catalog.**
   For a given tier and `external_data_sharing` value, the control IDs
   returned by `get_required_controls` must exactly match
   `control_catalog.json`'s `required_tiers` and
   `required_if_external_data_sharing` rules — no missed or extra control.
3. **The RACI defaults escalate monotonically and are never overridden by
   the engine after a human edits them.** `build_raci` is a pure function
   of `risk_tier`; the UI never re-derives it after an edit.
4. **The decision log accumulates, never overwrites.** Every call to
   `log_decision` appends one entry and leaves every prior entry byte-for-byte
   unchanged in the JSON array.
5. **Invalid or incomplete intake never reaches the scoring engine.**
   `IntakeRequest.validate()` must catch every required-field omission and
   every out-of-vocabulary enum value before `assess()` is ever called.
6. **The 20 seeded presets and the rubric never silently drift apart.**
   Every preset in `sample_use_cases.json` must still score to its own
   declared `expected_tier` under the current rubric — if the rubric ever
   changes, this is the mechanism that forces the seeded data (or the
   rubric) to be updated in lockstep.

## How the test suite checks each of those

Run with:

```bash
pytest -v
```

**62 tests, all passing**, split across three files:

### `tests/test_engine.py` (26 tests) — the rubric itself

- One dedicated fixture per tier (`test_minimal_risk_fixture_scores_minimal`
  … `test_restricted_risk_fixture_scores_restricted`) confirming both the
  raw score and the resulting tier.
- Four boundary tests (`test_minimal_low_boundary_is_contiguous`, and one
  per subsequent threshold) that check one point below and exactly at each
  of the four cutoffs, guarding against off-by-one errors.
- DPA-control tests confirming `external_data_sharing=True` always pulls in
  `UC-03` regardless of tier, and that it's excluded when `False`.
- A monotonicity test confirming the number of required controls never
  decreases as the tier rises, and strictly increases from `low` through
  `restricted`.
- A parametrized test (5 cases) checking the exact control-ID set returned
  at each of the five tiers against the catalog.
- A parametrized test (5 cases) checking the exact RACI dict returned at
  each tier, plus a dedicated test confirming `restricted` is strictly the
  most conservative (highest Accountable count of any tier, and the only
  tier where End Users move off "Informed").
- Decision-log accumulation and missing-file-returns-empty-list tests.

### `tests/test_presets.py` (23 tests) — the seeded data

- Exact-count check (`== 20`).
- Uniqueness check on `use_case_name`.
- Tier-spread check: every one of the 5 tiers has at least one preset, and
  no tier holds more than half of all 20 (guards against clustering).
- A parametrized test with **one node per preset** (20 total) asserting
  that preset both passes `IntakeRequest.validate()` cleanly and scores to
  its own declared `expected_tier` under the live rubric.

### `tests/test_intake_validation.py` (13 tests) — bad-input handling

- A fully-filled request produces zero validation errors.
- Missing/whitespace-only checks for each required free-text field
  (`use_case_name`, `business_owner`, `evaluation_method`).
- A parametrized test (4 cases) confirming each of the four enum fields
  rejects an out-of-vocabulary value.
- Multiple-missing-fields and completely-empty-intake tests confirming
  every one of the seven checks in `validate()` fires independently.
- An end-to-end test confirming the same control flow `app.py` uses: a
  request that fails validation is never passed to `assess()`, while a
  valid one flows all the way through to a `RiskAssessment` with a
  five-tier-vocabulary `risk_tier`.

## What this evaluation does *not* cover

- **No live-mode (Claude narration) testing.** `src/llm.py`'s live path
  calls the real Anthropic API and is not exercised by the test suite; it
  is manually verified to fall back to the deterministic template on any
  exception, and the template itself (`generate_mock_narrative`) is what
  the tests above exercise indirectly through the full pipeline.
- **No UI-level (Streamlit) testing.** The test suite exercises
  `src/models.py` and `src/engine.py` directly; `app.py`'s wiring
  (session-state handling, widget callbacks, the preset dropdown, the reset
  button) is verified manually — see `docs/limitations.md`.
- **No concurrency testing** of the JSON-file decision log — see
  `docs/limitations.md` and `docs/production-path.md`.
