# The ASO iteration loop

The reasoning behind every rule in this file is `doc:HANDBOOK.md§1.3` ("Цикл ітерації — центральна
глава") — read it once for the *why*; this file is the *how*, translated into steps you execute and
checks you enforce. Per FR-035, this file cites the handbook, it does not restate its argument.

Schema and field rules for everything mentioned below (`hypotheses/*.md`, `metrics/weekly.csv`,
`metrics/ranks.csv`, `decisions.md`): `references/state-store.md`. This file is about the *process*
that produces and consumes those records, not their format.

## The five steps (`doc:HANDBOOK.md§1.3`, Крок 1–5)

1. **Hypothesis, not a guess** — draft, refuse if incomplete, check the ledger for a prior verdict
2. **One variable per iteration** — enforced only in `P3-measure`; suspended below the volume
   threshold (`SKILL.md` Step 3)
3. **Measurement window** — declared per hypothesis, never bounded by provider retention
4. **What to read in App Store Connect** — the search segment, with browse as control
5. **Verdict and next iteration** — one of four outcomes, then draft what comes next

---

## Step 1 — Hypothesis

A hypothesis needs `change`, `mechanism`, `prediction`, `kill_criterion` — all four, no exceptions
(FR-003, FR-004; field rules in `references/state-store.md`). If any is missing, refuse and name
which one. **Do not fill it in for the user** — a kill criterion the skill invents on someone else's
behalf is not a kill criterion; the entire point is that it was committed to *before* the data that
could rationalize it existed.

**Prior-verdict guard, before drafting or accepting anything** (FR-005, SC-005): search
`marketing/hypotheses/*.md` for a settled `no-effect` or `adverse` verdict on the same or a
substantially similar `change`. If one exists, refuse the new hypothesis until:
- the old verdict is cited by ID, and
- what is different this time is stated explicitly (new evidence, a changed mechanism, a changed
  app state — not just "let's try again").

Without this check the ledger is a diary nobody rereads, and the same idea comes back every quarter
wearing a new hypothesis number.

**Active-experiment collision guard (1 active hypothesis per market at a time)**:
Before drafting, staging, or applying any metadata change for a market:
1. Audit all existing hypotheses in `marketing/hypotheses/*.md` that have `status: live` or `status: staged`.
2. Map each running hypothesis to its targeted market/locale (e.g., DE, FR, US, JP, etc.).
3. If the target market ALREADY has an active hypothesis whose 21-day measurement window is currently in flight:
   - **REFUSE to stage or apply a new hypothesis for that market.**
   - Do NOT modify metadata for that market — doing so contaminates the experiment and invalidates the 21-day observation window (FR-017).
   - Instead, save the proposed change as a future idea in the **Ideas Backlog** (`status: idea` or `marketing/ROADMAP.md` / `marketing/queue.md`) with a `blocked_by: Hxxx` reference.
   - It may only be scheduled once the active hypothesis reaches its 21-day window and receives a formal empirical verdict (`worked` / `no-effect` / `adverse`).
4. Only markets with **no active hypothesis in flight** are eligible to receive metadata updates in the next release.

## Step 2 — One variable per market (Market isolation & parallel execution)

**Market isolation principle**: Each App Store storefront (US, DE, JP, UA, FR, KR, BR, ES, etc.) is a completely independent search ecosystem with its own search index, query vocabulary, competitor landscape, and audience.

- **Within one market**: exactly one variable per iteration (e.g. do not change both keywords and screenshots in US simultaneously; isolate the causal variable).
- **Across different markets**: multiple market-specific hypotheses can and should run concurrently in the same app release (e.g. up to 20–25 parallel hypotheses, exactly 1 per market: H006 for DE, H009 for FR, H010 for JP, H011 for KO, H013 for UA, etc.). Because regional App Stores are disjoint segments, they do not contaminate each other's primary rank or download signals (FR-017).
- In `P2-cold`, volume is below threshold, so rank across the market's query basket is the primary signal (Step 5 below).

## Step 2.1 — Market Query Basket & Snapshots

A hypothesis for a market is not evaluated on a single keyword in isolation. Updating metadata causes Apple to re-index token combinations across Title, Subtitle, and Keyword fields, shifting the entire search landscape for that country.

- **Query basket**: 20–100 queries per market (proportional to market weight) harvested from Apple autocomplete hints.
- **Snapshot capture**: Every audit run records a structured JSON snapshot (`marketing/reports/snapshots/rank_snapshot_YYYY-MM-DD.json`) capturing the complete state of all queries in the top-200 for each country (`our_rank`, `total_results`, `volume_proxy`, `difficulty`, `opportunity`, `top_competitors`).
- **Evaluating market hypotheses**: The verdict is judged by comparing `baseline_snapshot` (at `went_live`) against `verdict_snapshot` (at `went_live + 21 days`):
  - *Net new ranks*: count of newly visible queries in top-200 (e.g. from 4/30 to 12/30).
  - *Target cluster movement*: rank shifts for the specific cluster targeted by the hypothesis (e.g. colour-noise terms in DE, rain/sleep terms in KO).
  - *Market opportunity delta*: overall opportunity score improvement.

## Step 3 — Measurement window

`window_days` is declared when the hypothesis is written, not derived afterward. Default 21 for a
keyword change (index, then move, then stabilize) — shorter for a fast-feedback change (e.g. an
icon swap under an active PPO test), longer for a slow one (e.g. a positioning change that needs a
full ranking cycle). A non-default window is accepted with its reason recorded in the hypothesis
file (FR-011). **Never** bound the window by how long Astro or aso.dev retains history (FR-012) —
`metrics/ranks.csv` and `weekly.csv` accumulate on the skill's own cadence regardless of what any
vendor keeps, so provider retention limits only how much can be back-filled on first use.

No verdict before `went_live + window_days` has elapsed. Asked early, state the days remaining and
stop there — do not hedge toward an early read.

## Step 4 — What to read

`P3-measure`: App Store Connect analytics, **Source Type = Search**, for the tracked markets
(US/GB/DE/UA). Segment is mandatory at entry (FR-006) — a row without `search`/`browse` is rejected
by `references/state-store.md`'s rules before it ever reaches a verdict, not caught here after the
fact.

`P2-cold`: rank position from the tracker (or the free-endpoint degraded path — see below), not the
funnel. Position is observable at any volume; impressions and CVR below ~100/week are noise
(`doc:HANDBOOK.md§1.2`, and research.md §4's correction to the handbook's own tooling-purchase
timing — rank tracking is the one exception to "wait for volume before buying tools").

## Step 5 — Verdict

Four outcomes (FR-005, FR-016; full table in `references/state-store.md`):

| Verdict | Condition | Action |
|---|---|---|
| `worked` | primary signal moved as predicted, CVR not down | keep; draft next |
| `no-effect` | nothing moved past the kill criterion | roll back; **record why the mechanism was wrong**, not just that it failed |
| `adverse` | impressions/rank up, **CVR down** | roll back — treat as harmful, not partial credit: non-converting traffic lowers ranking across *all* queries, not only the new one |
| `withheld` | window closed but data missing, or a confound dominates | name exactly what's missing; never guess to fill the gap |

**Rank-primary in `P2-cold`** (FR-026): the verdict rests on rank movement, with the reason stated
inline ("below 100 downloads/week, funnel figures are noise — this verdict rests on rank"), not on
funnel figures at all. Do not compute a funnel-based verdict "for reference" alongside it — a
precise-looking number computed from noise is worse than no number.

**Segment discipline** (FR-015): a keyword-change verdict is computed from the **search** segment
only. Always report the browse segment alongside it as the control — if total downloads rose but
browse carried the rise while search stayed flat, the hypothesis gets `no-effect`, and the growth is
attributed to browse, not credited to the keyword change that didn't move its own segment.

**Confounds** (FR-017): name any of the following present in the measurement window, and withhold
the verdict if one plausibly dominates the result rather than merely coexisting with it:
- a concurrent app release (a version bump can move rank/CVR for reasons unrelated to the hypothesis)
- a seasonal peak — this product has **January and September** peaks; a week-over-week comparison
  spanning one of them is flagged, not compared as if the world were flat
- plausible competitor activity — a rank or CVR drop with no corresponding action on this app's side
  is offered as a possible external cause, not treated as a failed hypothesis

**Never attribute organic traffic to a keyword** (FR-025, SC-006). No source produces that number —
Apple's Discovery and Engagement report has event type, country, referrer, source, OS, page type,
user action and date as dimensions, and **no search-term dimension**; the only first-party
search-query data Apple publishes is the Apple Ads search-terms report, which covers **paid**
queries only (`research.md §3`). Any per-keyword claim here is inference from rank movement plus
total search-segment movement, and must be labelled as inference when stated — never as a measured
fact. Asked directly for a per-keyword download count, say plainly that no source produces it
(`references/provenance.md` — this is the case the provenance waist exists for: the claim has no
available source kind).

**Tracker unavailable** (FR-031): if Astro's local MCP isn't reachable, say so and continue with
reduced confidence rather than erroring out. **Never** substitute iTunes Search API positions as if
they were real rankings — that index is measurably different from the real App Store index
(`research.md §4`); it's fine for discovery, not for a position a verdict rests on. Any verdict that
would have rested on a stale rank observation states how stale it is (age, from the `source` tag on
the `ranks.csv` row) and lowers confidence accordingly rather than proceeding as if the position were
current.

---

## Storefront Conversion Funnel Guardrails (TTR & CVR Integration)

While rank movement is the primary signal in cold phases (`P2-cold`), **Storefront Conversion Efficiency** is the essential commercial and algorithmic guardrail. High impressions without conversion hurt the app.

- **The Low-Intent Traffic Trap (`adverse` verdict)**: If adding broad keywords drives a surge in impressions (+100%) but Tap-Through Rate (TTR) plunges below 1.8% or Overall ASO CVR drops by >15%, the verdict is **`adverse`** — Apple's search ranking algorithm penalizes listings with poor conversion rates by gradually degrading rankings across *all* queries.
- **Run the Funnel Visualizer**: Run `python3 $SKILL_DIR/scripts/funnel_visualizer.py --store $STORE` at every verdict checkpoint.
- **Triage Leaks**: Refer to `references/funnel-analytics.md` for peer benchmarks and diagnostic root causes (Search Card TTR vs Product Page CVR vs Paywall CVR).

---

## Keyword selection method (FR-028, FR-029, SC-009)

Every candidate you propose carries three things, always, never just the word: its **relevance**
judgment, its **popularity/difficulty where known**, and why it's expected to be **winnable** at the
app's current standing. A word proposed by association alone — "users searching for X might like
this app" without checking any of the three — is not a candidate, it's a guess wearing a keyword's
clothes.

**Four candidate sources:**

1. **Own vocabulary** — every word already in the locale's keyword field, name and subtitle. Not
   knowing whether you already rank for what you claim is the first thing to check, not the last.
2. **Competitor metadata** — keywords implied by competitor names/subtitles surfaced via the iTunes
   Search API (`references/commands.md`).
3. **User review language** — words real users use to describe the app's problem, from
   `asc reviews list`.
4. **App Store autocomplete** — `MZSearchHints` (`references/commands.md`), ordered by real search
   popularity. This is where TARGET candidates (head terms not yet ranked for) come from — harvested,
   never invented.

**Scoring**: relevance × popularity × difficulty. **Ordering**: long-tail before head — a winnable
3-word phrase beats an unwinnable 1-word term at the app's current authority. **Field mechanics**:
keywords are combinable tokens, not fixed phrases (Apple's indexer recombines them), so do not spend
characters on a phrase when the same reach comes from its tokens placed once each; do not duplicate a
token that's already spent in the app name or subtitle (those are separately indexed and higher
weighted — see Indexed surface below) inside the keyword field too.

**The conversion veto** (FR-029) — every candidate passes a conversion test before proposal: *would
someone who searches this term be satisfied by this app?* A term that would bring non-converting
traffic is **rejected with that reason recorded**, never silently dropped, because that traffic
doesn't just fail to convert on its own search — it lowers ranking across every query this app
targets. High popularity does not override a failed conversion test.

## Indexed surface (FR-030)

Account for every field Apple indexes, not only the keyword field, when proposing a change:

| Field | Characters | Indexed? |
|---|---|---|
| App name | 30 | yes — highest weight |
| Subtitle | 30 | yes — second highest |
| Keyword field | 100 | yes |
| In-app purchase display names | 30 each | yes |
| In-app event titles | 30 | yes |
| Developer name | — | yes |
| Description | 4000 | **no** |
| Promotional text | 170 | **no** |

Flag unused or wasted indexed capacity as a candidate in its own right. Known example as of this
skill's build: the subscriptions are named "Pro Monthly" / "Pro Yearly" — roughly 21 indexed
characters spent on words nobody searches (`live:asc subscriptions list`, re-check before treating
as current). Small individually — a low-weight field — but free to fix and needs no new app version,
so it costs nothing to queue.

Screenshot caption text has been OCR-extracted by Apple since June 2025, but independent testing
found little evidence of broad indexing from it — write captions for humans, not for the indexer.

Since 30 July 2025, custom product pages (CPPs) can be linked to keywords from the keyword field and
served **organically** in search (limit raised 35→70 per app) — this moved CPPs from a paid-only tool
into core ASO. Each CPP needs its own screenshot set; which keywords deserve one is a traffic-data
question, covered in `references/playbooks.md`, not decided here.
