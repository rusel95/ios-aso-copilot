# Dashboard rework — design

Date: 2026-11-14 · Status: draft, waiting for approval · Mockups: https://claude.ai/artifact/NBZp3WPgyhgc7q9yaBUf6L (private canvas; artboards A and B are the chosen look, C is not built)

This repository is public. This document holds no figure, identifier or keyword of any app.

## Why

The skill's output today is prose an agent writes: `STATE.md` and dated reports. Many figures exist only as sentences there, so they cannot be charted, compared between two runs, or checked. Two sessions reading the same store can report different numbers, because each works them out again.

The owner wants the skill to work the way his reference project does: collection saves what it read, a named command builds every figure offline, a small set of data files holds only what a page shows, and a static page shows it with history and with the hypotheses. Determinism is the main requirement.

## What the owner decided

- The reference project's logic: a GitHub page, historical data, historical charts, hypotheses.
- JSON holds only what the page shows.
- Home screen is artboard A (by source). Its sections become tabs. The ledger and the charts of artboard B (what to judge, what to decide, the squares, the timeline, prediction against reads) are a tab of their own.
- The first app is the one whose store lives in the owner's first app repository. The reworked skill is run there, with the settings that repository already has, and the page shows that real data.
- Improvements noticed on the way are listed in the plan.

Everything else in this document is the author's call and is marked so where it matters.

## Goals

1. Same store and same `--as-of` date give the same data files, byte for byte. Same data files give the same page, byte for byte.
2. Every figure on the page comes from a data file, and every data file from a named command. No figure is worked out by an agent.
3. Every figure has history where its source has history, and says why where it has none.
4. A figure that could not be measured shows a code and a reason, never zero and never blank.
5. The page shows each hypothesis with its window, its verdict, and what was read against its prediction.
6. The page works opened as a local file, with no network.

## Non-goals

- More than one app on one page. One store, one page.
- A server, a database, accounts, or an admin panel.
- New data sources. This uses what the skill already reads.
- The page writing a verdict, a forecast or a recommendation. It shows evidence; the verdict stays a person's call.
- A dark theme in the first version.
- Artboard C (pipeline by stage and market).
- Showing `decisions.md`, the dated reports or the handbook on the page.

## Anti-goals

- A page that looks complete while holding figures typed in by hand.
- A second copy of the store that can drift from the first.
- Anything of an app (figures, identifiers, keywords) committed to this public repository.

## Constraints

- Python 3.11 or later, standard library only, like the scripts today. The page is plain HTML, CSS and JavaScript with inline SVG charts and no library.
- The store is `marketing/` in the app's main checkout and is shared by its worktrees (`references/state-store.md`). That stays.
- Rank history cannot be fetched again: the search API has no past. The rank ledger must never be lost or rewritten.
- The app repository is private; this one is public. The app repository reaches this skill through a link to this repository's main checkout, so a branch here is not what the app repository runs until it is merged.
- Existing commands keep working through the rework. Nothing an agent runs today breaks in the same change that adds the page.

## Approaches

**1. A derived data layer over the store as it is (chosen, author's call).** The append-only CSV and Markdown store stays the ledger of evidence. A new command, `export_dashboard.py`, reads it and writes `marketing/data/`, holding only what the page shows. A second command, `build_site.py`, reads only `marketing/data/` and writes the page. Gaps in history are closed by adding append-only series to the store.
Trade-off: two committed layers. It is bounded, because the second is fully derived: `export_dashboard.py --check` rebuilds it and fails when the committed files differ. In return nothing is migrated, existing commands keep working, the store stays correctable by hand, and `data/` is the one boundary a published page can ever cross.

**2. JSON replaces the store.** Collectors write period files directly and the CSV files are retired. One layer, but every collector and the ledger are rewritten at once, thousands of rank observations are migrated, and the hand-correctable append-only form is lost. Too large a step for what it buys.

**3. No data layer: the page is built straight from the store.** The least code. The page build is then tied to the store's internals, there is no contract to test, and "JSON holds only what the page shows" is not met.

## The design

### Three boundaries

| Step | Reads | Writes | Network | Clock |
|---|---|---|---|---|
| Collect (`copilot.py cycle` and the `pull_*`, `radar`, `ledger ingest/refresh` commands) | the sources | appends to the store | yes, the only step that has it | yes |
| Export (`export_dashboard.py --store S --as-of D`) | the store | `S/data/` | no | no: `--as-of` |
| Build (`build_site.py --data S/data --out public`) | `S/data/`, the skill's catalog and page source | `public/index.html` | no | no |

Apple Ads changes and App Store metadata changes are actions, not collection. They stay behind the approval fence (`queue.md`) and are never part of a cycle.

### The data contract: `aso-copilot/dashboard-data@1`

A lesson taken from the reference project: its period files repeat each figure's family, unit and source in every file, and that repetition is most of their size. Here static facts live once, in the skill.

- **Catalog** — `assets/dashboard/catalog.json` in the skill. One entry per figure key: family, title, unit, definition in plain words, whether it is a flow or a stock, and whether it is an approximation and by what method. The same for every app. Never written into `data/`.
- **Flows: `data/week/<monday>.json`.** Figures summed over one closed week: impressions, product page views, first-time downloads, trials, deletions, Apple Ads spend, taps and installs, proceeds, in-app events. Only closed weeks are written.
- **Stocks: `data/snapshot/<date>.json`.** Figures read at a moment: rank bands and coverage, subscriptions and MRR, ratings, chart position, search popularity, impression share.
- **`data/hypotheses.json`.** One entry per hypothesis with the fields the Ledger tab shows: id, title, markets, queries, status, verdict, went live, window, signal, prediction and kill criterion as text, confounds, and the derived state (open, due, days since the window closed, reads recorded inside the window, its own basket's movement as the ledger report counts it).
- **`data/keys.json`.** One entry per tracked key: market, group, and its position on each sweep date, with the three existing states kept apart (`ok`, `beyond-depth`, `error`). For the latest sweep it also carries what the ledger's priority order prints: the score, the net proceeds per subscriber, the demand label and the claim status.
- **`data/events.json`.** Dated things drawn as marks on charts and as lists: releases, and queued approvals read from the headings of `queue.md` (id, date, title).

A family whose source measures a period of its own states it in `measured`: Apple's search popularity week runs Sunday to Saturday, so it is a snapshot dated by its capture day that names the week it measured.

Inside a period file, figures are grouped by family, and the source and fetch time are stated once per family:

```json
{
  "schema": "aso-copilot/dashboard-data@1",
  "as_of": "2026-11-14",
  "period": {"kind": "week", "id": "2026-10-19", "start": "2026-10-19", "end": "2026-10-25"},
  "families": {
    "store_funnel": {
      "source": "asc-analytics", "fetched_at": "2026-10-28",
      "figures": {
        "impressions": {"value": 0, "by_market": {"ua": 0}},
        "page_cvr": {"value": 0.0, "numerator": 0, "denominator": 0}
      }
    },
    "in_app": {
      "unavailable": {"code": "no_source", "reason": "No stored series before 2026-11."}
    }
  }
}
```

A figure has a `value`, or `unavailable` with a code and a reason. `unavailable` on a family applies to every figure in it. Codes are a closed list: `no_source` (nothing stores it yet), `no_data` (the source answered and had nothing to count), `not_configured` (the store's config lacks what the collector needs), `unreachable` (the request failed). Files are canonical: sorted keys, fixed indentation, a trailing newline.

`build_site.py` checks every file against the contract before writing anything; one bad file fails the build and nothing is written. A test fails when the page names a figure key the catalog lacks, or the catalog holds one the page has no place for.

### Closing the storage gaps

Each of these is an append-only CSV in the store with `source` and `captured` columns, written by the collector that already reads the source:

| New file | Replaces | Written by |
|---|---|---|
| `metrics/revenue.csv`, one row per read | `revenuecat_latest.json`, which each run overwrites | `pull_revenuecat.py` |
| `metrics/cashflow_weekly.csv`, per closed week and storefront | `cashflow.csv`, one growing window | `pull_revenuecat.py` |
| `metrics/ads.csv`, per closed week and campaign | sentences in `STATE.md` | `radar.py` |
| `metrics/telemetry.csv`, per closed week: numerator and denominator per step | `telemetry_latest.json`, sentences in `STATE.md` | `pull_bigquery_telemetry.py` |
| `metrics/ratings.csv`, per read and storefront | sentences in `STATE.md` | `copilot.py reviews` |
| `metrics/charts.csv`, per read, storefront and genre | nothing: read live, never stored | `copilot.py charts` |
| `metrics/releases.csv`, version and the day it went live | sentences in `STATE.md` | `copilot.py status` |

Rules that change:

- **`weekly.csv` holds closed weeks only.** `pull_funnel.py` already folds the daily reports into Monday weeks and never rewrites a week it has written. The export reads only the rows that command wrote (their `source` begins `live:asc analytics daily`), whose `week_start` is a Monday and whose week has closed by `--as-of`. Every other row is left out and counted in the export's output. History for the store funnel is rebuilt by pulling the daily reports again, which the source keeps.
- **Ratios are computed from totals.** The export never reads a stored percentage such as `cvr_pct`, which today holds downloads over views in some rows and downloads over impressions in others. Each ratio is its own figure key with its numerator and denominator.
- **Rank bands are shares, not counts.** A snapshot states how many keys were read and how many sit in each band; the page charts the share. A date that read under half of the keys tracked on that date feeds the per-key series and is left out of the band trend (author's call on the threshold).
- **One owner per figure.** The band figures, the movers and the coverage come from `ledger.py` functions that `export_dashboard.py` calls; no second computation exists.
- **`STATE.md` is generated.** `export_dashboard.py` writes a one-screen summary from the data for an agent to read first. An agent no longer writes figures into it. Reasoning goes to `decisions.md`, as now.

Hypothesis files keep their form. The Ledger tab's chart for a rank hypothesis is drawn from fields that are already structured: `markets`, `queries`, `went_live`, `window_days`.

Two things artboard B draws are not built in the first version, because today they would be figures typed by hand:

- The target and guardrail lines on a due card. They need a machine-readable target per prediction, a later optional field; old files stay valid without it.
- The one-line proof beside each hypothesis that worked or hurt. The first version shows the verdict and the basket's movement. Later a judged hypothesis may name figure keys as its evidence, and the page prints those figures from the data.

### The page

One self-contained `index.html`: style, script and data inline, a content security policy that allows nothing from outside, no font or image loaded. Age in days is worked out in the reader's browser, since the build reads no clock; a source older than 14 days is marked stale (author's call).

Tabs, as hash routes:

| Tab | Holds |
|---|---|
| Overview | artboard A's top: sources and their age, six headline figures, then one summary block per tab below |
| Ledger | artboard B: judge, decide, next by money at stake; the squares; what worked and what hurt; the timeline; one card per due hypothesis with its queries' series, the live day, the window end, and the count of reads inside the window |
| Keywords | bands over time, top 30 by storefront, gains and losses, coverage, every tracked key with its series |
| Store funnel | closed weeks, by storefront, install lifecycle |
| Money | subscriptions, products, cashflow by storefront over closed weeks |
| Apple Ads | campaigns by closed week, impression share, search popularity |
| In-app | first-run steps, engine success, paywall, by closed week |
| How data gets here | the three steps, the rules, the four codes |

Any figure opens a panel: its value and state, the two totals behind it where the data holds them, its definition from the catalog, its source and when it was fetched, or the reason it is missing.

Look: the canvas. Inter for text, JetBrains Mono for figures, Space Grotesk for headings, named and used only where installed. One blue ramp for magnitude, blue against orange for polarity, the six verdict marks, hatching for a missing figure. Interface text is English, like the store.

### Tests

`tests/` with `unittest`, standard library only, no test reaches the network. An invented app's store under `assets/sample/store/` fills every place of the page. A golden test exports it, builds the page, and compares every file with recorded sha256 values; a change that alters output updates the manifest in the same change and says why. The scripts' existing `--self-check` runs stay.

### The real run in the first app's repository

This is the acceptance of the work, in two passes. Both use this branch's scripts with `--store` pointing at that repository's store, so that repository's link to the skill is not touched before the merge.

1. **Offline, after the export and the build exist.** Export from the store as it is, build, open the page. Export twice and build twice and compare bytes. This shows what history the store already holds and where it has none.
2. **Live, after the storage gaps are closed.** One full collection with the settings that repository already has: read-only against App Store Connect, RevenueCat, BigQuery, Apple Ads insights and the search API. It appends to the store, pulls the daily funnel reports again to rebuild true weeks, and takes one full rank sweep (about an hour at the API's pace). Then export, build, and commit `marketing/data/` there on a branch for the owner to review.

No Apple Ads change and no metadata change happens in either pass.

### Publishing

The build output is git-ignored and works as a local file, so both passes above need no hosting decision.

A Pages site built from a private repository is public to anyone with its address unless the account has access-controlled Pages. So publishing waits for one decision by the owner: **a public page, or a private one.** A public page needs a list of what never leaves (identifiers at least; possibly revenue and the keyword basket), enforced by a `check_clean.py` that scans `data/` for the store's own identifiers before a commit. A private one stays a local file, or goes to a host with access control. The workflow itself is the same either way: check out the app repository and this skill at a pinned commit, run `build_site.py`, deploy. It holds no source credentials and collects nothing.

### The skill itself

- `SKILL.md` becomes a router of about a quarter of its size: start here, the rules for every step, and one reference file per job (collect, export, publish, judge a hypothesis, propose one, Apple Ads actions).
- Hard rules, stated once: quote a figure from a command's output or a data file and work none out; pass `--as-of`; collectors are the only network code; actions go through the queue.
- **Long files are split** (added by the owner on 2026-11-14). No Python file under `scripts/` stays over 600 lines; the largest today is 2,751. Entry files keep their paths, because the app repository links to them; their bodies move into a package, `scripts/aso/`. The move changes no behaviour: every help text, the ledger report on the sample store and every self-check are recorded before the move and must come out the same after it.
- **One CLI** (added by the owner on 2026-11-14). `ios-aso-copilot` is the one documented entry: `collect` (today's `cycle`), `export`, `build`, `check`, `due`, and the commands it has now. Whatever changes something outside the store (Apple Ads keywords and campaign status, a reply to a review) lives in one module that `collect` never reaches.

## Order of work

1. Safety net: tests, an invented sample store, the recorded behaviour of today's commands.
2. Split the long files into `scripts/aso/`; one CLI.
3. Contract, catalog, and `export_dashboard.py` over the store as it is.
4. `build_site.py` and the page: Overview, Ledger, Keywords first, then the other tabs.
5. Offline pass in the first app's repository: the first real page.
6. Storage gaps: the new series and the collectors that write them.
7. Live pass in the first app's repository.
8. The reads calendar (`due`), the clean check, generated `STATE.md`, `SKILL.md` as a router, documents.
9. Publishing, once visibility is decided, with an optional scheduled rank read.

## Noticed in the skill, and where each is handled

| Finding | Handled in |
|---|---|
| Script files too long to hold in view (2,751 and 1,123 lines) | step 2 |
| Reads and writes in one command file: Apple Ads changes and review replies beside collection | step 2 |
| No tests beyond `--self-check` | step 1 |
| The same figure computed in more than one place gives more than one answer | steps 2 and 3 |
| Rank sweeps of different sizes compared by count | step 3 |
| A stored percentage that means two different ratios | step 3 |
| A hypothesis with no window prints a bare `d`; channel hypotheses are not in the ledger at all | steps 2 and 3 |
| Figures that exist only as sentences in `STATE.md` | step 6 |
| `*_latest.json` files overwrite their own history | step 6 |
| `weekly.csv` rows that re-record one growing window under one week | step 3, rebuilt in step 7 |
| `lifecycle.csv` has no command that writes it | step 6 |
| Windows close with none of the reads their prediction names | shown in step 4; `due` in step 8; scheduled read in step 9 |
| Stale queue entries | shown by age in step 4 |
| `SKILL.md` is 596 lines | step 8 |

Findings about the reference project are not recorded here; they were given to the owner directly.

## Left to the builder

- The exact figure keys and the catalog's wording.
- Chart geometry and the page's script structure.
- Column sets of the new CSV files beyond what the table above names.
- How `export_dashboard.py` reuses `ledger.py` (import or a shared module).
