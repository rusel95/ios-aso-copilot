# Dashboard Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the skill deterministic: collectors append to the store, `export` derives page-only JSON offline, `build` turns that JSON into one static page with history and the hypothesis ledger, and the long scripts become a small library behind one CLI.

**Architecture:** Three steps with hard boundaries: collect (network, appends to the store), export (store → `data/`, no network, no clock), build (`data/` → `index.html`, no network, no clock). Shared code moves from the entry scripts into the package `scripts/aso/`; entry paths stay. The page reads only `data/`.

**Tech Stack:** Python 3.11+ standard library, `unittest`; plain HTML, CSS and JavaScript with inline SVG; Node only as an optional test runner for the page.

**Spec:** `docs/superpowers/specs/2026-11-14-dashboard-rework-design.md`. Look: the canvas it links (artboards A and B).

## Global Constraints

- Python 3.11 or later, standard library only. No new dependency anywhere.
- This repository is public. No figure, identifier or keyword of a real app in any committed file. The sample store is the invented app "Tidepool", App ID `1000000001`, bundle `com.example.tidepool`.
- Nothing is copied from the reference project. Page source, scripts and tests are written fresh.
- Entry paths stay valid: `bin/ios-aso-copilot`, `scripts/copilot.py`, `scripts/ledger.py`, `scripts/radar.py`, `scripts/pull_*.py`.
- At the end no Python file under `scripts/` is over 600 lines.
- `scripts/aso/dashboard/` imports none of `urllib`, `http`, `socket`, `subprocess`, and calls neither `date.today()` nor `datetime.now()`. `--as-of` is its only date.
- Canonical JSON everywhere under `data/`: `json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n"`.
- Schema id `aso-copilot/dashboard-data@1`. Unavailable codes, closed list: `no_source`, `no_data`, `not_configured`, `unreachable`.
- Store CSV files are append-only. A correction is a new row.
- Thresholds: a source is stale after 14 days; a sweep that read under 50% of the tracked keys is left out of the band trend.
- Interface text is English.
- Quality gates, from the repository root: `python3 -m compileall -q -f scripts tests` prints nothing; `python3 -m unittest discover -s tests -t .` ends with `OK`.
- A task that adds a command re-records `tests/golden/help/copilot.txt` and that command's own help file, and names both in its commit. No other recorded file changes unless the task says so.
- In the app repository (Tasks 14 and 19): never commit, never switch branch, never edit `queue.md`, `decisions.md` or a hypothesis file. Only collectors append to `metrics/*.csv`; only `export` writes `data/` and `STATE.md`.

## Review Focus

1. **A fresh store** (header-only CSV files, no hypotheses): export succeeds, every family is `unavailable` with `no_data`, the page builds. Test in Task 7.
2. **A hand-edited row** with a non-number or a blank market: the row is named in the export's notes and skipped; no crash, no zero. Test in Task 7.
3. **A correction row** (same key, later `recorded`): the later one wins; with equal dates the later line wins; two exports are identical. Test in Task 7.
4. **Text that bites**: non-ASCII queries, U+2019 against U+0027 apostrophes, and a keyword containing `</script>`: a hypothesis query finds its own key and never a neighbour that differs only by apostrophe, and the payload cannot close its script tag. Tests in Tasks 2 and 8.
5. **`--as-of` in the past**: series rows dated or recorded after it are ignored, and due states are counted against it. Hypothesis files carry no history, so their verdicts read as they stand; the export says so in its notes. Test in Task 7.

## File map

| Path | Responsibility |
|---|---|
| `scripts/aso/store.py` | read the store: config, CSV, ranks, markets, hypotheses, brand tokens; `append_csv`; the `PROBLEMS` list |
| `scripts/aso/ranks.py` | pure rank logic: series, movement, bands, movers, coverage |
| `scripts/aso/ledger_state.py` | pure hypothesis states and the priority order |
| `scripts/aso/ledger_report.py` | prints sections A, B, C and the bands table from the pure functions |
| `scripts/aso/ledger_ingest.py` | snapshot ingest, refresh, draft (the only rank network code) |
| `scripts/aso/commands/*.py` | one module per `copilot.py` command group; `ads_actions.py` is the only module that changes anything outside the store |
| `scripts/aso/dashboard/contract.py` | schema id, codes, `canonical`, validation |
| `scripts/aso/dashboard/weeks.py` | Monday weeks and "closed by" |
| `scripts/aso/dashboard/export.py` | store → the `data/` file set; write, check |
| `scripts/aso/dashboard/site.py` | `data/` → `index.html` |
| `scripts/aso/dashboard/clean.py` | the check before a commit of `data/` |
| `scripts/export_dashboard.py`, `scripts/build_site.py` | thin entries |
| `assets/dashboard/{catalog.json,places.json,template.html,style.css,app.js}` | the figure catalog, which figure sits on which tab, the page source |
| `assets/sample/store/` | the invented store every test reads |
| `tests/` | unit tests, recorded behaviour, golden manifest |

---

## Phase 1 — Safety net

### Task 1: Test harness, sample store, recorded behaviour

**Files:**
- Create: `tests/__init__.py`, `tests/helpers.py`, `tests/test_recorded.py`, `tests/test_self_checks.py`, `tests/golden/help/*.txt`, `tests/golden/ledger_report.txt`
- Create: `assets/sample/store/` (`config.md`, `queue.md`, `hypotheses/*.md`, `metrics/*.csv`)

**Interfaces:**
- Produces: `tests.helpers.ROOT: Path`, `SAMPLE: Path` (`assets/sample/store`), `run(script: str, *args: str) -> tuple[int, str, str]` (runs `python3 scripts/<script>` with `cwd=ROOT`), `copy_store(tmp: Path) -> Path`, `AS_OF = "2026-11-14"`.

The sample store, exactly:

`config.md`: App ID `1000000001`, Version `1.0.0`, Brand tokens `tidepool`.

`metrics/ranks.csv`, source `itunes-search-api`, depth `200`, group `target`. A number is a position; `B` beyond-depth, `E` error, `Z` no-results, blank = no row.

| market | keyword | 2026-10-05 | 2026-10-19 | 2026-11-02 | 2026-11-09 |
|---|---|---|---|---|---|
| us | tidepool | 1 | 1 | 1 | |
| us | tide tracker | 40 | 22 | 9 | 7 |
| us | tide times | 120 | 95 | 60 | |
| us | surf forecast | B | B | 150 | |
| us | moon phase | 8 | 12 | 25 | 30 |
| us | sea level | E | 180 | B | |
| ua | tidepool | 2 | 1 | 1 | |
| ua | приплив | 15 | 9 | 4 | |
| ua | графік припливів | B | 28 | 11 | |
| ua | прогноз хвиль | 70 | 70 | 70 | |
| ua | фаза місяця | Z | Z | Z | |
| ua | п’ятниця море (U+2019) | 33 | E | 31 | |

`metrics/weekly.csv`: collector rows (`source` = `live:asc analytics daily r14+r3@<recorded>`) as impressions / page views / downloads:

| week_start | recorded | all | us | ua |
|---|---|---|---|---|
| 2026-10-19 | 2026-10-27 | 1000 / 100 / 40 | 600 / 60 / 24 | 400 / 40 / 16 |
| 2026-10-26 | 2026-11-03 | 1200 / 150 / 45 | 700 / 90 / 27 | 500 / 60 / 18 |
| 2026-11-02 | 2026-11-10 | 1500 / 160 / 64 | 900 / 100 / 40 | 600 / 60 / 24 |
| 2026-11-09 (open on the as-of day) | 2026-11-10 | 300 / 30 / 10 | | |

plus one legacy row: `2026-10-01,all,9999,999,99,…,asc-analytics-deduped,2026-10-20`.

`metrics/markets.csv`: `us` 25.00, `ua` 4.00. `metrics/popularity.csv`: week `2026-10-25`, captured `2026-11-03`, us, `tide times`, popularity 41. `metrics/popularity_cut.csv`: us listed 500 min 38; ua listed 0. `metrics/impression_share.csv`: us, `tide tracker`, rank 2, 0.31–0.40. `metrics/lifecycle.csv`: one legacy row with `week_start` `2026-10-01`.

`hypotheses/`:

| id | markets | signal | queries | went_live | window_days | verdict |
|---|---|---|---|---|---|---|
| H001 | us | rank | tide tracker; tide times | 2026-10-06 | 21 | worked |
| H002 | ua | rank | прогноз хвиль | 2026-10-06 | 21 | no-effect |
| H003 | us | rank | moon phase | 2026-10-06 | 21 | adverse |
| H004 | ua | funnel | | 2026-10-10 | 14 | withheld |
| H005 | ua | rank | приплив; графік припливів | 2026-10-20 | 14 | |
| H006 | us | rank | surf forecast | 2026-11-05 | (blank) | |
| H007 | us | funnel | | | 14 | |
| C001 | (channel `threads`, status `live`, went_live 2026-11-01, window 7) | | | | | |

`queue.md`: `### Q001 · queued 2026-10-30 · needs a go — create the us penny flight` and `### Q002 · queued 2026-11-12 · stage 1.0.1 metadata`.

- [ ] **Step 1:** Create the sample store above and `tests/helpers.py`.
- [ ] **Step 2:** Record today's behaviour. For each of `copilot.py`, `ledger.py`, `radar.py`, `pull_funnel.py`, `pull_revenuecat.py`, `pull_ga.py`, `pull_bigquery_telemetry.py`, and every `copilot.py` subcommand the parser lists, save `--help` output to `tests/golden/help/<name>.txt`. Save the output of `ledger.py --store assets/sample/store --as-of 2026-11-14 report` to `tests/golden/ledger_report.txt`.
- [ ] **Step 3:** Write `tests/test_recorded.py`: `test_help_texts_unchanged` (each file equals a fresh run) and `test_ledger_report_unchanged`. Write `tests/test_self_checks.py`: one test per script that has `--self-check`, asserting exit code 0. A self-check that needs the network or an outside tool is listed there as skipped, with that reason.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `test: sample store and the recorded behaviour of today's commands`.

---

## Phase 2 — Split the long files, one CLI

### Task 2: `ledger.py` becomes `scripts/aso/`

**Files:**
- Create: `scripts/aso/__init__.py`, `store.py`, `ranks.py`, `ledger_state.py`, `ledger_report.py`, `ledger_ingest.py`
- Modify: `scripts/ledger.py` (argparse and dispatch only), `scripts/radar.py`, `scripts/ads_keywords.py` (imports)
- Test: `tests/test_ranks.py`, `tests/test_ledger_state.py`

**Interfaces:**
- Produces, in `aso.store`: `read_config(store) -> dict`, `read_csv(path) -> list[dict]`, `append_csv(path, cols, rows) -> None`, `read_ranks(store) -> list[dict]`, `read_markets(store) -> dict[str, float]`, `read_hypotheses(store, kinds=("H",)) -> list[dict]`, `read_brand_tokens(store) -> list[str]`, `parse_date(value) -> date | None`, `PROBLEMS`, `problem(where, why)`.
- Produces, in `aso.ranks`: the moved `band`, `band_of`, `brand_hit`, `series`, `movement`, `zero_result_keys`, and new pure functions:
  - `sweep_bands(rows: list[dict], brand: list[str], date: str) -> dict` with keys `tracked_keys`, `keys_read`, `top10`, `top30`, `top100`, `top200`, `beyond`, `no_results`, `errors`, `by_market` (the same counts per market). Brand keys are left out. `keys_read` counts `ok` and `beyond-depth` rows of that date. `tracked_keys` counts distinct non-brand keys with any row dated on or before `date`.
  - `movers(pairs: dict, brand: list[str]) -> list[dict]` with `market`, `keyword`, `first_date`, `first`, `last_date`, `last`, `delta`, `label`, sorted as section B sorts.
- Produces, in `aso.ledger_state`:
  - `hypothesis_states(hyps, pairs, empty, as_of: date) -> list[dict]` with `id`, `markets`, `signal`, `live`, `window` (int, 21 when blank), `verdict`, `state` (`judged`, `due`, `open`, `not-shipped`), `age_days`, `basket` (`None` for a funnel hypothesis, else `{"up","down","flat","unpaired","unmeasurable"}`).
  - `priority(pairs, markets, hyps, brand, demand) -> list[dict]` with `score`, `market`, `keyword`, `position`, `band`, `proceeds`, `gain`, `reach`, `status`, `demand`, sorted as section C sorts.
- The module global `TODAY` is gone. Functions that needed it take `as_of`; `scripts/ledger.py` passes `args.as_of or date.today()`.

- [ ] **Step 1: Write the failing tests** with the sample store's values:

```python
def test_bands_on_a_full_sweep(self):
    b = sweep_bands(read_ranks(SAMPLE), ["tidepool"], "2026-11-02")
    self.assertEqual((b["tracked_keys"], b["keys_read"]), (10, 9))
    self.assertEqual((b["top10"], b["top30"], b["top100"], b["top200"], b["beyond"]), (2, 2, 3, 1, 1))
    self.assertEqual((b["no_results"], b["errors"]), (1, 0))
    self.assertEqual(b["by_market"]["ua"]["top10"], 1)

def test_bands_on_a_partial_sweep(self):
    b = sweep_bands(read_ranks(SAMPLE), ["tidepool"], "2026-11-09")
    self.assertEqual((b["tracked_keys"], b["keys_read"]), (10, 2))

def test_states(self):
    s = {h["id"]: h for h in states(AS_OF)}            # helper: hypothesis_states on the sample
    self.assertEqual([s[i]["state"] for i in ("H001", "H005", "H006", "H007")],
                     ["judged", "due", "open", "not-shipped"])
    self.assertEqual(s["H001"]["basket"], {"up": 2, "down": 0, "flat": 0, "unpaired": 0, "unmeasurable": 0})
    self.assertEqual(s["H005"]["basket"]["up"], 1)
    self.assertEqual(s["H005"]["basket"]["unpaired"], 1)
    self.assertEqual(s["H006"]["window"], 21)
    self.assertIsNone(s["H004"]["basket"])

def test_priority_order(self):
    top = priority_on_sample()[0]
    self.assertEqual((top["market"], top["keyword"], top["score"]), ("us", "moon phase", 14.0))
    self.assertEqual(top["status"], "open hypothesis, not yet dominant")

def test_apostrophe_forms_join(self):
    # a hypothesis that spells the key with U+0027 still finds the U+2019 key in ranks.csv
```

- [ ] **Step 2:** Run them. Expected: FAIL, `No module named 'aso'`.
- [ ] **Step 3:** Move the code. Printing functions in `ledger_report.py` call the pure functions and print the same text. The join between a hypothesis query and a rank key goes through one function, `aso.ranks.resolve_key(keys, index, market, query)`: the exact spelling when it is tracked, otherwise the single key with the same loose form (`key_of`: case, spacing, NFC, U+2019 as U+0027). Two keys that share a loose form are two queries to the store, which ranks them apart, so then the query names neither.
- [ ] **Step 4:** One intended change of output: the Window column prints the parsed window, so H006 reads `21d`, not `d`. Re-record `tests/golden/ledger_report.txt` and name that single changed line in the commit message. Every other line must be unchanged.
- [ ] **Step 5:** Run the quality gates. Expected: `OK`, with `test_help_texts_unchanged` untouched.
- [ ] **Step 6:** Commit: `refactor: ledger logic moves to scripts/aso, pure functions for states, bands and priority`.

### Task 3: `copilot.py` becomes a thin CLI over command modules

**Files:**
- Create: `scripts/aso/commands/__init__.py`, `status.py`, `charts.py`, `keywords.py`, `ads_read.py`, `ads_actions.py`, `collect.py`, `google.py`, `cycle.py`, `campaign.py`, `selfcheck.py`
- Modify: `scripts/copilot.py` (keeps `build_parser()`, `main()`, the logging helpers)
- Test: `tests/test_boundaries.py`

**Interfaces:**
- Produces: every `cmd_*` function keeps its name and signature in its new module. `ads_actions.py` holds `cmd_ads_add_keywords`, `cmd_ads_set_campaign_status` and `cmd_reviews_respond` (the `respond` branch cut out of `cmd_reviews`). The parser gains `collect` as a second name for `cycle`.

- [ ] **Step 1: Write the failing tests** in `tests/test_boundaries.py`:

```python
def test_only_actions_module_changes_the_outside(self):
    # the strings "create-bulk" and "respond" (as an asc argument) and the campaign status update
    # appear in scripts/aso/commands/ads_actions.py and in no other file under scripts/
def test_collect_never_reaches_actions(self):
    # scripts/aso/commands/cycle.py and collect.py do not import ads_actions
def test_collect_is_cycle(self):
    code, out, _ = run("copilot.py", "collect", "--help")
    self.assertEqual(code, 0)
```

- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Move each command group to its module, as the table in the file map names them. Move nothing else and rename nothing.
- [ ] **Step 4:** Record `tests/golden/help/copilot-collect.txt` and re-record `copilot.txt`, whose command list gained `collect`. Run the quality gates. Expected: `OK`; `test_help_texts_unchanged` passes for every other file as recorded in Task 1.
- [ ] **Step 5:** Commit: `refactor: copilot commands move to modules, actions in one place, collect as a name for cycle`.

### Task 4: The other files over 600 lines

**Files:**
- Modify: `scripts/rank_audit.py`, `scripts/pull_ga.py`, `scripts/pull_revenuecat.py`, `scripts/localization_tool.py`, `scripts/radar.py`
- Create: `scripts/aso/<name>_*.py` as the recipe yields
- Test: `tests/test_boundaries.py`

- [ ] **Step 1: Write the failing test:**

```python
def test_no_long_files(self):
    long = {str(p.relative_to(ROOT)): n for p in (ROOT / "scripts").rglob("*.py")
            if (n := len(p.read_text(encoding="utf-8").splitlines())) > 600}
    self.assertEqual(long, {})
```

- [ ] **Step 2:** Run it. Expected: FAIL, listing these five files.
- [ ] **Step 3:** For each file, in this order and stopping when it is under 600 lines: move its `self_check` into `scripts/aso/<name>_selfcheck.py` (the `--self-check` flag still calls it); replace its own config and CSV readers with `aso.store`; move the largest group of functions that its own section comments mark off (fetching, folding, printing) into `scripts/aso/<name>_<group>.py`. The entry file keeps `main()` and its argparse.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `refactor: no script file over 600 lines`.

---

## Phase 3 — Contract and export

### Task 5: Contract, catalog, weeks

**Files:**
- Create: `scripts/aso/dashboard/__init__.py`, `contract.py`, `weeks.py`, `assets/dashboard/catalog.json`
- Test: `tests/test_contract.py`, `tests/test_weeks.py`

**Interfaces:**
- Produces: `contract.SCHEMA`, `contract.CODES`, `contract.canonical(obj) -> str`, `contract.load_catalog() -> dict`, `contract.validate(rel_path: str, text: str, catalog: dict) -> list[str]` (problems; empty means valid; it checks that `text == canonical(json.loads(text))`, that the path agrees with the period, every family and figure key against the catalog, every figure for a number `value` or an `unavailable` with a listed code and a reason).
- Produces: `weeks.monday(d: date) -> date`, `weeks.closed(week_start: date, as_of: date) -> bool` (true when `week_start + 6 days < as_of`).
- The catalog, `{"families": {<family>: {"kind": "week"|"snapshot", "title": str, "figures": {<key>: {"title", "unit", "definition", "ratio": [num, den] | null, "approximation": str | null}}, "rows": [columns] | null, "open": bool}}}`. Families and figure keys:

| Family | Kind | Figures |
|---|---|---|
| `store_funnel` | week | `impressions`, `page_views`, `first_downloads`, `view_rate` (page_views / impressions), `page_cvr` (first_downloads / page_views), `impression_cvr` (first_downloads / impressions) |
| `lifecycle` | week | `optin_installs`, `optin_deletions`, `deleted_within_1d`, `deletions_per_100` (approximation: opt-in devices only) |
| `money` | week | `proceeds_usd`, `ad_spend_usd`, `net_cashflow_usd`, `transactions`, `new_trials` |
| `ads` | week | `spend_usd`, `impressions`, `taps`, `installs`, `ttr` (taps / impressions), `cpi_usd` (spend_usd / installs) |
| `in_app` | week | open family: any key `<section>.<metric>` the store's telemetry holds |
| `ranks` | snapshot | `tracked_keys`, `keys_read`, `top10`, `top30`, `top100`, `top200`, `beyond`, `no_results`, `errors`, `share_top10`, `share_top30` |
| `coverage` | snapshot | `paired_keys`, `unmeasurable_keys`, `failed_requests`, `observations` |
| `subscriptions` | snapshot | `active_subscriptions`, `active_trials`, `mrr_usd`, `revenue_28d_usd`, `new_customers_28d`, `active_users_28d` |
| `ratings` | snapshot | `ratings_count`, `rating_average`, `reviews`, `reviews_unanswered` |
| `demand` | snapshot | rows: `market`, `genre`, `term`, `popularity_100`; and `cuts` rows: `market`, `genre`, `listed`, `min_popularity_100` |
| `impression_share` | snapshot | rows: `market`, `term`, `rank`, `share_low`, `share_high` |
| `charts` | snapshot | rows: `market`, `genre`, `chart_type`, `position`, `status` |

The rank bands do not overlap: `top30` counts positions 11 to 30, `top100` 31 to 100, `top200` 101 to 200. `share_top10` and `share_top30` are positions 1 to 10 and 1 to 30 over `keys_read`.

A figure may carry `numerator`, `denominator`, `by_market` (code → number or null) and, in `ads`, `by_campaign`. A family carries `source` and `fetched_at` once, an optional `measured: {"start","end"}`, and `figures` or `rows`; or only `unavailable`.

- [ ] **Step 1: Write the failing tests:** `test_canonical_is_stable` (dict order does not change the text; non-ASCII stays readable; ends with one newline), `test_valid_week_file_passes`, `test_unknown_figure_key_fails`, `test_non_canonical_bytes_fail`, `test_unknown_code_fails`, `test_path_must_match_period`, `test_week_must_start_on_monday`, `test_open_family_accepts_any_key`, `test_closed` (`closed(date(2026,11,2), date(2026,11,14))` true; `closed(date(2026,11,9), date(2026,11,14))` false; `closed(date(2026,11,2), date(2026,11,8))` false).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement `contract.py`, `weeks.py`, and write `catalog.json` with a plain-words definition for every figure.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: the dashboard data contract and the figure catalog`.

### Task 6: Export the entities

**Files:**
- Create: `scripts/aso/dashboard/export.py`
- Test: `tests/test_export_entities.py`

**Interfaces:**
- Consumes: `aso.store`, `aso.ranks`, `aso.ledger_state` (Task 2), `radar.demand_lookup`, `radar.demand_label`.
- Produces: `export.hypotheses(store, as_of) -> dict`, `export.keys(store, as_of) -> dict`, `export.events(store, as_of) -> dict`. Shapes:
  - `{"schema", "as_of", "hypotheses": [{"id", "kind" ("H" or "C"), "title" (the file name's slug with spaces), "markets", "queries", "status", "verdict", "signal", "went_live", "window_days", "window_end", "state", "age_days", "days_past_window", "reads_in_window" (distinct sweep dates, inside the window, that read at least one basket key), "basket", "prediction", "kill_criterion", "confounds"}]}`
  - `{"schema", "as_of", "dates": [...], "keys": [{"market", "keyword", "group", "brand": bool, "positions": [int | "b" | "e" | "z" | null], "priority": {...} | null}]}`; `positions` is aligned with `dates`; `priority` is that key's row of `ledger_state.priority`, or null.
  - `{"schema", "as_of", "releases": [], "queue": [{"id", "date", "title"}]}`; `releases` stays empty until Task 17.
- The export reads both kinds, `read_hypotheses(store, kinds=("H", "C"))`. A channel hypothesis gets its state by the same rule as any other, and its `basket` is null. On the sample, `C001` is `due` (live 2026-11-01, 7 days).

- [ ] **Step 1: Write the failing tests:**

```python
def test_hypotheses(self):
    h = {x["id"]: x for x in export.hypotheses(SAMPLE, date(2026, 11, 14))["hypotheses"]}
    self.assertEqual(sorted(h), ["C001", "H001", "H002", "H003", "H004", "H005", "H006", "H007"])
    self.assertEqual((h["H005"]["state"], h["H005"]["window_end"], h["H005"]["days_past_window"]),
                     ("due", "2026-11-03", 11))
    self.assertEqual(h["H005"]["reads_in_window"], 1)
    self.assertEqual(h["C001"]["kind"], "C")

def test_keys(self):
    k = export.keys(SAMPLE, date(2026, 11, 14))
    self.assertEqual(k["dates"], ["2026-10-05", "2026-10-19", "2026-11-02", "2026-11-09"])
    row = next(x for x in k["keys"] if x["keyword"] == "sea level")
    self.assertEqual(row["positions"], ["e", 180, "b", None])
    self.assertTrue(next(x for x in k["keys"] if x["market"] == "us" and x["keyword"] == "tidepool")["brand"])

def test_queue_from_headings(self):
    self.assertEqual(export.events(SAMPLE, date(2026, 11, 14))["queue"][0],
                     {"id": "Q001", "date": "2026-10-30", "title": "needs a go — create the us penny flight"})

def test_as_of_hides_later_sweeps(self):
    self.assertEqual(export.keys(SAMPLE, date(2026, 10, 20))["dates"], ["2026-10-05", "2026-10-19"])
```

- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the three functions.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: export hypotheses, keys and events`.

### Task 7: Export the periods, write, check, and the `export` command

**Files:**
- Modify: `scripts/aso/dashboard/export.py`, `scripts/copilot.py` (the `export` command)
- Create: `scripts/export_dashboard.py`
- Test: `tests/test_export_periods.py`, `tests/test_export_cli.py`

**Interfaces:**
- Produces: `export.build_all(store: Path, as_of: date) -> tuple[dict[str, object], list[str]]` (relative path under `data/` → object, and the notes), `export.write(store, files) -> dict[str, list[str]]` (`written`, `unchanged`, `removed`; it removes only `week/*.json`, `snapshot/*.json` and the three entity files that this run did not produce), `export.check(store, files) -> list[str]` (paths that differ, are missing or are extra).
- Command: `export_dashboard.py --store S --as-of YYYY-MM-DD [--check]`. `--as-of` is required here. It prints one `WROTE`, `SAME` or `REMOVED` line per file, then the notes, then `PASS export (W written, U unchanged, R removed)`. With `--check` it writes nothing and ends `PASS check` or `FAIL check: <paths>` with exit code 1. `copilot.py export` is the same command with `--as-of` defaulting to today, and it prints the date it used.
- Rules this task implements:
  - `week/<monday>.json` for every closed Monday week that has a collector-written `weekly.csv` row. `store_funnel` reads only rows whose `source` begins `live:asc analytics daily`; ratios come from the totals, with `numerator` and `denominator`; `by_market` from the two-letter segments. Other week families are `unavailable` with `no_source` until Phase 6.
  - `snapshot/<date>.json` for every sweep date (`ranks`, `coverage`) and every capture date of `popularity.csv` and `impression_share.csv` (`demand`, `impression_share`, each with `measured`). If `metrics/revenuecat_latest.json` exists, its `captured_at` day gets a `subscriptions` family read from its `overview`.
  - Among rows with the same key the latest `recorded` or `captured` wins, then the later line.
  - A row that cannot be read is named in the notes and skipped.

- [ ] **Step 1: Write the failing tests:**

```python
def test_closed_weeks_only(self):
    files, notes = export.build_all(SAMPLE, date(2026, 11, 14))
    self.assertEqual(sorted(p for p in files if p.startswith("week/")),
                     ["week/2026-10-19.json", "week/2026-10-26.json", "week/2026-11-02.json"])
    self.assertTrue(any("weekly.csv" in n and "left out" in n for n in notes))

def test_funnel_figures(self):
    f = export.build_all(SAMPLE, date(2026, 11, 14))[0]["week/2026-11-02.json"]["families"]["store_funnel"]["figures"]
    self.assertEqual(f["impressions"], {"value": 1500, "by_market": {"ua": 600, "us": 900}})
    self.assertEqual((f["page_cvr"]["value"], f["page_cvr"]["numerator"], f["page_cvr"]["denominator"]), (0.4, 64, 160))

def test_rank_snapshot(self):
    r = export.build_all(SAMPLE, date(2026, 11, 14))[0]["snapshot/2026-11-02.json"]["families"]["ranks"]["figures"]
    self.assertEqual((r["keys_read"]["value"], r["share_top30"]["numerator"], r["share_top30"]["denominator"]), (9, 4, 9))

def test_every_file_is_valid(self):          # contract.validate on canonical(obj) for every path: no problems
def test_two_exports_are_identical(self):    # build_all twice: equal canonical text for every path
def test_fresh_store(self):                  # header-only CSVs, no hypotheses: no week or snapshot files,
                                             # three entity files, valid, no exception
def test_bad_row_is_named_and_skipped(self): # a weekly.csv row with impressions "abc": a note names
                                             # "metrics/weekly.csv:<line>", the week is still exported without it
def test_correction_row_wins(self):          # a second 2026-11-02/all row recorded 2026-11-12 with 1600: value 1600
def test_as_of_in_the_past(self):            # as_of 2026-11-05: only week/2026-10-19 and 10-26; H005 is "due" by 2 days;
                                             # a note says verdicts are read as they stand
def test_check_reports_drift(self):          # write, edit one byte in data/, run --check: exit 1, the path is printed
def test_write_removes_stale(self):          # a stray data/week/2000-01-03.json is removed and printed as REMOVED
```

- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Extend `tests/test_boundaries.py` with `test_dashboard_has_no_network_and_no_clock` (an AST walk over `scripts/aso/dashboard/*.py`: none of the four imports, no `today` or `now` attribute call). Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: export_dashboard writes and checks the data files`.

---

## Phase 4 — The page

### Task 8: `build_site.py`

**Files:**
- Create: `scripts/aso/dashboard/site.py`, `scripts/build_site.py`, `assets/dashboard/template.html`, `style.css`, `app.js` (a shell that prints the app name), `places.json`
- Modify: `scripts/copilot.py` (the `build` command)
- Test: `tests/test_build_site.py`

**Interfaces:**
- Consumes: `contract.validate`, `contract.load_catalog`.
- Produces: `site.build(data_dir: Path, out_dir: Path, name: str) -> int`. It validates every file; on a problem it prints `INVALID <path>: <problem>` per problem and `FAIL data`, returns 1 and writes nothing. Otherwise it writes `<out_dir>/index.html` and prints `PASS site (<n> files, <bytes> bytes)`. Command: `build_site.py --data DIR --out DIR [--name TEXT]`; `copilot.py build` passes the store's `data/` and `public/`.
- The page: `template.html` with `{{CSP}}`, `{{STYLE}}`, `{{PAYLOAD}}`, `{{SCRIPT}}`. The payload is `{"name", "catalog", "places", "weeks": [...], "snapshots": [...], "hypotheses", "keys", "events"}`, weeks and snapshots sorted by id, serialised canonically with every `<` written as `<`. The policy: `default-src 'none'; style-src 'sha256-…'; script-src 'sha256-…'; base-uri 'none'; form-action 'none'`, the two hashes computed from the inlined text.
- `places.json`: `{"overview": [...], "ledger": [], "keywords": [...], "funnel": [...], "money": [...], "ads": [...], "in_app": [], "how": []}`, each a list of `family.key`.

- [ ] **Step 1: Write the failing tests:** `test_build_is_byte_identical_twice`, `test_invalid_file_writes_nothing` (exit 1, `INVALID`, no `index.html`), `test_csp_hashes_match_inlined_text`, `test_payload_cannot_close_its_script` (a key `a</script><script>alert(1)` in a temporary store: the built file has exactly two `</script>` closings), `test_no_outside_reference` (no `http://`, `https://`, `//` source or `@import` in the built file), `test_every_catalog_figure_has_a_place` (the union of `places.json` equals the catalog's closed figure keys, and names none beyond them).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement `site.py`, the template and the shell.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: build_site makes one self-contained page from the data files`.

### Task 9: Page shell, Overview, the figure panel

**Files:**
- Modify: `assets/dashboard/app.js`, `style.css`, `places.json`
- Create: `tests/page_smoke.js`, `tests/test_page.py`

**Interfaces:**
- Produces, in `app.js`: one global `ASO` with `ASO.render(route: string, payload: object, today: string) -> string` (the HTML of `<main>` for a route; pure, no DOM), `ASO.series(payload, key) -> [{id, value, unavailable}]`, `ASO.esc(text) -> string`, and `ASO.start()` (reads the payload, listens to `hashchange`, wires the panel). Routes: `#/`, `#/ledger`, `#/keywords`, `#/funnel`, `#/money`, `#/ads`, `#/in-app`, `#/how`. Every figure is drawn by one function that handles the three states: a value, an approximation (marked `≈`), unavailable (hatched, with the reason in words). Every string from the payload passes through `ASO.esc`.
- `tests/page_smoke.js <index.html> <route> <today>`: extracts the payload and the script from the built file, runs the script with `globalThis.document` undefined, prints `ASO.render(route, payload, today)`. `tests/test_page.py` builds the sample page once and is skipped when `node` is not on the path.
- Look: the canvas, artboard A. Tokens: page `#f9f9f7`, surface `#fcfcfb`, ink `#0b0b0b`, secondary `#52514e`, hairline `#e1e0d9`, axis `#c3c2b7`; blue ramp `#184f95`, `#2a78d6`, `#5598e7`, `#86b6ef`; orange `#eb6834`; worked `#0ca30c`, no-effect `#898781`, adverse `#d03b3b`, due `#fab219`; withheld and missing are hatched. Fonts named, not loaded: Inter, JetBrains Mono, Space Grotesk.

- A sweep is partial when `keys_read` is under half of `tracked_keys`. Headline rank figures and the band trend use the newest sweep that is not partial; a source's age uses its newest file of any kind.

- [ ] **Step 1: Write the failing tests** on the Overview with `today` `2026-11-14`: the sources strip names keyword ranks with `5 d` and store funnel with `4 d` and marks none stale; the six headline tiles hold `8 hypotheses`, `4 of 9` keys in the top 30, `64` first-time downloads; a family that is `no_source` renders the words `Not stored yet` and no `0`; with `today` `2026-12-01` the ranks source is marked `stale`. One more: `test_escape` (a hypothesis title `<b>x</b>` renders as text).
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the shell, the Overview and the panel (value and state, the two totals where the data has them, the catalog definition, source and fetch day, or the reason).
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: page shell, Overview tab and the figure panel`.

### Task 10: Ledger tab

**Files:**
- Modify: `assets/dashboard/app.js`, `style.css`
- Test: `tests/test_page.py`

- [ ] **Step 1: Write the failing tests** on `#/ledger`: the judge list holds `H005` with `closed 11 d ago` and `C001` with `closed 6 d ago`; the decide list holds `Q001` and `Q002` with their age in days; the next list's first row is `moon phase` with `14.00`; there are 8 squares, one per hypothesis, each with a `title` of id and state; the legend counts read `1 worked`, `1 no-effect`, `1 adverse`, `1 withheld`, `2 due`, `1 open`, `1 not shipped`; the timeline has one bar per hypothesis with a live day; the due card of `H005` says `1 read inside the window` and names its two queries.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the tab after artboard B: judge, decide, next; the squares; what worked and what hurt, each with verdict and basket movement and no typed proof line; the timeline from the first live day to `today`, with month and release marks; one card per due hypothesis with an inline SVG of its queries' series, the live day, the window end and today, and no target line.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: Ledger tab`.

### Task 11: Keywords tab

**Files:**
- Modify: `assets/dashboard/app.js`, `style.css`
- Test: `tests/test_page.py`

- [ ] **Step 1: Write the failing tests** on `#/keywords`: the band chart has three columns (`2026-10-05`, `2026-10-19`, `2026-11-02`) and a line saying one sweep was left out as partial; the share under `2026-11-02` reads `44.4%`; the storefront list reads `us 2 of 5` and `ua 2 of 4`; the gains list starts with `tide times` `+60`; the coverage block holds the four coverage figures; the key table has 12 rows and the brand rows are marked.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the tab after artboard A's keyword section, plus the table of every tracked key with its series as an inline SVG line.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: Keywords tab`.

### Task 12: Store funnel, Money, Apple Ads, In-app, How data gets here

**Files:**
- Modify: `assets/dashboard/app.js`, `style.css`
- Test: `tests/test_page.py`

- [ ] **Step 1: Write the failing tests:** `#/funnel` shows three closed weeks, `1500` impressions and `40.0%` for the newest, and a by-storefront table with `us` and `ua`; `#/money`, `#/ads` and `#/in-app` each render `Not stored yet` for every family that is `no_source` and contain no digit `0` standing for a figure; `#/how` names the three steps and the four codes.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement the five tabs after artboard A's sections. A family renders from whatever weeks hold it, so these tabs fill in by themselves once Phase 6 stores the series. The In-app tab groups an open family's keys by their section.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: Store funnel, Money, Apple Ads, In-app and How tabs`.

### Task 13: Golden test

**Files:**
- Create: `tests/test_golden.py`, `tests/golden/sample.sha256`

**Interfaces:**
- Produces: `python3 tests/test_golden.py --update` rewrites the manifest; as a test it exports the sample with `--as-of 2026-11-14`, builds the page, and compares the sha256 of every file under `data/` and of `index.html` with the manifest.

- [ ] **Step 1:** Write the test; run it. Expected: FAIL, no manifest.
- [ ] **Step 2:** Run `python3 tests/test_golden.py --update`, then the quality gates. Expected: `OK`.
- [ ] **Step 3:** Commit: `test: golden manifest of the sample's data files and page`.

---

## Phase 5 — First real page

### Task 14: Offline pass in MediaCleaner

No file in this repository changes. `STORE` is `/Users/Ruslan_Popesku/Desktop/MediaCleaner/marketing`; the commands run from this worktree.

- [ ] **Step 1:** `python3 scripts/export_dashboard.py --store "$STORE" --as-of 2026-11-14`. Expected: `PASS export`. Keep the notes: they list what the store cannot yet show.
- [ ] **Step 2:** Run the same command with `--check`. Expected: `PASS check`.
- [ ] **Step 3:** `python3 scripts/build_site.py --data "$STORE/data" --out /tmp/aso-page-1 --name Compresso`, then again into `/tmp/aso-page-2`; `cmp /tmp/aso-page-1/index.html /tmp/aso-page-2/index.html`. Expected: `PASS site` twice, `cmp` silent.
- [ ] **Step 4:** Compare three figures with the commands that own them: the hypothesis counts with `ledger.py --store "$STORE" --as-of 2026-11-14 report`, the newest sweep's bands with `ledger.py --store "$STORE" bands`, the number of closed funnel weeks with the notes of Step 1. Any difference is a defect of this plan's code: fix it under its task before going on.
- [ ] **Step 5:** Open `/tmp/aso-page-1/index.html` in the browser pane and look at every tab at desktop and phone width for overflow, collisions and empty places that should hold data.
- [ ] **Step 6:** Stop. Show the owner the page, the notes of Step 1 and `git -C "$STORE/.." status --short marketing/data`. Nothing is committed in that repository without his word.

---

## Phase 6 — Storage gaps

Each task: a pure function turns what the collector already fetched into rows; `aso.store.append_csv` appends the rows whose key is new; the export gains the family; `places.json` and the golden manifest are updated in the same commit, and the commit says which files changed.

### Task 15: Revenue, weekly cashflow, Apple Ads

**Files:**
- Modify: `scripts/pull_revenuecat.py` and its `scripts/aso/pull_revenuecat_*.py`, `scripts/aso/dashboard/export.py`, the sample store
- Test: `tests/test_series_money.py`

**Interfaces:**
- Produces: `revenue_row(data: dict) -> dict` for `metrics/revenue.csv` (`captured,active_subscriptions,active_trials,mrr_usd,revenue_28d_usd,new_customers_28d,active_users_28d,source`; key `captured`); `cashflow_weeks(by_country_daily, trials_by_country, daily_spend, as_of) -> list[dict]` for `metrics/cashflow_weekly.csv` (`week_start,country,transactions,new_trials,gross_revenue_usd,proceeds_usd,ad_spend_usd,source,captured`; key `week_start,country`; closed weeks only); `ads_weeks(report_rows, campaigns_meta, as_of) -> list[dict]` for `metrics/ads.csv` (`week_start,campaign_id,market,spend_usd,impressions,taps,installs,source,captured`; key `week_start,campaign_id`). The Apple Ads report request adds `tapInstalls` to its fields and is grouped by day and campaign.
- `export_snapshots` keeps writing `revenuecat_latest.json` and `cashflow.csv` for the commands that read them; the export stops reading `revenuecat_latest.json` once `revenue.csv` has a row.

- [ ] **Step 1: Write the failing tests** with small literal inputs: a daily series spanning two closed weeks and one open week yields rows for the two closed weeks only; appending twice adds nothing the second time; the exported `money` family of a week holds `net_cashflow_usd` equal to proceeds minus spend, in total and in `by_market`; `ads.ttr` carries taps and impressions as its totals; a week with spend and no install has `cpi_usd` unavailable with `no_data`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement; add three weeks of invented rows to the sample store.
- [ ] **Step 4:** Update the golden manifest; run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: revenue, weekly cashflow and Apple Ads are stored as series`.

### Task 16: In-app telemetry by closed week

**Files:**
- Modify: `scripts/pull_bigquery_telemetry.py`, `scripts/aso/dashboard/export.py`, the sample store
- Test: `tests/test_series_telemetry.py`

**Interfaces:**
- Produces: `analyze_telemetry(project_id, dataset_id, days=0, start=None, end=None)`: with `start` and `end` (dates) every query filters `_TABLE_SUFFIX` between them; `telemetry_rows(data: dict, week_start: date, captured: str) -> list[dict]` for `metrics/telemetry.csv` (`week_start,section,metric,numerator,denominator,source,captured`; key `week_start,section,metric`), one row per number in the `funnel`, `compression` and `monetization` blocks; the collector runs once per closed week not yet stored, newest first, at most 12 per run.

- [ ] **Step 1: Write the failing tests:** `telemetry_rows` on a literal `data` dict yields the expected rows; the SQL built with `start` and `end` contains both suffix bounds and no `CURRENT_DATE`; the exported `in_app` family holds `funnel.first_open` with its value and a ratio row with `numerator` and `denominator`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement; add invented rows to the sample store.
- [ ] **Step 4:** Update the golden manifest; run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: in-app telemetry is stored per closed week`.

### Task 17: Ratings, charts, releases

**Files:**
- Modify: `scripts/aso/commands/collect.py`, `charts.py`, `status.py`, `scripts/aso/dashboard/export.py`, the sample store
- Test: `tests/test_series_store_state.py`

**Interfaces:**
- Produces: `ratings_rows(asc_json, captured) -> list[dict]` for `metrics/ratings.csv` (`captured,market,ratings_count,rating_average,reviews,reviews_unanswered,source`); `chart_rows(results, captured) -> list[dict]` for `metrics/charts.csv` (`captured,market,genre,chart_type,position,depth,status,source`; `status` is `ok` or `beyond-depth`); `release_rows(versions_json, captured) -> list[dict]` for `metrics/releases.csv` (`version,state,state_date,source,captured`; key `version,state`). `reviews ratings`, `charts` and `status` append these when run with `--store`; they print what they printed before.
- Before writing code, run `asc reviews ratings --help` and `asc versions list --help` and take the JSON flag they document. If a command has no JSON output, its family stays `no_source` with that reason, and this is written under the task in this plan.

- [ ] **Step 1: Write the failing tests** from literal JSON: rows per storefront; a chart miss is a row with a blank position and `beyond-depth`; a version already stored in the same state adds no row; `events.json` lists releases whose state is the live one, with `state_date`; the `ratings` family carries `by_market`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement; add invented rows to the sample store.
- [ ] **Step 4:** Update the golden manifest; run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: ratings, chart positions and releases are stored`.

### Task 18: Lifecycle weeks, and `collect` runs every writer

**Files:**
- Modify: `scripts/pull_funnel.py`, `scripts/aso/commands/cycle.py`, `scripts/aso/dashboard/export.py`, the sample store
- Test: `tests/test_series_lifecycle.py`

**Interfaces:**
- Produces: `fold_lifecycle(rows, today=None) -> dict[(week, segment), dict]` and `write_lifecycle_weeks(out_dir, metrics, today=None) -> tuple[int, list]` in the shape of the existing `fold_reports` and `write_new_weeks`; rows go to `metrics/lifecycle.csv` with `source` beginning `live:asc analytics daily`. The report to read is the installation and deletion report `references/funnel-analytics.md` names. The export reads only rows with that source and a Monday `week_start`.
- `collect` runs, in order: versions and releases, ratings, funnel and lifecycle, revenue and cashflow and ads, telemetry, radar, then prints the ledger. Each step that fails prints its reason and the run goes on.

- [ ] **Step 1: Write the failing tests:** folding literal daily rows gives Monday weeks per segment; the open week is not written; the legacy sample row stays out of the export and is counted in the notes; `deletions_per_100` carries its two totals.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement; add invented collector rows to the sample store.
- [ ] **Step 4:** Update the golden manifest; run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: install lifecycle by closed week, and collect runs every writer`.

---

## Phase 7 — Real data

### Task 19: Live pass in MediaCleaner

Read-only against every source. It appends to that store's `metrics/*.csv`. It changes no Apple Ads entity and no metadata.

- [ ] **Step 1:** Ask the owner for a go, naming what will run: one `collect`, the telemetry backfill of up to 12 weeks, one full rank sweep of about an hour. Wait for it.
- [ ] **Step 2:** `python3 scripts/copilot.py collect --store "$STORE"`. Read every step's line; a step that failed is reported to the owner with its reason, not retried blindly.
- [ ] **Step 3:** The full sweep: `python3 scripts/ledger.py --store "$STORE" refresh --bundle <the bundle id in that store's config.md>`, run in the background.
- [ ] **Step 4:** Export with today's date, `--check`, build twice and `cmp`, as in Task 14.
- [ ] **Step 5:** Open the page; every tab now has history where its source has it. List for the owner each family still `unavailable`, with its code and reason.
- [ ] **Step 6:** Stop. Show `git status --short` of that repository's `marketing/`. The owner decides how the appended rows and `data/` are committed.

---

## Phase 8 — The skill itself

### Task 20: `due` and `check`

**Files:**
- Create: `scripts/aso/dashboard/clean.py`
- Modify: `scripts/aso/ledger_state.py`, `scripts/copilot.py`
- Test: `tests/test_due.py`, `tests/test_clean.py`

**Interfaces:**
- Produces: `reads_due(hyps, rows, as_of) -> list[dict]` with `id`, `market`, `queries`, `day` for every live rank hypothesis and each of the last three days of its window that is on or before `as_of` and has no sweep reading its basket; `copilot.py due [--as-of D]` prints them, one line each, or `Nothing due.`
- Produces: `clean.check(data_dir: Path, store: Path) -> list[str]`: problems found in `data/`. It always flags the values of the store's own `config.md` identifiers (App ID, provider token, Apple Ads account, GA4 property, Firebase ids, RevenueCat project), e-mail addresses and anything shaped like a key or token. It also flags whatever `NEVER_PUBLISH` lists. `copilot.py check` prints `PASS clean` or one line per problem and exits 1.

- [ ] **Step 1: Write the failing tests:** on the sample with `as_of` `2026-11-03`, `reads_due` returns `H005` for `2026-11-01` and `2026-11-03` and not for `2026-11-02`; a `data/` file holding `1000000001` fails the check and names the file; the sample's own `data/` passes.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement both, with `NEVER_PUBLISH` empty.
- [ ] **Step 4:** **The owner writes `NEVER_PUBLISH`** in `clean.py`: the list of what must never leave his repository beyond identifiers (for example revenue figures, or the keyword basket). It is his decision about his data, five to ten lines.
- [ ] **Step 5:** Run the quality gates. Expected: `OK`.
- [ ] **Step 6:** Commit: `feat: the reads calendar and the clean check`.

### Task 21: Generated `STATE.md`

**Files:**
- Modify: `scripts/aso/dashboard/export.py`
- Test: `tests/test_state_md.py`

**Interfaces:**
- Produces: `export.state_md(files: dict, as_of: date) -> str`: one screen of Markdown built only from the exported objects: as-of day, each source's last day, the hypothesis counts, the due list, the queue, the newest headline figures. `export.write` writes it to `<store>/STATE.md` only when that file is absent or starts with the line `<!-- generated by export_dashboard; do not edit -->`. Otherwise it prints `KEPT STATE.md: written by hand, archive it first` and leaves it.

- [ ] **Step 1: Write the failing tests:** the text starts with the marker line; it holds `2 due`, `H005` and `C001`; a hand-written `STATE.md` is kept and the `KEPT` line is printed; two runs give the same text.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: STATE.md is generated from the data`.

In MediaCleaner the hand-written `STATE.md` is archived by the owner's word only: `git mv marketing/STATE.md marketing/reports/STATE_until_2026-11.md`, then one export.

### Task 22: `SKILL.md` as a router, documents, version

**Files:**
- Modify: `SKILL.md`, `README.md`, `CHANGELOG.md`, `ROADMAP.md`, `package.json`, `references/state-store.md`, `references/commands.md`, `assets/store-template/`
- Create: `references/collect.md`, `references/export-and-page.md`, `references/judge.md`, `references/actions.md`
- Test: `tests/test_skill_md.py`

- [ ] **Step 1: Write the failing tests:** `SKILL.md` is at most 12,000 bytes; it has the sections `Start here`, `Rules for every step`, `Collect`, `Export and page`, `Judge a hypothesis`, `Propose a hypothesis`, `Actions`; every `ios-aso-copilot <command>` it names exists in the parser; every `references/*.md` it links exists; the rules section holds the four hard rules of the spec.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Rewrite `SKILL.md` as a router and move its detail into the reference files; nothing is dropped, each moved passage lands in one of them. `references/state-store.md` gains the new CSV files and the `data/` layer and loses the hand-written `STATE.md`. The store template gains header-only copies of the new CSV files. `package.json` goes to `3.0.0`; `CHANGELOG.md` gets the entry.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `docs: SKILL.md is a router; the store reference names the series and the data layer`.

---

## Phase 9 — Publishing

### Task 23: The Pages workflow, behind the owner's decision

Blocked until the owner says whether the page is public or private. Until then the page is the local file of Tasks 14 and 19.

**Files:**
- Create: `assets/workflows/aso-dashboard.yml`, `assets/workflows/rank-reads.yml`, `references/publish.md`
- Test: `tests/test_workflows.py`

- [ ] **Step 1: Write the failing tests:** both files parse as the workflow shape (top-level `name`, `on`, `jobs`); the dashboard workflow checks out this skill at a full commit hash, runs `export_dashboard.py --check`, `copilot.py check` and `build_site.py`, and names no secret; the rank-reads workflow is `workflow_dispatch` and a schedule, runs `copilot.py due` and then `ledger.py refresh` for the due markets only, and commits only `marketing/metrics/ranks.csv`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Write the two templates and `references/publish.md`: the steps to copy them into an app repository, the visibility setting to choose first, and that neither workflow holds a source credential.
- [ ] **Step 4:** Run the quality gates. Expected: `OK`.
- [ ] **Step 5:** Commit: `feat: workflow templates for the page and for scheduled rank reads`.
- [ ] **Step 6:** Installing either workflow in MediaCleaner is the owner's step, after his decision.
