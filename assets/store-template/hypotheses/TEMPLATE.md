---
id:                       # H<NNN>, monotonic, never reused — even if this hypothesis is abandoned
markets:                  # comma-separated storefront codes this change is exposed in (us,gb) — the ledger pairs rank observations to a hypothesis through this field, so an empty one means it can never be judged
status:                   # draft / queued / live / judged / abandoned
phase_at_start:           # the Phase value (e.g. P2-cold) when this went live — fixes which rigor applied, so a verdict written later is still readable
change:                   # WHAT is changing. One variable only if phase_at_start is P3-measure.
mechanism:                # WHY this change should move the outcome. The causal story, not the hope.
prediction:                # The expected effect AND by when. A number, not a direction.
kill_criterion:            # What result counts as FAILURE. Written before went_live — a criterion written after seeing data is not a criterion.
kill_criterion_written:    # date — MUST precede went_live
went_live:                 # date this change reached the live store (not the day it was submitted) — leave empty until it does
window_days:                # integer. Default 21 for a keyword change (index, then move, then stabilise). Shorter for fast-feedback changes, longer for slow ones. State the reason if it differs from the default. Never bounded by how long a data provider retains history.
primary_signal:             # rank (if phase_at_start is P2-cold) or funnel (if P3-measure)
verdict:                    # worked / no-effect / adverse / withheld — leave empty until judged
confounds:                  # list: concurrent release, seasonal peak (Jan/Sep for this app), competitor activity — empty list if none observed
---

## Reasoning

<!-- The argument for why `mechanism` should produce `prediction`. Cite `marketing/HANDBOOK.md`
     for general reasoning rather than restating it; write only what is specific to this hypothesis. -->

## Verdict reasoning

<!-- Filled in when judged. Required even for `no-effect` and `adverse` — a discarded idea without
     recorded reasoning gets re-proposed later. State what the mechanism got wrong, not just that
     it failed. Every figure cited here carries a provenance tag (references/provenance.md). -->
