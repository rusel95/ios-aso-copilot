# Marketing metrics without invented funnels

Use `scripts/funnel_visualizer.py --store "$STORE" --segment search --market us`. The script
renders only recorded values; missing metrics stay absent. `--format json` preserves null versus zero.
An ambiguous week/segment selection is an error, not permission to take the last CSV row or add
unique-device counts. `--price` cannot establish revenue and is rejected; use the economics script
for a labelled scenario.

## Definitions before ratios

Record period, timezone, storefront, source type, version/product where available, metric unit,
report identifier, data freshness and completeness. ASC impressions include page views, so
`Product Page Views ÷ Impressions` is not a tap-through rate. Users may download directly from search;
all downloads divided by page views is not page-view conversion. ASC conversion uses total downloads
and pre-orders divided by unique-device impressions, with pre-order counting rules. Prefer the reported
rate; do not recompute it from ambiguous legacy columns.

Storefront observations and in-app events are different populations. Same-week trial starts are not
necessarily from same-week downloads. Trial starts are not payments. Paying users are not transaction
counts, revenue is not proceeds, and estimated proceeds are not a bank deposit. Use mature cohorts
for trial-to-paid conversion and reconciliation with financial reports for realized payments.

ASC Search can include Apple Ads. Keep paid query reporting separate. Campaign links can help with
external attribution, subject to Apple's reporting eligibility and privacy limits; they do not expose
organic installs by keyword. Browse is descriptive context, not an automatic causal control.

## In-App Product Analytics (Google Analytics / Firebase)

When `$STORE/scripts/pull_ga.py` is configured, in-app telemetry bridges the gap between App Store acquisition and downstream monetization:
- **Engagement Depth:** `Avg Engagement Duration` (seconds), `Sessions per User`.
- **Product Velocity:** `media_swiped` count and `swipes_per_user` (verdicts: kept, deleted, compressed) — measures whether users actually engage with the core mechanic before dropping off or converting.
- **In-App Funnel:** `first_open` → `session_start` → `media_swiped` → `paywall_shown` → `cleanup_completed` → `rating_prompt_requested`.
- **Uninstalls:** not observable in GA4 on iOS — see § Deletions below.
- **Reconciliation:** Storefront downloads (ASC) are acquisition; `first_open` / `session_start` (GA4) are activation. Comparing downloads to `first_open` measures the drop-off between store install and first launch. Comparing `media_swiped` to `paywall_shown` measures activation depth before monetization.

## Deletions — the end of the lifecycle

App Store Connect's **"App Store Installation and Deletion Standard"** analytics report (same ONGOING
request as the funnel reports) carries `Install` and `Delete` events per day, territory, app version and
source, plus `App Download Date` — when that device installed. It is the only first-party source for
uninstalls on iOS: Firebase's `app_remove` is Android-only, and an APNs `410 Unregistered` needs a push
server and arrives days late.

The store's `pull_funnel.py` should request it and write `metrics/lifecycle.csv`
(`first_installs_optin`, `deletions_optin`, `deleted_within_1d`, `median_days_to_delete`);
`copilot.py funnel` prints it after the weekly summary, and a full audit must report it next to the
GA4 funnel. Rules for reading it:
- **Opt-in sample, not totals.** Only devices sharing analytics with developers are counted. Compare
  installs with deletions inside this report; never divide by `weekly.csv` downloads.
- **Not a cohort rate.** A deletion in the window may belong to an install before it.
- `Date` is the event day, bucketed into its week for older data; a negative
  `Date − App Download Date` is that bucketing and is excluded from timing.
- The signal that matters is **time to delete**. Deletion within a day of install means the first
  session failed (permission, first screen, value never shown); deletion after weeks is ordinary churn
  or the job being done. Map fast deletions against the GA4 step where those users stopped.

## Diagnosis

There are no universal hardcoded TTR, page-CVR or paywall-CVR cutoffs in this skill. Read an eligible
Apple peer benchmark with its cohort, date and metric definition; compare like populations. A low
ratio may reflect traffic mix, missing events or device/language differences before creative quality.
Inspect the counts and uncertainty before recommending an icon or paywall change. With missing data,
report `not_assessed`; never `healthy`.

Sources checked 2026-09-24:
- https://developer.apple.com/help/app-store-connect-analytics/reference/metrics-definitions/
- https://developer.apple.com/help/app-store-connect-analytics/benchmarks/peer-group-benchmarks/
- https://developer.apple.com/help/app-store-connect-analytics/acquisition/acquisition/
