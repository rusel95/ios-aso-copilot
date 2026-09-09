---
name: ios-marketing-ops
description: >
  Post-launch marketing operations for this repo's App Store app: ASO / keyword iteration, App
  Store release readiness, Apple Ads setup and economics, product-page experiments, reviews,
  content backlog. Reads a persistent state store from the current repo's own marketing/ (app
  identity and numbers are per-repo, never shared across apps) and answers "where am I, what's
  next" — never starts from zero.
  Triggers on: ASO, App Store keywords, App Store Connect status/readiness, Apple Ads / Search Ads,
  marketing hypothesis or iteration, weekly funnel numbers, keyword rank, product page experiment,
  review replies, marketing content backlog, off-store traffic, reddit, threads, twitter, campaign link,
  channel hypothesis, ugc, tiktok, reels, shorts, video script — and the Ukrainian equivalents: маркетинг, ASO, ключові слова, статус релізу,
  Apple Ads / реклама, гіпотеза, ітерація, ранжування, відгуки, де я і що далі, що робити далі,
  запусти рекламу, онови позиції, проведи мене по кроках, зроби ітерацію в авто-режимі,
  зовнішній трафік, реддіт, тредс, де запостити, кампанія, трафік з соцмереж, юджісі, тікток, рілс, сценарій відео.
argument-hint: "[status | manual | auto] [free text]"
metadata:
  version: 1.3.1
---

# iOS marketing operations

Keep the app's marketing work continuous: inspect the existing evidence, reconcile what is actually
live, improve the next decision, and record changes. A report is not evidence that marketing worked.
Read `references/provenance.md` before factual claims. Use `references/respectaso.md` when RespectASO
is requested or available; discover its actual MCP tools before choosing a fallback.

## Resolve the app and the single state store

- `SKILL_DIR` is the real directory containing this skill (resolve symlinks).
- From the app repo run `git worktree list --porcelain`. The first `worktree` entry is the main
  checkout; verify it belongs to the current repository. Do not infer this from missing branch brackets.
- `STORE` is that checkout's `marketing/`, shared by all its worktrees. Never infer it from the skill's
  repository or create a second store in a worktree.
- Read `config.md` for the exact App ID and working version. Read `STATE.md`, `queue.md`, hypotheses,
  recent decisions, metrics and the relevant handbook sections. State is a cache, not a data source.
- Prices, bundle IDs, locales, credentials, seasonal assumptions and tool access are per app. Never
  carry them from a previous project. Missing identity means report that gap before app-specific API calls.
- Keep one global skill installation. Project links may point to it; do not copy skill directories.
  Preserve unique local additions before replacing a copy. The installer and agents must resolve links.

## Open every run with the ledger, before proposing anything

The first command of any invocation — `status`, `manual` or `auto` — is:

```bash
python3 "$SKILL_DIR/scripts/ledger.py" --store "$STORE" report
```

Three sections in a fixed order: what is already live and what happened to it, what moved, what to
do next. **Do not draft a new hypothesis before section A is on screen.** Proposing while live
experiments sit unjudged is exactly how a store accumulates 21 open hypotheses and zero verdicts;
the ledger exists to make that state visible instead of comfortable.

- **A · Hypothesis ledger.** Every hypothesis carries a state: `judged` / `due` / `open` /
  `not shipped`. `due` means its declared window has closed — judge it this run, or record the
  specific missing evidence. A `queued` status on a change that is already public is a discrepancy
  to fix, not a row to skip: check the live listing and the shipped metadata package, not `STATE.md`.
  `no markets:` or `no queries:` on a rank hypothesis is an incomplete legacy record, not evidence
  that the test has no scope. Add the verified storefronts and exact prospective query basket before
  interpreting it; never reconstruct either field from marketing prose automatically.
  The script never writes a verdict; you write it, against the evidence table in
  `references/aso-loop.md`. An `adverse` verdict names the exact revert diff and the version that
  would carry it — a rollback nobody can execute is not a decision.
- **B · Progress and regress per key.** Every tracked key, paired first-to-latest. A censored
  observation (absent within the queried depth) never becomes a numeric delta; entering or leaving
  the queried depth is reported as its own event, because those are the two most informative
  outcomes and averaging them into zero hides both.
- **C · What to do next.** Ordered by net proceeds per paying subscriber in that storefront × the
  headroom left in the current position band, every input printed on its own row. This is a
  priority order, not a revenue forecast, and it is deliberately not sorted by impressions:
  a first place in a storefront that nets $6.37 a subscriber is worth less than a fifth place in
  one that nets $29.88. Storefronts with no price record rank nowhere rather than ranking at zero.

Drafting the next one is the same command with `draft --market X --queries "a; b"`. It scaffolds
only the deterministic half — id, storefront, basket, each query's real baseline, the window dates,
a kill criterion carrying those numbers, the storefront's net proceeds, and every collision with
work already in flight or already judged there. **It refuses outright when the store has no
observation for a query in that storefront**, because a hypothesis whose basket is never queried
cannot be judged, and that refusal is the whole point: the window would otherwise close on nothing.
`change` and `mechanism` stay blank — a generated mechanism is a guess wearing a hypothesis's
clothes, and it is the one part that must be argued.

The ledger's inputs are `$STORE/metrics/ranks.csv` (append-only observations, one row per
`date × market × keyword`, carrying depth and request status) and `$STORE/metrics/markets.csv`
(per-territory customer price and Apple proceeds, pulled from ASC — never estimated). Refresh the
first with one command — `ledger.py refresh --bundle <id>`, which re-queries the basket `ranks.csv`
already holds and ingests the result; add `--failed-only` to pick up what a rate limit ate. Apple
documents the Search API at roughly 20 calls a minute and 429s above it, so the default 3s between
queries is not a knob to turn down: at 1s more than half the queries came back as failures. Refresh
`markets.csv` when prices change.

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
again for permission already given. If an action cannot proceed, name the specific missing condition.

## Reconcile release status separately from measurement readiness

Read `asc versions list --app "$APP_ID" --platform IOS` before interpreting `asc validate`.
Track the **live version** and **working/review version** separately. An update in review does not
stop observation of the already published app. `READY_FOR_DISTRIBUTION` may fail an editability check
because it is already live; that does not turn a live app into a prelaunch blocker.

Use P0-prelaunch when no version is live, P1-review for the candidate's review status, and P2-cold or
P3-measure only with available measurement evidence. If metrics are absent, say `live; volume unknown`.
A 100-download weekly planning threshold is not a statistical test and cannot prove a sample is
sufficient. Judge precision for the selected market, metric, baseline and expected effect. Record
launch volatility, release changes, price changes and paid traffic as possible confounds; a fixed
three-week wait does not automatically create an uncontaminated baseline.

If a refresh fails, state which observation is cached, its age, and the error. Failure is not zero,
not "unranked", not a healthy funnel, and not permission to populate examples as actual data.

## Status output

Give a compact account of live/candidate versions, open ASO and channel hypotheses, observed metrics
with units and dates, gaps in the ledger, pending actions, and one useful next step. Use
`scripts/funnel_visualizer.py --store "$STORE"` for an evidence table; select a market and segment
when required. Do not infer page conversion, paid subscribers, source shares or bank payouts from
unjoined totals. Do not diagnose a bottleneck from a generic benchmark.

## One execution cycle

1. Verify identity and live/candidate versions. Reconcile stale state within the authorized edit scope.
2. Fetch the weekly data that is accessible. Save source exports, complete periods, units, filters,
   timezone and recording time. Missing fields stay blank with a reason. Never invent a baseline.
3. Refresh a fixed query basket. Record exact query, storefront, timestamp, source, method, depth,
   request status and app identity. Keep new discovery queries separate from paired comparisons.
4. Review hypotheses whose declared windows have closed. Use `references/aso-loop.md`. Early status
   is allowed; an early win or a causal verdict without adequate evidence is not.
5. Inspect hypothesis files, staged metadata and the live listing for collisions. Include queued
   changes that may already have shipped. Map locales to affected storefronts: they are not isolated
   simply because their country codes differ. Preserve the original prediction and add dated amendments.
6. Prepare the next justified change. Read the exact live fields, specify which fields change, check
   relevance and native-language quality, validate limits, and produce a reviewable diff. Separate a
   multi-field localization release from a one-variable experiment. Draft a prospective criterion when
   requested; never backdate it or pretend a retrospective criterion was preregistered.
7. Complete already-authorized actions. Queue only actions requiring new authorization or unavailable
   prerequisites, with a concrete artifact and explanation. Do not let one blocker halt independent work.
8. Update state, decisions and references consistently; report done, missing evidence and next action.
9. **Schedule verification in TickTick.** When hypotheses are sent to release (or when an App Store version with staged hypotheses is submitted for review), automatically create a scheduled verification task in TickTick for the end of the measurement window (e.g. went_live + window_days). Multiple hypotheses from the same release or window are batched into a single task in project `🎛Hush White Noise` (`66bb310904da5140ff7af08a`) with target positions, baselines, and CLI command to run.

## Evidence rules that affect decisions

- RespectASO `popularity` can mix Apple data and an internal fallback. Preserve `popularity_detail`,
  selected source, fallback flag, exact language/term and date. Scores do not transfer across translations.
- iTunes API order is discovery evidence. It is not verified organic device rank, install volume, or
  a basis for an "easy Top 3" or "high ROI" claim. The bundled rank script no longer fabricates these scores.
- Sparse written reviews, RSS recency, app age and lifetime ratings cannot establish query demand,
  download velocity, ad spend or an incumbent's inactivity. No formula promises a rank from N reviews.
- Brand terms, competitor brands and relevant generic terms belong to different research groups.
  Rank for our own name does not prove generic demand or brand awareness.
- Apple Ads query reports describe paid traffic; ASC Search can include ads. Organic installs per
  exact keyword are not directly observed in ASC. Browse is context, not a randomized control.
- Product claims must match shipped behavior. Reject keywords implying unsupported features. Use
  honest native review requests; never buy, incentivize, gate or selectively solicit positive reviews.
- A 21-day window is a scheduling default. An inconclusive result can remain inconclusive after it.
  Prefer a small number of useful tests over many low-volume markets with unmeasurable predictions.

## Reference map

| Need | Read |
|---|---|
| Claim sources and uncertainty | `references/provenance.md` |
| RespectASO tools and data boundaries | `references/respectaso.md` |
| Formats and append rules | `references/state-store.md` |
| Closing a window, rollback, priority order | `references/aso-loop.md` |
| ASC commands and external actions | `references/commands.md` |
| Keyword selection and experiment verdicts | `references/aso-loop.md` |
| Metrics and denominators | `references/funnel-analytics.md` |
| Paid acquisition scenarios | `references/apple-ads.md` |
| PPO, CPP, reviews and content | `references/playbooks.md` |
| Off-store channels | `references/channel-playbooks.md` |
| Short video scripts and briefs | `references/ugc-playbook.md` |
| Per-app teaching and reasoning | `$STORE/HANDBOOK.md` |
| Missing capabilities and acceptance criteria | `ROADMAP.md` |

## Bundled scripts

All use the Python standard library and provide `--self-check`. Run only what the task needs.

- `ledger.py`: the run-opening report above; `ingest` appends a snapshot to `metrics/ranks.csv` and
  refuses any position deeper than the result list that query returned — a value carried over from an
  older snapshot is not an observation.
- `ledger.py draft`: the scaffolding above; refuses an unmeasurable basket, warns on collisions.
- `ledger.py refresh`: re-queries the tracked basket per storefront and ingests it; `--failed-only`
  retries what a rate limit ate. Every command reports the store rows it could not use, not just
  `report`.
- `funnel_visualizer.py`: observed counts with explicit absence; no automatic health or cash estimate.
- `rank_audit.py`: iTunes discovery snapshots, exact bundle identity and per-query error status.
  Supply `--bundle`, `--niche` and target `--markets`; existing seed profiles are examples, not app identity.
- `diff_snapshots.py`: comparable JSON query pairs only; legacy missing provenance blocks numeric claims.
- `harvest_keywords.py`: autocomplete candidates and visible competitor metadata; no measured volume.
- `economics.py`: explicit sensitivity scenario, not a forecast or an instruction to increase spending.
- `campaign_link.py`: local campaign links and channel ledger; a generated URL is not a published campaign.

Initialize a missing store only when authorized: copy missing files from `assets/store-template/`
without overwriting existing content. Fill in the app's identity before running app-specific commands.
