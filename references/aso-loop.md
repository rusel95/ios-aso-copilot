# ASO iteration

Read the app's handbook for context and `state-store.md` for records. Separate a sensible metadata
change, an observed result and evidence that the change caused the result.

## Draft a prospective hypothesis

Include change, mechanism, prediction, kill criterion, exact query basket, locale/storefront mapping,
primary metric, guardrails, baseline/window, source/method and known confounds. The skill may draft
these when requested. Record when the criterion was written; do not retrofit it after seeing results.
Check prior verdicts and explain new evidence before repeating a failed idea.

Check hypothesis files and live metadata, not only STATE. A queued item may already be deployed.
Locale and storefront are different: a localization can serve multiple countries. Map the actual
exposure and shared release changes before treating experiments as independent. Multi-field
localization can be useful, but its effects cannot be assigned to one keyword or one screenshot.

## Choose queries with product relevance first

Use live metadata, real user language, visible competitor positioning, autocomplete and RespectASO.
A suggestion is a candidate, not measured volume. Match exact native term, country, provider and
observation date. Separate brand, generic, use-case and unsupported-feature terms. The app must solve
the requested job; a popular irrelevant term fails this test.

Validate title/subtitle/keyword limits in ASC. Remove unnecessary repetition following Apple's
metadata guidance, but do not assert exact tokenizer behavior for every language. Compounds, inflected
forms, CJK and Unicode limits need validation. A simulator's combination list is not an Apple index
readout. Promotional text is not a search-ranking field. Metadata relevance does not guarantee rank.

## Observe comparable evidence

A 21-day keyword window is a planning default, not proof of statistical sufficiency. Start it at
verified public exposure, not submission. Store the before/after text and dates; note gradual release
or localization differences. Allow monitoring for errors before the window ends without declaring a win.

Use a fixed query basket and consistent source, device method, depth and app identity. New or failed
queries cannot count as lost/gained ranks. `diff_snapshots.py` enforces comparability for supported JSON
snapshots; historical missing provenance is not automatically repaired. iTunes order is a discovery
proxy; a rank-primary verdict needs an appropriate, verified measurement method.

For business outcomes, compare complete periods and relevant storefront/source populations. ASC
Search can include paid ads; browse is context, not a randomized control. No ASC report supplies
organic downloads by exact keyword. Consider launch volatility, version/price changes, acquisition mix,
seasonality evidenced for this app, and competitor changes. Do not invent January/September peaks.

## Close the window before opening another

`scripts/ledger.py report` computes the state of every hypothesis from its own frontmatter, with no
judgement of its own. Its states, and what each one obliges:

| State | Condition | Obligation this run |
|---|---|---|
| judged | `verdict` set | nothing; it is closed |
| due | `went_live` + `window_days` <= today, no verdict | judge it, or record the specific missing evidence |
| open | inside the window | leave it; an early peek is not a verdict |
| not shipped | `went_live` empty | resolve the discrepancy: is it really unshipped, or shipped and mislabelled |

`went_live` is the date the change was publicly visible, never the submission date. Backfill it from
shipping evidence — the version that carried the change, and its release date — as a dated amendment
that leaves the original prediction and kill criterion untouched.

A `not shipped` row whose status says `queued` is the failure mode this pass exists to catch: a
change that shipped months ago and was never judged because the ledger still called it pending. Check
the shipped metadata package and the live listing, not `STATE.md`.

Rollback is a decision with a cost, not a reflex. An `adverse` verdict states the exact fields to
revert and the version that would carry them; a missing data point is not grounds to revert public
metadata, and neither is one bad week inside the window.

## Order the next actions by money, not by impressions

Rank of a keyword and value of a keyword are different quantities. Section C multiplies the
storefront's **net proceeds per paying subscriber** — the real Apple price record, `metrics/markets.csv`,
pulled with `asc subscriptions pricing prices list`, never estimated — by the headroom left in the
current position band. Two consequences worth stating plainly, because they invert the intuitive order:

- A high rank in a cheap storefront can be worth less than a mediocre rank in an expensive one.
  Apple equalizes on proceeds, so the spread between storefronts is large and not guessable.
- A storefront with no price record is ranked nowhere, never at zero — an unknown input must not
  quietly sort a market to the bottom.

The band weights are a declared ordering assumption printed with the output, not a measured tap
share, and the section prints no currency total. It answers "what first", never "how much".

## Judge honestly

| Outcome | Evidence required |
|---|---|
| worked | Prespecified target met, guardrails assessed, with inference strength stated |
| no-effect | Enough precision to rule out the useful effect; a small sample is not proof of no effect |
| adverse | Credible harm to the declared outcome or product guardrail; no invented all-query algorithm penalty |
| withheld | Missing or incomparable data, immature cohort, low precision or dominant confound |

A directional observation may support keeping a useful change without proving causality. State that
separately. A valid trial can remain inconclusive after 21 days. Evaluate rollback cost and current
release constraints; a missing data point is not a reason to blindly roll back public metadata.
A 100-download weekly threshold cannot replace power, minimum detectable effect and per-cell counts.
For randomized creative tests use Apple's PPO workflow and current reporting interpretation.

Sources: https://developer.apple.com/app-store/search/
https://developer.apple.com/help/app-store-connect/reference/app-information/app-store-localizations/
https://developer.apple.com/app-store/product-page-optimization/
