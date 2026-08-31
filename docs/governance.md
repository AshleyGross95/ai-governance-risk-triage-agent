# Governance model

This repo is one of two in this portfolio where governance, RACI, and risk
are the actual subject of the demo (the other is
`enterprise-knowledge-governance-agent`). This document explains three
things a reader of the code should understand but that don't fit naturally
in the README: the rubric's governance *intent* (why it's shaped the way it
is, not just what it computes), who would own the control catalog in a real
deployment, and how a real organization would version and change-control a
rubric like this one instead of letting it drift.

Everything below describes an illustrative operating model for this
portfolio demo. It is not a certified framework and not a substitute for
your organization's actual AI governance policy.

## 1. The rubric's governance intent

`src/engine.py::score_risk` is a small, additive points table over six
factors (data sensitivity, intended users, automation level, decision
impact, human review presence, external data sharing), bucketed into five
tiers by four fixed thresholds. The *engineering* reason for that shape is
in the module docstring; this section is about the *governance* reasoning
behind each design choice.

- **Additive, not multiplicative.** Each factor contributes points
  independently and the total is just a sum. This is a deliberate
  simplification: a multiplicative or weighted model would be harder for a
  non-specialist reviewer to recompute by hand, and "auditable by hand" is
  the rubric's core design goal (see `docs/evaluation-plan.md` point 1). The
  tradeoff is that the rubric cannot express factor *interactions* (e.g. "restricted
  data is only really dangerous when combined with full autonomy") except by
  the accident of both factors independently pushing the score up. A real
  organization's rubric committee should treat this as a known limitation,
  not a hidden one.
- **Five tiers, not three.** The original three-tier version of this rubric
  (low/medium/high) collapsed two governance-meaningfully-different
  situations into one bucket: "genuinely no risk factors present" and "some
  risk factors, but still low-stakes" both scored as "low," and the single
  "high" tier had to cover everything from "somewhat concerning" to
  "should not proceed without executive sign-off." Splitting into five
  tiers — **Minimal, Low, Moderate, High, Restricted pending formal
  review** — lets the rubric express that top distinction explicitly: a
  request combining the most severe factors (restricted data, full
  autonomy, high individual impact, no human review) doesn't just need
  *more controls* than a High-tier request, it needs a **different kind of
  gate** — a named governance-committee review (`UC-14`) and an independent
  assessment (`UC-15`) that no other tier requires, before the standard
  control checklist even starts.
- **Why `restricted` means "pending formal review," not "blocked."** The
  engine deliberately never says a use case is rejected. Governance
  functions that hand out hard "no" answers from an automated tool tend to
  get routed around by business teams; a tool that instead says "this
  needs a specific, named review before it can proceed" keeps the
  governance function in the loop without setting itself up as an
  unaccountable blocker. The tier name says exactly what has to happen
  next, and the RACI at that tier (below) says exactly who has to do it.
- **Why the DPA control is tier-independent.** `external_data_sharing=True`
  always pulls in the Data Processing Agreement review (`UC-03`),
  regardless of computed tier. This mirrors real governance practice:
  certain controls are triggered by a specific fact pattern (data leaving
  the organization's boundary) rather than by an overall risk score. A
  `minimal`-tier use case that happens to share data externally still needs
  a DPA review; the rubric encodes that as an exception to the tier-based
  filter rather than trying to force it into the point system.

## 2. RACI escalation as governance intent, not just a table

`src/engine.py::build_raci` is not five independent tables — it's a single
escalation ladder, and the ladder itself is the governance statement:

| Role | Minimal | Low | Moderate | High | Restricted |
|---|---|---|---|---|---|
| Business Owner | A | A | A | A | A |
| Data Privacy | I | C | C | C | **A** |
| Security | I | I | C | **A** | A |
| Legal | I | I | C | **A** | A |
| IT | R | R | R | R | R |
| End Users | I | I | I | I | **C** |

- **Business Owner is Accountable at every tier.** Ownership never moves —
  the rubric never lets a business owner hand off accountability for their
  own use case to a governance function, even at the most severe tier.
  Governance roles get added *alongside* the owner, not instead of them.
- **Data Privacy, Security, and Legal escalate independently, at different
  points.** Privacy starts getting Consulted at Low (data questions come up
  early); Security and Legal don't get pulled in as Consulted until
  Moderate, and don't become Accountable until High. This reflects a
  real-world pattern: privacy review is usually cheap enough to do early
  and often, while formal security and legal sign-off is reserved for
  requests serious enough to justify the review cycle.
- **At Restricted, Data Privacy joins Security and Legal as Accountable —
  four Accountable roles at once, alongside the Business Owner.** This is
  the rubric's most conservative possible RACI, by design (verified by
  `tests/test_engine.py::test_raci_restricted_tier_is_the_most_conservative`).
  A single "governance committee" line item wouldn't force each function to
  independently sign off; naming all three as Accountable does.
- **End Users move from Informed to Consulted only at Restricted.** This is
  the one departure from the otherwise-monotonic "more Accountable roles as
  tier rises" pattern, and it's deliberate: at every other tier, the people
  affected by the AI system are simply told what's happening (Informed). At
  the tier reserved for the most severe combination of factors — including,
  by construction, high decision impact on individuals — the rubric asserts
  that affected parties (or their representatives) should have real input
  before the use case proceeds, not just notice after the fact.
- **IT is Responsible at every tier, never Accountable.** IT builds and
  operates the system; it is never the party the rubric holds accountable
  for whether the system *should* exist in its proposed form. That
  accountability sits with the Business Owner and, as risk rises, with
  Privacy/Security/Legal.

All of this is a *default*, not a decision. The Streamlit UI's RACI table
is fully editable before a review packet is generated — a human reviewer
can override any cell, and the engine never re-derives or corrects an
edited value. The rubric proposes; a human disposes.

## 3. Control-catalog ownership model

`data/synthetic/control_catalog.json` (15 controls, `UC-01` … `UC-15`) is
the single source of truth for what "the controls this tier requires"
means. In this prototype it's a static file anyone with repo access can
edit; in a real deployment, it needs an explicit owner and a change
process, because every entry in it is effectively a governance policy
decision encoded as data.

**Proposed ownership model for a real deployment:**

- **Catalog owner: the AI governance function** (typically a cross-functional
  body that includes Legal, Security, Privacy, and a business
  representative — not engineering alone). This function owns the meaning
  of each control, not just its wording.
- **Control-by-control sub-ownership**, since a governance function
  shouldn't be the technical authority on every control's content:
  - Security-flavored controls (`UC-06` security architecture review,
    `UC-07` vendor security questionnaire, `UC-09` incident response plan)
    — content owned by the Security team; inclusion/tier-mapping decision
    owned by the governance function.
  - Privacy-flavored controls (`UC-02` data inventory, `UC-03` DPA review,
    `UC-12` privacy impact assessment, `UC-13` retention policy) — content
    owned by the Privacy/Legal team.
  - Fairness/impact controls (`UC-08` bias evaluation, `UC-11` AI-use
    disclosure) — content owned by whichever function is accountable for
    responsible-AI practice (often a dedicated AI ethics/responsible-AI
    function, where one exists, otherwise Legal + a data science lead
    jointly).
  - Restricted-tier-exclusive controls (`UC-14` governance committee
    review, `UC-15` independent assessment) — content and process owned
    directly by the governance function; these are procedural gates, not
    technical controls, so they can't be delegated to a single team.
- **A single accountable editor of the JSON file itself.** Even with
  distributed content ownership, exactly one role (e.g. a governance
  program manager) should be the only one who actually merges a change to
  `control_catalog.json`, after collecting sign-off from the relevant
  sub-owner(s) above. This prevents the catalog from becoming an ungoverned
  free-for-all even though many people contribute to its content.

## 4. Versioning and change control for the rubric

Nothing in this prototype enforces version control beyond git history. A
real deployment needs to treat a change to the rubric's thresholds, point
values, or the control catalog's tier mappings as a **governed change to a
policy artifact**, not an ordinary code change. Proposed model:

1. **Every rubric-affecting file carries an explicit version number and
   effective date.** In practice: a `"rubric_version"` and
   `"effective_date"` field added to `control_catalog.json` (and a
   corresponding constant near `src/engine.py`'s threshold definitions),
   bumped only as part of a reviewed change, never silently.
2. **Changes go through a two-step review, mirroring the rubric's own
   escalation logic**: (a) the proposing owner (per the sub-ownership model
   above) documents the change and its rationale — what factor, threshold,
   or control is changing and why; (b) the governance function that owns
   the catalog formally approves it, the same way the rubric itself
   requires Accountable sign-off from multiple functions at its highest
   tier. A rubric change is, structurally, itself a `restricted`-tier
   decision: it affects every future use case scored against it.
3. **Changes are never applied retroactively to already-decided
   assessments.** A `decision_log.json` entry should record which rubric
   version scored it (this prototype does not do this yet — see
   `docs/limitations.md` — a production version should add a
   `"rubric_version"` field to every logged entry). This lets an auditor
   answer "was this use case correctly scored under the rules that existed
   at the time?" without re-running history through today's rubric.
4. **A standing review cadence, not just ad hoc edits.** At minimum, an
   annual review of the full rubric (thresholds, point values, and the
   control catalog) by the governance function, informed by the adoption
   metrics in `docs/production-path.md` (particularly the RACI/tier
   override rate — a high override rate is the clearest signal that a
   threshold or weight needs revisiting).
5. **Deprecation, not silent deletion, for a removed control.** If a
   control is ever retired, it should be marked deprecated (e.g. an
   `"active": false` flag) rather than deleted outright, so historical
   decision-log entries that reference its ID remain interpretable.

None of this versioning/change-control machinery is implemented in this
prototype's code — this section documents the *model* a real deployment
would need, consistent with the Roadmap in `README.md` and the fuller
detail in `docs/production-path.md`.
