# Known limitations

**Defects found during this release pass: none.** The full test suite
(`pytest -v`, 62/62 passing), `python -m py_compile` on every module, a
Streamlit boot check (HTTP 200), and a manual click-through of every
in-app flow (intake, all 20 presets, submission, all five risk tiers, the
review packet, and the "Reset state" button) all passed. One real bug was
found and fixed during this pass: the original "Reset state" implementation
tried to overwrite `st.session_state["preset_choice"]` after that widget
had already been instantiated in the same script run, which raised a
`StreamlitAPIException`. It is now wired through `st.button(...,
on_click=reset_state)` instead, which runs before the widget is
re-instantiated on the next script run — this is the same reason the
existing preset dropdown must use `on_change`.

## Prototype limitations (intentionally out of scope for a demo)

- **No real authentication or authorization** — anyone running the app
  locally sees and can do everything; there are no access-controlled roles.
  Every RACI role is a display label, not a login.
- **No database** — the control catalog, the seeded presets, and the
  decision log are local JSON files read/written on disk, not a real
  datastore with concurrency control, locking, or transactions. Two
  simultaneous submissions could race on the same
  `data/synthetic/decision_log.json` write.
- **No real directory/HRIS/ticketing integration** — `business_owner` and
  `model_provider` are free-text fields, not looked up against a real
  system of record.
- **The rubric, control catalog, and RACI defaults are static and
  unversioned in this prototype's runtime** — the files themselves are
  version-controlled in git like any other source file, but the app has no
  in-product change-control workflow (approval, effective-dating, audit
  trail of *who* changed a threshold and *when*) around them. See
  `docs/governance.md` for how a real deployment would need to add this.
- **"Reset state" clears a session's view, not the underlying data** — by
  design, per the release brief. It does not simulate multi-user isolation;
  in a real deployment, each reviewer would need their own session and the
  decision log would need real access control, not just a client-side view
  toggle.
- **No hosted demo for this prototype** — see the deployment section of
  `README.md`; a Streamlit Cloud URL is pending.
- **The 20 seeded presets and the 5 committed decision-log entries are
  entirely fictional** — no real use case, employee, or organization is
  represented, and none of the "vendor" or "model provider" names refer to
  real companies.

## What this rubric is not

- **Not a certified compliance framework.** The scoring weights, the
  four thresholds, the control catalog, and the RACI defaults are
  illustrative examples built for this portfolio demo — they are not
  ISO 42001, NIST AI RMF, SOC 2, or any other certified standard, and they
  have not been reviewed by a real legal, privacy, or security team.
- **Not a substitute for human sign-off.** Every risk tier, control list,
  and RACI assignment is decision support that a human reviewer must
  confirm — the engine never approves or blocks a use case, and the UI
  says so explicitly (see the in-app warning banner and the review
  packet's closing disclaimer).
- **Not adaptive.** The rubric does not learn from outcomes, does not use
  an LLM to weigh factors, and does not adjust its own thresholds. Every
  score is deterministic and reproducible by hand.
