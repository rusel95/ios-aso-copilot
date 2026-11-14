# Collect: reading the sources into the store

Collection is the only part of the skill that touches the network. It reads; it appends rows to the store's
`metrics/*.csv`; it changes nothing outside the store. Everything after it (`export`, `build`, `check`, `due`,
the ledger report) reads files only, so the same store gives the same answer on the same day.

## Resolve the app and the single state store

- `SKILL_DIR` is the real directory containing this skill (resolve symlinks).
- From the app repo run `git worktree list --porcelain`. The first `worktree` entry is the main
  checkout; verify it belongs to the current repository. Do not infer this from missing branch brackets.
- `STORE` is that checkout's `marketing/`, shared by all its worktrees. Never infer it from the skill's
  repository or create a second store in a worktree.
- Read `config.md` for the exact App ID and working version. Then read only the state files and handbook
  sections needed for this request; a full cycle needs `queue.md`, hypotheses, decisions and relevant
  metrics. `STATE.md` is written by the export (`references/export-and-page.md`). State is a cache, not a
  data source.
- Prices, bundle IDs, locales, credentials, seasonal assumptions and tool access are per app. Never
  carry them from a previous project. Missing identity means report that gap before app-specific API calls.
- App Store reads in `copilot.py` (`status`, `reviews`, `cycle`) must reject a missing or `TODO` App
  ID/version before calling ASC. Funnel and GA pulls must use the app's exact configured source identity
  and property; funnel helper `APP_ID` must match the store, and GA4 property must come from that store's
  `config.md` or an explicit one-off override. Never use an environment property, `STATE.md`, or a
  cross-app mapping. If identity is missing, stop rather than reusing another app's values. Credentials
  come only from an explicit argument, this app's config path when that file is on this machine, else
  `GOOGLE_APPLICATION_CREDENTIALS` or local Application Default Credentials loaded by the Google client
  library; a config path that leads nowhere is said aloud and the machine's own settings are used. If
  the installed CLI differs, inspect its `--help` and code before running; never accept an undocumented
  fallback identity. For Firebase apps, resolve project and iOS app with Firebase CLI, then verify the
  numeric GA4 Property ID via Firebase Management API `projects.getAnalyticsDetails`; require its stream
  to map to the selected Firebase App ID. Firebase CLI reads project/app SDK config but does not fetch
  historical GA4 event reports; see `references/google-analytics.md` for the Data API and OAuth scope.
  If the selected app defines `**GA4 Funnel Steps**` in `config.md`, use only that app's ordered events
  that represent users advancing through the same path; keep diagnostic, eligibility, suppression and
  branch events separate, and never reuse another app's event taxonomy.
- Keep one global skill installation. Project links may point to it; do not copy skill directories.
  Preserve unique local additions before replacing a copy. The installer and agents must resolve links.

## Many projects

One store per project: `<app repo>/marketing`. Every command takes `--store` (default `./marketing`), and
everything a command writes lands inside that store: rows in `metrics/`, the exported files in `data/`,
the page in `public/` (or wherever `build --out` says). Two projects never share a file. What they share
is the machine: the `asc` login under `~/.asc`, the Google login, and Apple's request limits, which is why
only one rank sweep and one App Store Connect analytics pull run at a time across all projects.

How a project is fetched is written in its own `config.md` (App ID, bundle id, GA4 property and
credentials file, Firebase project, RevenueCat project, Apple Ads profile and account, optional
`**Charts storefronts**` and `**Charts genres**`). A stage whose line is missing says `not set up` and reads
nothing; it never borrows another project's value.

## Route to the smallest supported operation

Do not run a full cycle for a narrow question. `copilot.py status` is read-only but queries live ASC
versions and ratings as well as the local ledger; it is not an offline cache read. Its ledger output
stops after section A; run the local ledger report if the user also needs movement or priority (B/C).
`collect` (also spelled `cycle`) pulls more data and appends to the store, so reserve it for a full audit, the weekly pass or explicit auto iteration.

```bash
COPILOT="$SKILL_DIR/scripts/copilot.py"

# Current version/rating reads and local hypothesis/rank summary:
python3 "$COPILOT" status --store "$STORE"

# Full CLI collection pass, only when the request needs it:
python3 "$COPILOT" collect --store "$STORE"
```

### The pass, stage by stage

`collect` runs its source stages side by side (`--jobs 1` runs them one after another) and prints them in
stage order, each under `▶ [n/N]`, then a `STAGE SUMMARY` table: `ok`, `partial`, `failed` or `skipped`, with
the reason. Exit `2` means at least one stage needs a look.

| Stage | Reads | Appends to |
|---|---|---|
| Versions | App Store Connect | nothing (printed) |
| Reviews & ratings | App Store Connect, the public lookup | `ratings.csv`, `releases.csv` |
| Funnel | App Store Connect analytics, three daily reports at once | `weekly.csv`, `lifecycle.csv` (closed Monday weeks) |
| In-app telemetry | GA4 | printed; `ga4_funnel.csv` when asked |
| In-app weeks & charts | BigQuery; the category chart feeds | `telemetry.csv`; `charts.csv` when `**Charts storefronts**` is set |
| Demand radar | Apple Ads | `popularity.csv`, `popularity_cut.csv`, `impression_share.csv` |
| Revenue | RevenueCat, Apple Ads | `revenue.csv`, `cashflow_weekly.csv`, `ads.csv`, `revenuecat_latest.json` |
| Rank sweep (`--ranks`) | App Store search, twenty a minute | `ranks.csv` |
| Ledger report | the store | nothing (printed); waits for all the above |

A week is written once it has closed, only when both funnel reports were read (a half-read week would
stay half empty), and only when the reports already hold a day after it: Apple publishes a day about two
days late, so a pass on the Monday after a week leaves that week to the next pass rather than write it
without its Sunday. Run the weekly pass on a Wednesday or later and it carries the week just ended. App Store Connect limits analytics downloads; when it says `rate limited … asked to wait
12m`, the funnel stage fails for this pass and keeps what it downloaded, and the next pull continues from
there. A first pull (about a hundred daily reports) can take two passes.

Run the pass in a subagent on a cheaper model when the harness has one: it is long and mechanical, and
its output is large. Give it the exact command, the store, and the limits (no commit in the app
repository, no Apple Ads or metadata change); read its stage table and reasons, then judge in the main
session.

### Full-cycle invocation

`ios-aso-copilot --full [app and scope]` is the skill's explicit full-cycle mode. It is a skill
argument, not a `copilot.py` flag. After resolving the store, App ID, exact bundle ID and fixed query
basket, run `python3 "$COPILOT" collect --ranks --store "$STORE"`. The full Top-200 rank refresh
(`ledger.py refresh`) is then one stage of the pass and runs beside the ASC version, review and funnel
reads, GA4, the in-app weeks, the demand radar and RevenueCat; the ledger report waits for all of them.
Rank requests still run serially with the 3s guard, so the sweep is the longest stage: running it beside
the others cuts the wall-clock time without changing its request rate. Rows are dated by each query's own
`observed_at`, so a refresh that crosses local midnight lands on two days; that is correct.
Once the pass finishes, inspect every stage's status and warning in the stage table, then generate the
final local `ledger.py report --as-of`.
Use that completed report for hypothesis decisions and sections A/B/C. Do not parallelize or shorten
rank requests, start a second full refresh (Apple's limit is per machine: one sweep at a time across all
apps), or use a mid-refresh ledger as final. If requests fail, wait out the source cooldown and retry
only those rows with `ledger.py refresh --failed-only`.
Do not stop at CLI output. Keep missing stages explicit and judge a due hypothesis only if its
predeclared signal has comparable evidence. The mode permits local evidence/report updates; it does
not authorize metadata publishing, campaign changes, or spend changes. An explicit narrower user
request still takes precedence.

Example: `[$ios-aso-copilot](SKILL.md) --full MyApp, App ID <app-id>`.

| Request | Narrow route | What it does |
|---|---|---|
| Current status | `python3 "$COPILOT" status --store "$STORE"` | Live ASC version/rating reads plus ledger section A; use `ledger ... report` for B/C |
| Review only | `python3 "$COPILOT" reviews ratings --store "$STORE"` or `python3 "$COPILOT" reviews unreplied --store "$STORE"` | Reads ratings or unresponded reviews |
| Existing funnel snapshot | `python3 "$COPILOT" funnel --store "$STORE"` | Reads local `weekly.csv`; no pull |
| Refresh funnel / in-app data | `python3 "$COPILOT" funnel --pull --store "$STORE"` / `python3 "$COPILOT" ga --days 14 --store "$STORE"` | Makes remote reads and appends closed Monday weeks to `weekly.csv` and `lifecycle.csv`; the daily reports are kept per app under `~/.cache/ios-aso-copilot/funnel/<app id>` and a later pull asks only for new days |
| RevenueCat & Cashflow (ROAS) | `python3 "$COPILOT" rc --store "$STORE" --export` (alias: `cashflow`) | Pulls live RevenueCat 3-tier revenue (`revenue` Gross, `revenue_net_of_taxes`, `proceeds` Net), MRR, trials, and joins with Apple Ads spend (`asc ads`) by flight, rolling window, and country; writes `metrics/revenuecat_latest.json` and `metrics/cashflow.csv`, and appends `revenue.csv`, `cashflow_weekly.csv` and `ads.csv` |
| BigQuery Telemetry & Cohorts | `python3 "$COPILOT" telemetry --store "$STORE" --export-md` | Pulls 4-pillar raw BigQuery telemetry (Funnel, Compression Engine, Retention curve, Paywall CVR) |
| One-screen brief (ASC state, Top-200 bands per storefront, all hypotheses, store funnel, cashflow) | `python3 "$COPILOT" brief --store "$STORE"` | Reads only (`asc` reads + local files + RC cashflow digest); the Top-200 table alone is `ledger.py --store "$STORE" bands` |
| Hypothesis/rank ledger | `python3 "$COPILOT" ledger --store "$STORE" report [--as-of YYYY-MM-DD]` | Local report; `--as-of` fixes date-dependent states; `refresh` queries Apple and appends observations; `draft` writes a hypothesis |
| Apple demand (popularity, impression share, keyword lens) | `python3 "$COPILOT" radar --store "$STORE" pull` · `report` · `keywords [--campaign ID]` | `pull` reads Apple Ads (needs the Apple Ads lines in config.md), appends weekly popularity and impression-share history and skips a week already stored; `report` reads it offline; `keywords` joins the keyword report to keyword text |
| Full audit / auto iteration | `python3 "$COPILOT" collect --store "$STORE"` | Reads versions/ratings/reviews, pulls ASC analytics impressions, funnel and lifecycle, GA, the in-app weeks, chart positions, the demand radar, RevenueCat + Apple Ads Cashflow side by side, then reports the ledger |
| Explicit full skill run (`--full`) | `python3 "$COPILOT" collect --ranks --store "$STORE"`: the rank sweep runs beside the other stages | Completes both mechanical collection and the skill's live-source analysis, hypothesis decisions, Cashflow/ROAS accounting, and A/B/C report |

Check `python3 "$COPILOT" --help` or the specific script's `--help` when a flag is unfamiliar or the installed
version differs. The CLI `collect` is only the mechanical collection pass: it refreshes keyword ranks only with
`--ranks`, and does **not** audit Apple Ads, inspect metadata exposure, judge hypotheses, or choose/write a change. The skill
does those remaining steps only when they fit the user's requested scope. Avoid repeating successful
reads the same cycle already returned; use a narrow command to recover a missing stage. If the cycle
needs only one analytics source, use its narrow command or pass `--skip-pull` / `--skip-ga` / `--skip-rc`. Its final
footer only means the command sequence ended; inspect each stage because the process may finish with
missing or failed sources. The CLI returns `2` when a collection stage fails or required output is
unavailable, and forwards nonzero codes from narrow commands. Ledger row warnings are printed in its
report and may still accompany exit `0`; inspect them. Blank output is unknown, not proof of zero rows.
A zero exit code is not a data-completeness certificate.

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
not "unranked", not a healthy funnel, and not permission to populate examples as actual data. A live
source is a new snapshot, not a replay of an earlier one; do not claim historical values unless the
source or a saved export preserves them. Use a bounded retry supported by the command, respect
`Retry-After`, and stop on terminal auth/config errors instead of looping or fanning out requests.

## Status output

Give a compact account of live/candidate versions, open ASO and channel hypotheses, observed metrics
with units, periods and dates, gaps in the ledger, pending actions, and one useful next step. Label
`captured_at` separately from the measured `as_of` period; include timezone, source, filters and
completeness when available. Use
`scripts/funnel_visualizer.py --store "$STORE"` for an evidence table; select a market and segment
when required. Do not infer page conversion, paid subscribers, source shares or bank payouts from
unjoined totals. Do not diagnose a bottleneck from a generic benchmark.

## One execution cycle: the reading steps

1. Use the route table; do not rerun reads already completed successfully. Verify app identity and live/
   candidate versions from this run's source output. Reconcile stale state only within the authorized scope.
2. For a full audit, fetch the weekly data that is configured and relevant: ASC funnel via
   `pull_funnel.py` in the app store or skill scripts when present, and GA4/Firebase via
   `$SKILL_DIR/scripts/pull_ga.py` (see `references/google-analytics.md`). `copilot.py collect` attempts
   both pulls and records a failure/skip in its output. The funnel is pulled with the skill's own
   `pull_funnel.py` even when the app store carries a script of that name: only it folds the daily
   reports into closed Monday weeks, which is all the export shows. It keeps the source CSVs per app
   under `~/.cache/ios-aso-copilot/funnel/<app id>` and prints the exact path. The pass does not make
   missing scripts or credentials appear. GA4 may require the
   app's existing virtual environment and provider library. Do not install
   packages, create credentials, or widen the date window just to fill a report. Record source, app,
   period, `as_of`, capture time, timezone, filters, units and completeness when the source provides them.
   `captured_at` is retrieval time; `as_of` is the measured period boundary. If a tool cannot persist a
   field or source history, state that limitation. Store downloads and `first_open` are different
   populations; reconcile only comparable storefronts and periods. Missing fields stay blank with a
   reason. Never invent a baseline.
3. Audit App Store customer reviews and ratings only as needed: use `asc reviews ratings --app "$APP_ID" --all`
   and the documented read command for unresponded reviews (see `references/reviews-and-ratings.md`). Report rating counts,
   averages by country, star distribution, qualitative sentiment, praised features to amplify in
   ASO metadata/creatives, and list unresponded reviews requiring developer replies. A failed or empty
   response is unavailable/unknown unless the tool confirms zero rows. Replies remain drafts unless the
   user authorized publication under `references/commands.md`.
4. Refresh a fixed query basket. Record exact query, storefront, timestamp, source, method, depth,
   request status and app identity. Keep new discovery queries separate from paired comparisons.

The judging steps are in `references/judge.md`; the steps that change something are in `references/actions.md`.
