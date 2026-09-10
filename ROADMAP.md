# ASO capability roadmap

Open work only. Completed changes belong in [CHANGELOG.md](CHANGELOG.md).
Updated 2026-09-10 after a handbook-to-roadmap coverage audit. A documented playbook is not an implemented integration.
App IDs, credentials, prices and event names belong in each app's store, not this global roadmap.
The practical teaching companion for an app is its own `marketing/HANDBOOK.md`.
An idea already enforced by the skill or explained in a reference is not duplicated here; this file tracks
only the missing capability needed to operationalize it.

## P0 Make observations trustworthy

| ID | Capability still missing | Acceptance criterion | Dependency |
|---|---|---|---|
| R-29 | RespectASO business tools verified end to end | Active licensed session; exact app identity; one Apple value, one fallback and one error saved with raw source detail | User's existing license/access; no purchase assumed |
| R-23 | ASC Analytics import | Reuse existing request; paginate reports; ingest complete periods with source/territory/unit/timezone; reconcile totals to ASC | Account read access |
| R-28 | Metric schema and corrections | Explicit unique/total units, territory, date window, report ID and corrected-row selection; never sum overlapping unique populations | R-23 |
| R-30 | Hypothesis exposure reconciliation and collision control | Compare staged and live metadata to each hypothesis; persist `markets`, prospective `queries`, public start, exact diff, locale exposure, confounds and one-material-change collision state per market/intent cell; partial implementation distinguishable | ASC metadata reads |
| R-13 | Scheduled paired query history | Fixed basket, app identity, method/depth/source/status/timestamp per row; errors and unqueried terms excluded from deltas | Verified tracker method |
| R-37 | Competitor observation quality and listing timeline | Exact app ID; dated metadata/creative snapshots; preserve RSS error, pagination and coverage; written reviews distinct from ratings; no demand/velocity inference from missing feeds | Independent sample verification |

Basic honest metric rendering and removal of fabricated rank/ROI scoring have shipped. These do not
close R-23/R-28/R-13: they do not create real analytics, a tracker, or an automatic data pipeline.

## P1 Make fewer and better tests

| ID | Missing approach | Concrete first deliverable | Done when |
|---|---|---|---|
| R-31 | Intent and locale research | Matrix of job, native term, app capability, storefront, served locale and demand evidence | Two priority markets reviewed by a fluent reader, checked in the app UI and read back from live ASC; misleading feature terms rejected |
| R-32 | Experiment design and power | Prospective primary metric, useful effect, allocation, window and guardrails | Sample/duration feasibility calculated per cell; inconclusive is a supported outcome |
| R-33 | Creative testing with PPO | One real first-screenshot, icon or honest App Preview contrast with substantiated value and actual UI | Validated localized assets, feasible duration, approved test and archived result; a preview is used only when it clarifies the product |
| R-34 | Intent-specific CPP and deep links | Compression-video page and storage-saving page, with distinct relevant keyword combinations | Public pages verified; iOS 18+ route and older-OS fallback tested; page analytics available |
| R-10 | Apple query demand source | Apple popularity and/or actual paid-query observations with dates and source details | Missing/censored values preserved; no monthly-volume conversion invented |
| R-21 | Apple Ads pilot preparation | One-market exact-query research plan with hard total loss cap and stop rule | Approved plan launched, spend/installs/quality read back and reconciled |
| R-26 | Paid-query reporting | Search-term rather than only bid-keyword reports; attribution windows and new/redownload definitions | Paid acquisition analyzed separately from ASC Search totals |
| R-35 | Review language and quality loop | Classify real objections; native neutral prompts after a successful user outcome | Product issues feed backlog; replies are drafts until authorized; no incentives or review gating |
| R-40 | External ASO tool or tracker evaluation | Write the blind spot, concrete decision, alternative already available in the skill, data export/retention requirement, one known-fact validation and stop rule | A single trial answers its declared question without turning a vendor score into evidence or creating a duplicate source of truth |

PPO tests creative, not keyword text. CPP comparisons need an allocation strategy before being called
an A/B test. Do not create many pages merely because Apple supports them. Research budgets buy
information; scale budgets require mature observed economics.

## P2 Connect acquisition to product value

| ID | Missing approach | Acceptance criterion |
|---|---|---|
| R-27 | In-app activation measurement | App-specific events for first success, time to value, failure and paywall exposure; consent and denominator documented |
| R-24 | Subscription cohort analysis | Trial starts, completed trials, paid conversion, renewals and refunds segmented by plan/country/acquisition cohort |
| R-25 | Proceeds reconciliation | Sales, estimated proceeds, refunds and payments kept separate and checked against source reports |
| R-36 | External content and web discovery | A relevant helpful page/video, campaign token or CPP, and measured qualified visits; no view-to-install attribution invented |
| R-38 | Lifecycle, seasonal, In-App Event and editorial experiments | Real user need/event, appropriate eligible Apple surface, localized assets, baseline and stop rule; skip manufactured events |
| R-39 | Bounded automated marketing runs | Use existing scheduler; saved inputs and partial failures; recheck live state; notify only actionable changes; never schedule overlapping material tests in one market/intent cell |
| R-41 | Attribution-stack escalation | Name the paid decision ASC, campaign links and existing product analytics cannot answer; introduce an MMP only when multi-channel spend or unresolved attribution ambiguity makes that gap material; reconcile source definitions, deep-link/campaign rules and downstream quality without claiming organic keyword attribution |
| R-42 | Paywall and pricing experiment readiness | Separate the price/paywall treatment from acquisition and product changes; declare audience, cohort, effect, guardrail and rollback; read mature proceeds, refunds and retention by the selected cohort before a scale decision |

For a utility app, time to first successful user outcome and trust can be more informative
than daily use. Trial duration, plan price and retention assumptions must be refreshed per app.

## Lower priority engineering backlog retained

- R-11: calibrate any future search proxy against a suitable reference. Until then label it discovery;
  retire unsupported claims such as a known “±300%” accuracy range.
- R-12: rate limits and bounded retries with explicit partial-run/error records; no success-shaped empty data.
- R-17: wire verified observations into the cycle after R-13/R-29; do not restore forecast leaderboards.
- R-18/R-19: npm publication or additional packaging only when distribution demand exists.
- R-20: additional progress UI only if existing per-market progress is insufficient.
- R-22: review reply drafting; retain author approval for public responses.

## Operating order for a target app

First populate the evidence ledger and verify tool access. Then reconcile open hypotheses with actual
release exposure and native-language quality. Select one or two high-relevance market/intent cells.
Use creative or paid-query research only with an explicit measurable question. Expand locales and
spend after those observations justify it. Every item above has a deliverable; none is an automatic
instruction to buy software, publish assets or spend money.
