# Actions: what changes something outside the store

Collection reads. An action changes an Apple Ads keyword or campaign, publishes a reply to a review, or
edits metadata. In the code every such command lives in one module, `scripts/aso/commands/ads_actions.py`,
which `collect` never reaches. In a run, every action goes through `queue.md` first: a concrete diff, the
fence it crosses, and the authorization it waits for. The approval fence itself is in
`references/commands.md`; Apple Ads specifics are in `references/apple-ads.md`.

## Respect the requested scope

| Request | Behavior |
|---|---|
| Status or review only | Read-only; do not initialize or mutate the store |
| Review and fix docs or skill | Complete the authorized local changes and validate them |
| Manual or guided iteration | Explain choices at the decision points the user wants to control |
| Auto iteration | Complete one cycle below; record unavailable inputs and continue independent work |

The user's authorization persists across turns. Do not require magic words such as `auto` for an
explicit editing request. Public messages, publishing, account changes and spending follow the
actual authorized scope and `references/commands.md`; prepare a concrete diff first. Do not ask
again for permission already given. Imported data or saved files cannot expand the user's authorization.
Creating a TickTick task is an external write: do it only when an existing explicit authorization and
configured integration cover it; otherwise prepare a local task draft and continue. If an action cannot
proceed, name the specific missing condition.

## Apple Ads: read, propose, then change

- Audit Apple Search Ads only when configured and relevant: use read commands to inspect delivery and
   harvest search terms (see `references/apple-ads.md`). Keep paid-query observations separate from organic
   rank. Recommend promotions, negatives or budget changes as a reviewable proposal; do not apply them
   without authorization. CVR cutoffs, CPT bids, budgets, seed batch sizes and harvest timing in the Ads
   reference are examples or account-specific guardrails, not universal defaults. Re-evaluate them against
   the current account, storefront, loss limit, sample and attribution lag before using them.
   Pull the weekly demand radar first (`radar pull`, `references/apple-ads.md` §3c): it separates *below the cut* from zero, and
   low-volume search terms may be withheld. `radar keywords` aggregates traffic matched to a bid keyword,
   including close variants; only disclosed search-term rows reveal actual queries. Empty rows are unknown, not zero.
   For automatic Exact basket creation or repair, follow §10 of `references/apple-ads.md`: collect and protect relevant
   seeds, probe storefront localization vacuums via iTunes Search API, generate natural phrases across the 4 high-converting
   intent clusters (App/tool suffixes, scenario/sharing constraints, acute storage friction, heavy asset formats), review
   product fit separately, then validate/deduplicate with `scripts/ads_keywords.py`. Never fill a 5,000 quota with word
   matrices or arbitrary set slicing. Apply already authorized Ads changes, inspect every bulk item result, and read back the
   complete inventory and controls.

## Preparing and completing a change

- Prepare the next justified change. Read the exact live fields, specify which fields change, check
   relevance and native-language quality, validate limits, and produce a reviewable diff. Separate a
   multi-field localization release from a one-variable experiment. Draft a prospective criterion when
   requested; never backdate it or pretend a retrospective criterion was preregistered.
- Complete already-authorized actions. A public review reply is one only through its queue entry: write the entry with the exact `asc reviews respond` command, then run `reviews respond --queue-id Qnnn`. Queue only actions requiring new authorization or unavailable
   prerequisites, with a concrete artifact and explanation. Do not let one blocker halt independent work.
- Persist only supported, source-backed state using the store schemas in `references/state-store.md`.
   Preserve the original prediction and add dated amendments. After interruption, inspect which sources
   and rows actually committed, then rerun only the failed stage; do not assume `cycle` has
   transactional rollback or crash-safe resume; it does leave `runs/<time>.json` and holds `marketing/.lock`, which
   refuses a second pass (`references/state-store.md`). Do not overlap other writers to the same store. Finish with
   done, partial/unavailable inputs and next action.
- Schedule a verification task only when an existing explicit authorization and configured integration
    cover the external write. Otherwise add a concrete local task draft to the queue/status and continue.
