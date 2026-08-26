# Roadmap

What is still to do. What has landed is in [`CHANGELOG.md`](CHANGELOG.md).
An item that closes moves there in the same commit that closes it — gaps in numbers are in the changelog.

Items are numbered in the order they were found. Tags: **[verified]** confirmed by running it.
**[open]** needs a decision or design before implementation.

---

## P0 — Data integration: connect all available signals

The skill currently operates on keyword rank (iTunes Search API) and hypothesis state.
The full picture requires correlating **all available data sources** — only then can you answer
"why did conversions drop?" or "which keyword change drove downloads?". Every item below
represents a data source that is accessible but not yet wired into the skill's auto cycle.

**R-23 [open] ASC App Analytics — impressions, product page views, installs, sessions**
`asc analytics request --app APP_ID --access-type ONGOING` creates a reusable analytics report.
Reports include: App Units (installs), Sessions, Active Devices, Crashes, Product Page Views,
Impressions, Impressions Unique, Proceeds, Paying Users, In-App Purchases — all breakable by
Territory, Source Type, Device, App Version.
This is the funnel: Impressions → Product Page Views → Installs → Sessions.
Without it, keyword rank improvements cannot be correlated to actual download changes.
Implementation: add `scripts/fetch_analytics.py` that calls `asc analytics download` and
appends to `metrics/weekly.csv` automatically each `auto` cycle.
See: `asc analytics --help` for full endpoint map.

**R-24 [open] RevenueCat — subscription revenue, trial conversion, churn**
RevenueCat MCP server is available (configured in `.kiro/settings/mcp.json`).
Exposes: MRR, ARR, active subscriptions, new subscribers, churned, trial starts,
trial conversions, refunds — all filterable by country, product, date range.
Integration target: `auto` cycle Step 2 pulls RevenueCat overview + country breakdown
and writes to `metrics/weekly.csv` alongside ASC installs. This makes the full funnel visible:
Keyword rank → Impressions → Installs → Trial → Paid → Churn.
Key calls: `get_overview_metrics`, `get_chart_data` (mrr, trials, conversion_to_paying).

**R-25 [open] ASC Sales & Trends reports — paid installs, in-app purchases per country**
`asc analytics sales --vendor VENDOR_ID --type SALES --subtype SUMMARY --frequency DAILY`
Returns daily/weekly unit sales and proceeds per country, per SKU. Complements RevenueCat
(which tracks subscriptions) with one-time purchase and free download counts.
Blocker: requires vendor number — not yet retrieved (FINDINGS.md §Vendor number search).
Implementation: add `scripts/fetch_sales.py`.

**R-26 [open] Apple Search Ads — impressions, taps, installs, CPA per keyword**
`asc ads reports campaigns --org ORG_ID` returns campaign-level metrics.
`asc ads reports adgroups` and `asc ads reports keywords` give keyword-level: impressions,
taps, conversions, spend, CPA. This is the paid acquisition funnel complement to organic rank.
Requires: active campaign for Hush in org 23140040. Once campaign exists, keyword popularity
scores also unlock (R-10).
Implementation: `scripts/fetch_ads_report.py` — weekly pull of keyword-level performance.

**R-27 [open] PostHog — in-app behaviour (sessions, feature usage, paywall views)**
PostHog is live (`phc_mOOeqJCMhLNkeyuzg4bizA0txCCdZnc3eiDnag1CNbj`, us.posthog.com).
PostHog MCP is available in the session. Currently 0 events being tracked (not wired up in app).
When wired: tracks which sounds are played, timer usage, settings opens, paywall impressions,
paywall conversions. Completes the in-app funnel: Install → First Sound Played → Paywall → Buy.
Implementation: 1) Wire PostHog events in Swift app (separate task). 2) Add `scripts/fetch_posthog.py`
to pull weekly active users, paywall conversion rate into `metrics/weekly.csv`.

**R-28 [open] Unified weekly metrics schema**
`metrics/weekly.csv` currently has gaps and inconsistent columns. With all sources above, define
a canonical schema:
```
date, impressions, page_views, installs, sessions, active_devices,
mrr_usd, new_subscribers, trials_started, trial_conversion_pct,
top_keyword_rank_us, top_keyword_rank_de, reviews_count, crashes
```
Every `auto` cycle Step 2 fills what it can, marks the rest `absent:<reason>`.
This is the single source of truth for "are we growing?".

---

## P1 — Correctness: existing keyword ranking

**R-10 [open] Apple Ads popularity scores as volume proxy**
`rank_audit.py` currently uses `total_search_results` as volume proxy (rough ±300% accuracy).
Apple Search Ads API endpoint `POST /v5/search/targeting/keywords/suggestions` returns
`popularityRange: {min, max}` (5–100 scale) — the only official Apple volume signal.
Requires: Hush app added to an ASA org, `asc ads` configured for that org.
Blocks: opportunity scores being meaningful rather than directional.
See: `FINDINGS.md §ASA` for setup steps.

**R-11 [open] Keyword difficulty uses only top-1 competitor**
Current formula: `log10(top1_total_ratings)`. Should use top-3 or top-5 weighted average to
avoid outlier distortion (e.g. one giant app dominating a niche that has weak #2–#5).

**R-12 [open] Rate limiting and retry logic in rank_audit.py**
iTunes Search API rate limits are undocumented. At 2 req/sec the script sometimes gets empty
responses (treated as "absent"). Need: exponential backoff on empty response + 429 detection.
Current workaround: `--delay 0.5` flag.

---

## P1 — Capability gaps (materially limits usefulness)

**R-13 [open] Historical rank tracking**
`rank_audit.py` produces a snapshot. `check_ranks.py` appends to `metrics/ranks.csv` for a
fixed set of terms. Need: rank_audit to also append its results to ranks.csv in a consistent
schema, so trends are visible over time.

**R-14 [open] Competitor keyword gap analysis**
Find keywords where competitor A ranks #1–5 but we are absent. Currently we only check our
own rank. Requires: searching by competitor bundle ID, not just ours.

**R-15 [open] Metadata character-count validator in auto mode**
Step 6 of auto drafts metadata changes. ASC title ≤ 30 chars, subtitle ≤ 30, keywords ≤ 100.
`asc metadata validate` covers this but only after pull. Need offline pre-validation before
the `plan` step so the agent doesn't draft changes it can't apply.

**R-16 [open] Multi-app support tested**
Skill claims to work for any app via `config.md`. Tested only on Hush (WhiteNoise).
MediaCleaner is the next candidate. Needs: one real end-to-end run on a second app to
confirm `$APP_ID`, `$BUNDLE_ID`, `$STORE` all resolve correctly and no Hush-specific
assumptions remain in references/*.

**R-17 [open] rank_audit output integrated into auto cycle**
`auto` mode Step 3 currently calls `check_ranks.py` for a fixed keyword list. Should call
`rank_audit.py --expand-from-hints` and use the opportunity leaderboard to drive Step 5
(hypothesis drafting): next hypothesis = highest-opportunity unranked keyword cluster.

---

## P2 — Polish and discoverability

**R-18 [open] npm publish**
`package.json` exists. Publishing to npm enables `npx ios-marketing-ops install` without
installing from GitHub. Requires: npm account, CI publish workflow.

**R-19 [open] Kiro power packaging**
Kiro powers can bundle MCP servers + skills. Wrap this skill as a Kiro power so it appears
in the Kiro power marketplace and can be installed via the Kiro UI (no CLI needed).

**R-20 [open] Progress output for long rank_audit runs**
Full 25-market audit takes 10–20 minutes. Currently the only progress signal is one line per
market printed to stdout. Need: a `--progress-file` flag that writes a JSON status file
every N queries so a watcher script or UI can show live progress without tailing stdout.

**R-21 [open] ASA campaign automation**
`references/apple-ads.md` documents Apple Ads setup manually. Auto mode could draft a
campaign structure (Search, Brand defense, Competitor) and queue it for approval. Currently
fully manual. Requires R-10 (ASA API connectivity) first.

**R-22 [open] Review reply templates**
`references/playbooks.md` mentions review management. No automation exists yet. Add:
sentiment classification of new reviews + templated reply drafts queued for human approval.

---

## Questions waiting on a decision

**Q-01** Should `rank_audit.py` use `--expand-from-hints` by default (slower but better data),
or keep fallback keyword lists as the default (faster, predictable runtime)?
Current default: fallback lists. Hint expansion requires `--expand-from-hints` flag.
Evidence: hint expansion takes ~2 min/market vs ~30 sec/market for fallback.

**Q-02** Should the skill track 4 markets (US/GB/DE/UA per original design) or all 25 markets
that `rank_audit.py` now covers? Tracking all 25 in `metrics/ranks.csv` weekly is 500+
rows/week. May be noise rather than signal at P2-cold volume.
Current answer: rank_audit runs all 25, `check_ranks.py` tracks the 19 from the original list.

**Q-03** What is the canonical mapping between ASC locale codes and ASA storefront codes?
Some discrepancies exist (e.g. `no` in ASC vs `143447` storefront for Norway). Not yet
verified exhaustively.
