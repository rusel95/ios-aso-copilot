# The state store

**This file is the runtime authority.** `specs/013-marketing-ops-skill/data-model.md` is the design
record the plan was built from; if the two ever disagree, this file wins, because it is what you
actually read at run time. Schema changes are made here first and back-ported there — never the
reverse.

## Location — read this before touching any path

The store is `marketing/` at the repository root, **always resolved to the main checkout of
whichever repo the session is actually in** — `$MAIN_CHECKOUT/marketing/`, computed live by
`references/collect.md` (*Resolve the app and the single state store*: the first entry of `git worktree list`). Never
`$PWD/marketing/`, never a path hardcoded to any one app's repo, never relative to wherever this
session happens to be running. A repo that runs many concurrent git worktrees needs this doubly: a
session started in one worktree must still read and write the *same* store as every other session
in that repo — never a copy under the worktree, and never another repo's store. See `references/collect.md` for
the resolution logic — do not "simplify" it to a relative or literal path, that is precisely the bug
this exists to prevent.

```text
marketing/
├── config.md            this repo's App Store Connect app id + version · static, never rewritten
├── STATE.md            written by the export from data/ · read first · holds no authority of its own
├── decisions.md         append-only
├── queue.md             pending approvals · entries stay when executed (`reviews respond` appends "Qnnn approved, executed" to `decisions.md`) and are removed when abandoned
├── hypotheses/
│   ├── TEMPLATE.md
│   └── H001-<slug>.md   one file per hypothesis
├── metrics/              append-only CSV series, one file a source (listed below)
├── data/                 written by `export`: what the page shows, and nothing else
├── public/               written by `build`: index.html
├── keywords/             tracking lists, one file per market (exists already)
├── HANDBOOK.md           the reasoning layer — cite it, never copy it (exists already)
└── README.md             (exists already)
```

Two formats, chosen by shape: **CSV for time series** (append a row, never rewrite a row), **Markdown
for records that carry reasoning** (a hypothesis is an argument, not a row). Both must stay readable
and hand-correctable in a plain text editor — a store the user cannot fix by opening it goes wrong
silently.

**Never rewrite a CSV row.** A correction is a new row with a later `recorded`/`date` and a note —
history is a ledger, not a spreadsheet cell.

## Provenance is shared vocabulary

Every `source` column below uses the closed vocabulary in `references/provenance.md`. Read that file
first; this one just names which column carries the tag in each file.

## Phase

Not stored as an entity — **computed fresh on every run**, then cached into `STATE.md` for display
only. `references/collect.md` (*Reconcile release status*) owns the detection logic. When the cache disagrees with a live check, the live check
wins and the disagreement is shown, never silently repaired.

Track live version, candidate version/review status, and measurement readiness separately.
An update in review does not make the live app unmeasurable. Missing weekly data means volume is
unknown. P2/P3 are planning labels; 100 downloads/week and three launch weeks are not significance
or baseline-validity tests. See `references/collect.md` for current detection.

## Hypothesis — `hypotheses/H<NNN>-<slug>.md`

One file per hypothesis. `<NNN>` is monotonic and **never reused**, including for abandoned
hypotheses — a discarded idea keeps its number so a later reference to it stays unambiguous. Start
from `$SKILL_DIR/assets/store-template/hypotheses/TEMPLATE.md`, which carries every field below with inline
guidance.

| Field | Type | Rule |
|---|---|---|
| `id` | `H001`… | monotonic, never reused |
| `markets` | comma-separated storefront codes | exact storefront exposure; required for rank hypotheses |
| `queries` | semicolon-separated exact queries | prospective fixed basket; required when `primary_signal` is `rank` |
| `status` | `idea` / `draft` / `queued` / `staged` / `live` / `judged` / `abandoned` | |
| `phase_at_start` | a Phase value | which rigor applied — fixes how an old verdict should be read |
| `change` | text | **what** is changing — one variable only when `phase_at_start` is `P3-measure` |
| `mechanism` | text | **why** it should work — the causal story |
| `prediction` | text + number | the expected effect **and** by when |
| `kill_criterion` | text + number | what counts as failure |
| `kill_criterion_written` | date | must precede exposure; use timestamps if both are on one date |
| `went_live` | date or empty | the day the change reached the **live store**, not the day it was submitted |
| `window_days` | integer | declared per hypothesis, default 21 for a keyword change; shorter for fast feedback, longer for a slow mechanism; never bounded by a data provider's retention |
| `primary_signal` | `rank` / `funnel` | `rank` if `phase_at_start` is `P2-cold`, `funnel` if `P3-measure` |
| `verdict` | `worked` / `no-effect` / `adverse` / `withheld` | absent until judged |
| `confounds` | list | concurrent release, seasonal peak, competitor activity |

**Validation, enforced at entry, not at verdict time:**

- `change`, `mechanism`, `prediction`, `kill_criterion` must all be present. Refuse a hypothesis
  missing any of them, name which is missing, and draft prospectively when requested; never backdate a criterion after seeing outcomes.
- `markets` and, for rank hypotheses, `queries` must be explicit. A legacy file without them remains
  visible in the ledger as malformed; do not infer experimental scope from free-form prose.
- A criterion must be recorded before exposure. A retrospective correction is a dated amendment, not a preregistration. Keep the historical record and mark evaluation observational or withheld.
- No verdict before `went_live + window_days` has elapsed. A window shorter or longer than the
  default is accepted, with the reason recorded in the file.
- **Exposure rule**: inspect all hypothesis files and live metadata, including queued items. Map locales to storefronts and shared release changes before claiming independence. Record partial deployment and confounds.
- **Prior-verdict guard**: before drafting or accepting a hypothesis, search `hypotheses/` for a
  settled `no-effect` or `adverse` verdict on the same change. If one exists, refuse until it is
  cited and what has changed since is stated. Without this check the ledger is written but never
  consulted, and the same idea returns every quarter.

**Verdict outcomes:**

| Verdict | Condition | Action |
|---|---|---|
| `worked` | primary signal moved as predicted, CVR not down | keep; draft the next hypothesis |
| `no-effect` | sufficient precision rules out the useful effect | record evidence; sparse data is not proof that the mechanism was wrong |
| `adverse` | credible harm to a declared outcome or guardrail | evaluate a justified rollback; no assumed all-query ranking penalty |
| `withheld` | window closed but data missing, or a confound dominates | name what's missing; do not guess |

## Channel Hypothesis — `hypotheses/C<NNN>-<channel>-<slug>.md`

One file per external traffic experiment (Reddit, Threads, Twitter/X, Product Hunt, ASA). `<NNN>` is monotonic (`C001`, `C002`...) and never reused. Governed by `references/channel-playbooks.md`.

| Field | Type | Rule |
|---|---|---|
| `id` | `C001`… | monotonic, prefixed with `C` to distinguish from ASO `H` hypotheses |
| `channel` | `reddit` / `threads` / `x` / `producthunt` / `asa` | external marketing vector |
| `type` | `contextual_reply` / `dev_showcase` / `post` / `ad` | execution format |
| `status` | `idea` / `draft` / `queued` / `staged` / `live` / `judged` / `abandoned` | operational state |
| `target_community` | string (e.g. `r/iphonehelp`, `r/iosapps`) | destination community or ad group |
| `campaign_token` | string (e.g. `reddit_storage_fix`) | alphanumeric token passed in `?ct=...` |
| `tracked_link` | URL | full App Store URL with `ct` and optional `pt` |
| `prediction` | text + numbers | expected clicks and installs within window (default 7–14 days) |
| `kill_criterion` | text + numbers | removal/ban, or < N clicks in window |
| `copy_template` | text / markdown | exact native copy (one text per language) prepared for posting |
| `went_live` | date | day the post/comment/ad was actually published |
| `window_days` | integer | default 7 days for social comments, 14 days for ads/showcases |
| `verdict` | `worked` / `no-effect` / `adverse` / `withheld` | outcome judged via ASC Campaign Analytics |

**Attribution Ledger — `campaigns.csv`**: Every generated campaign link is appended to `marketing/campaigns.csv` via `scripts/campaign_link.py`. Results are cross-referenced in App Store Connect (App Analytics → Sources → Campaigns).

**Anti-Collision & Deduplication Guard**:
Before creating or proposing a new channel experiment, `campaign_link.py` and the skill check all existing `C*.md` files. If a community already has an active `queued` or `live` hypothesis (or if `r/iosapps` is under its 30-day cooldown), the skill refuses to generate a duplicate proposal and cites the existing hypothesis.



## Weekly record — `metrics/weekly.csv`

Append-only. A logical observation is keyed by period, segment, market and metric definition. Corrections retain the old row and explicitly name the superseded record; until duplicate selection is implemented, the visualizer rejects ambiguous rows.

```csv
week_start,segment,impressions,product_page_views,downloads,cvr_pct,trial_starts,source,recorded,note
2026-09-07,search,,,,,,unavailable,2026-09-14,ASC analytics not yet generated
```

- `week_start` — Monday, ISO date. Weeks are whole; never record a partial week.
- Record whether impressions and views are total or unique, and downloads first-time or total.
  Preserve the source's `cvr_pct`; ASC conversion is total downloads plus pre-orders divided by
  unique-device impressions, with Apple's pre-order counting rules. Downloads/views is not page CVR.
- `segment` and territory filters must be explicit. Search may include Apple Ads; browse is context.
  If adding an optional `market` column, preserve historical blanks as unknown, not global totals.
- `source` — a provenance tag (`user:@<date>` for a figure read off the web UI, `live:<command>@<date>`
  for one pulled by API, `absent:<reason>` when unobtainable). Never invented: an unobtainable figure
  is an empty cell tagged `absent:<reason>` — never a zero, never an estimate.
- Trial starts may come from a subscription provider or eligible ASC subscription reports; record the source and definition. They are not paid users. An optional `paid_subscribers` field must be separately observed.
- **Metrics display**: use `funnel_visualizer.py` with explicit filters; no fabricated values, fixed benchmarks, sequential funnel or inferred cash. See `references/funnel-analytics.md`.

## The series the pass stores

Each file is appended by one stage of `collect` and by nothing else. A row carries the day it was captured or recorded; a correction is a later row for the same key, and the export takes the latest one known on its day.

| File | Written by | Holds |
|---|---|---|
| `metrics/lifecycle.csv` | the funnel stage | one row a closed Monday week and segment (`all`, each storefront): opt-in installs and deletions. A sample of devices that share analytics, not a cohort |
| `metrics/cashflow_weekly.csv` | the revenue stage | one row a closed week and storefront: transactions, new trials, gross revenue, proceeds, Apple Ads spend |
| `metrics/ads.csv` | the revenue stage | one row a closed week and Apple Ads campaign: spend, impressions, taps, installs |
| `metrics/revenue.csv` | the revenue stage | one row a read: active subscriptions and trials, MRR, the 28-day figures |
| `metrics/telemetry.csv` | the in-app weeks step | one row a closed week and metric of the app's own events: a count, or a numerator with its denominator |
| `metrics/ratings.csv` | the reviews stage | one row a read and storefront (`all` for the total): ratings, average, written reviews, unanswered reviews |
| `metrics/charts.csv` | the charts step and `charts` | one row a read, storefront, genre and chart: the app's position, or `beyond-depth` with the chart's size, or `error` |
| `metrics/releases.csv` | the reviews stage | one row the first time a version is seen live, with the day the store says it was released |

```csv
# lifecycle.csv
week_start,segment,first_installs_optin,deletions_optin,deletions_per_100_installs,deleted_within_1d,deletions_timed,median_days_to_delete,source,recorded
# cashflow_weekly.csv
week_start,country,transactions,new_trials,gross_revenue_usd,proceeds_usd,ad_spend_usd,source,captured
# ads.csv
week_start,campaign_id,market,spend_usd,impressions,taps,installs,source,captured
# revenue.csv
captured,active_subscriptions,active_trials,mrr_usd,revenue_28d_usd,new_customers_28d,active_users_28d,source
# telemetry.csv
week_start,section,metric,numerator,denominator,source,captured
# ratings.csv
captured,market,ratings_count,rating_average,reviews,reviews_unanswered,source
# charts.csv
captured,market,genre,chart_type,position,depth,status,source
# releases.csv
version,state,state_date,source,captured
```

`weekly.csv` and `lifecycle.csv` hold two kinds of rows: those the collector folded from the daily reports (`source` begins `live:asc analytics daily`, `week_start` is a Monday of a closed week) and older rows a person or an older script wrote. Only the first kind is exported; the export counts the rest in a `NOTE` and leaves them where they are.

## Rank observation — `metrics/ranks.csv`

Append-only, one row per `(date, market, keyword)`.

```csv
date,market,keyword,group,position,popularity,difficulty,source,depth,status
2026-09-08,us,compress videos,target,,58,,astro,200,beyond-depth
```

- `market` — `us` / `gb` / `de` / `ua` for the weekly set; other locales are fine for a monthly pass.
- `group` — `own` / `title` / `target` / `competitor`, matching `marketing/keywords/`.
- `position` — a blank is ambiguous without request status and depth. Only a successful query can establish not observed within the tracked depth. A
  keyword that was not checked at all is simply an absent row, not an empty-position row — the two
  are not the same thing and must not be conflated.
- Preserve source/method/depth/status, exact query, timestamp and app identity in the linked raw snapshot. A failed request is unknown. Historical rows missing these fields cannot support paired rank verdicts.
- `depth` / `status` — the queried depth and the request outcome, the two fields that make a pair
  comparable. `status` is `ok` (found, `position` set), `beyond-depth` (queried, absent within
  `depth`, `position` blank) or `error` (request failed, nothing observed). Two `beyond-depth`
  observations are not a zero delta; `ok` -> `beyond-depth` and back are events in their own right.
  `scripts/ledger.py ingest` writes these and refuses any position deeper than the result list its
  query returned, which is what a value carried over from an older snapshot looks like.
- Append on the skill's own cadence, not the tracker's retention window. History accumulates locally
  independent of how long the provider keeps it — provider retention only bounds how much can be
  back-filled on first use, never how long an experiment may run.

## Apple demand — `metrics/popularity.csv`, `popularity_cut.csv`, `impression_share.csv`

Append-only, written by `scripts/radar.py`, never rewritten. `week` is the measured Sunday–Saturday week (its Sunday),
`captured` the pull date; keep them apart. `source` is `asc-ads-insights`; the full tag is
`live:asc ads insights <search-term-popularity|impression-share> find@<captured>`.

```csv
week,captured,market,genre,term,rank_in_genre,popularity_100,popularity_5,why,source
2026-09-20,2026-09-29,jp,PHOTO_VIDEO,動画圧縮,185,55,3,basket,asc-ads-insights
```

- `why` — `basket` (a tracked term found in the head) or `topic` (a head term containing a configured topic word, at most 40 per market).
  It records how the row was picked at pull time; readers match by term, so a `topic` row for a term tracked since counts as tracked.
- `popularity_cut.csv` — `week,captured,market,genre,listed,min_popularity_100,source`: per market × genre, how many terms Apple
  listed and the lowest score listed. `listed=0` with a blank genre means Apple lists nothing for that storefront. A tracked term
  missing from `popularity.csv` is *below this cut*: never zero, never "no demand". The two files are read together.
- `impression_share.csv` — `week,captured,market,term,rank,popularity_5,share_low,share_high,source`: only terms the app's own ads
  showed on; two different bounds mean Apple returned a band.
- config.md labels, all optional: `**Apple Ads profile**:`, `**Apple Ads account**:`, `**Apple Ads genres**:`, `**Apple Ads topic words**:`.

## Storefront economics — `metrics/markets.csv`

One row per territory, refreshed when prices change, never estimated.

```csv
territory,storefront,currency,customer_price,proceeds_local,fx_to_usd,proceeds_usd,source
DEU,de,EUR,35.99,25.71,0.860364,29.88,live:asc subscriptions pricing prices list@2026-09-08
```

- `proceeds_local` is Apple's own proceeds figure from the price record, not price minus a guessed
  commission. Pull it with `asc subscriptions pricing prices list --subscription-id ID --include
  territory,subscriptionPricePoint --paginate`.
- `fx_to_usd` carries its own date and source in `source`; it is the only estimated field, and a
  blank one leaves `proceeds_usd` blank rather than inventing a conversion.
- `storefront` is the alpha-2 code that joins to `ranks.csv`; a blank one means that territory
  cannot be ranked against the others yet.

## Decision — `decisions.md`

Append-only, newest entry last, never reordered.

```markdown
## 2026-08-19 — Buy Astro on the day the app leaves review, not before
**Evidence**: no trial, 14-day refund only; app ranks for nothing while in review, so the window
would be spent with nothing to evaluate against.
**Supersedes**: earlier "buy before launch to capture the baseline" — the baseline *is* the first
live day, so there is nothing to capture earlier.
```

Every entry: a date-stamped heading naming the choice, an **Evidence** line (provenance-tagged where
it cites a figure), and a **Supersedes** line naming what it reverses — even `none` if it's the first
decision on the topic. This is what makes a reversal legible as a reversal instead of reading as if
the new position had always been held.

## Queued action — `queue.md`

`reviews respond --queue-id Qnnn` runs only when entry Qnnn holds exactly that command, and only once: it then appends "Qnnn approved, executed" to `decisions.md` and leaves the entry. Remove an entry when it is abandoned or has been recorded.

```markdown
### Q003 · queued 2026-09-10 · fence: publishes
**Effect in plain language**: replies publicly, under your name, to the 1★ review from "mkdev".
**Command**: asc reviews respond --review-id <ID> --response "<text>"
**Preconditions**: review still unanswered; text unchanged since drafting.
```

Every entry: the **exact** runnable command with no placeholders left to fill in, the effect in one
plain-language sentence naming what changes and who sees it, and its preconditions. Re-verify
preconditions immediately before executing an approved entry — an approval given weeks ago was given
against a world that has since moved; a stale entry is re-planned, not executed on trust.

## The data layer — `data/`

`export` derives it from the store, offline and without reading the clock: the same store and `--as-of` day
give the same bytes, and `export --check` fails when `data/` differs from a fresh export. Nothing is typed
into it by hand and nothing in it is a source.

```text
data/
├── week/<monday>.json         flows of one closed Monday week: store funnel, lifecycle, money, ads, in-app
├── snapshot/<date>.json       stocks read on one day: ranks, coverage, demand, impression share,
│                              subscriptions, ratings, charts
├── hypotheses.json            every hypothesis with its state on the export's day and its basket
├── keys.json                  every tracked key with its position on each sweep date
└── events.json                the queue and the releases
```

By path: `data/week/<monday>.json`, `data/snapshot/<date>.json`, `data/hypotheses.json`, `data/keys.json`,
`data/events.json`. The contract (`aso-copilot/dashboard-data@1`), the meaning of `unavailable` and its four codes are in
`references/export-and-page.md`.

## STATE.md

Written by `export` from the exported objects and from nothing else: the day, the hypothesis counts and the
due list, the queue, the newest headline figures, each source's newest period. Its first line is
`<!-- generated by export_dashboard; do not edit -->`. The export writes it only when the file is absent or
starts with that line; a `STATE.md` a person wrote is kept, the export says `KEPT STATE.md: written by hand,
archive it first`, and it stays until it is moved aside (for example `git mv marketing/STATE.md
marketing/reports/STATE_until_<month>.md`). A generated one that was edited fails `export --check`.

It holds **no authority of its own**: a figure in it is a figure of `data/`, which is a figure of the store.
Never cite `store:STATE.md` as if the cache were the source (see `references/provenance.md`).

## Entity relationships

```text
Phase ──governs──▶ which rigor applies to ──▶ Hypothesis.primary_signal
                                                  │
Hypothesis ──judged against──▶ Weekly record (P3-measure)
           └──judged against──▶ Rank observation (P2-cold)
           └──produces────────▶ Decision
           └──may produce─────▶ Queued action

data/ ──derived from──▶ everything above, by `export` (never typed, never a source)
STATE.md ──derived from──▶ data/ (never authoritative on its own)
```

Two invariants that override everything else in this file:

1. **No file except a live check may raise confidence.** Every stored artifact can lower it (missing
   data, a confound, a stale rank) but none can establish what is true of the App Store right now.
2. **No claim leaves the skill without a provenance tag** (`references/provenance.md`).
