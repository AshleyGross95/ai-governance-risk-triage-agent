# Demo script (60-90 seconds)

A guided walkthrough a reader can follow verbatim, either live or reading
along with a screen recording.

---

**[0:00-0:10] Orient**

"This is a demo intake tool for AI governance. A business user proposes an
AI use case, and the app applies a transparent scoring rubric to assign a
risk tier, the controls that tier requires, a draft accountability table,
and a paper trail — all before anything reaches Legal or Security."

Point out the **"Public portfolio prototype · Synthetic data"** line and
the warning banner: *"Decision support, not a legal, privacy, or security
determination."* — "Everything here is illustrative. No real company's
policy, no real employee data."

**[0:10-0:20] Show the scale**

Point at the 3-metric panel: "20 seeded example use cases, 5 risk tiers,
and 62 automated tests back every number you'll see."

**[0:20-0:35] Load a high-severity preset**

Open the "Load a seeded sample use case" dropdown, select **"AI
resume-screening assistant."** — "This is restricted-sensitivity HR data,
external candidates, fully autonomous scoring, and no human review before
a rejection is sent." Click **"Assess risk."**

**[0:35-0:55] Walk the output**

- Point at the tier: *"Risk tier: Restricted pending formal review — score
  17 out of a possible 19."* Note the red banner explaining what
  "restricted" actually gates: a governance committee review and an
  independent assessment, on top of everything a High-tier request already
  needs.
- Scroll to "Why this tier": read one or two of the plain-English factor
  sentences (e.g. *"Data sensitivity is 'restricted' (+4 pts)"*) — "Every
  point is auditable by hand from the rubric table in the README."
- Scroll to the controls table: "14 controls apply here, including a
  governance-committee sign-off and an independent third-party assessment
  that only the restricted tier requires."
- Scroll to the RACI table: "At this tier, the Business Owner, Data
  Privacy, Security, and Legal are all Accountable — the most conservative
  RACI the rubric produces."

**[0:55-1:10] Show it's editable and produces a real artifact**

Change one RACI cell (e.g. flip "End Users" from Consulted to Informed) —
"Every assignment here is a draft; a human reviewer can adjust it before
anything is final." Click **"Generate review packet"** and scroll the
resulting markdown — "This is what actually gets attached to the
governance ticket." Click **"Download packet (.md)."**

**[1:10-1:20] Show the paper trail and reset**

Scroll to the decision log at the bottom: "Every completed assessment is
appended here automatically — this one included." Click **"Reset state"**
— "This clears the form and the log view for a fresh demo run, but never
touches the underlying decision-log file; the entry we just created is
still there on disk."

**[1:20-1:30] Close**

"The rubric, the control catalog, and the RACI defaults are all
illustrative — not a certified compliance framework, and not a substitute
for your organization's actual legal, privacy, and security review. See
`docs/governance.md` for how a real organization would own and
change-control a rubric like this one."

---

**Optional extension (if time allows):** load a `minimal`-tier preset
(e.g. "Public product FAQ answering bot") right after the restricted one,
to show the score-1 end of the spectrum and how few controls and how light
a RACI it produces by contrast.
