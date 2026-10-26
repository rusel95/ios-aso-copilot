# In-App Product Telemetry via BigQuery (Firebase / GA4 Raw Events)

Use `python3 scripts/copilot.py telemetry --store "$STORE" [--days N] [--export-md]`.

BigQuery exports raw, unaggregated, row-level Firebase / GA4 event streams (`analytics_<propertyId>.events_*`).
Unlike App Store Connect (which only tracks impressions and downloads) and the GA4 Data API (which suffers from
sampling, strict API quotas, and fixed dimensions), BigQuery provides complete visibility into in-app behavior,
core feature utility, retention decay, and monetization mechanisms.

## The 4 Telemetry Pillars

### 1. Activation & Conversion Funnel
A true ordered sequence of user milestones from download to purchase:
- `first_open` (100% baseline)
- `photo_access_gate_shown` → `photo_access_granted` (Permission gate drop-off)
- `cold_scan_finished` (Library analysis completion)
- Core interaction: `media_swiped` (User actively engaged with the core mechanic)
- Value delivery: `cleanup_completed` / `compression_completed`
- Monetization: `paywall_shown` → `purchase_started` → `purchase_finished` (`result = 'purchased'`)

### 2. Core Feature Value Engine
Measures whether the app is delivering its core promise and how much tangible utility is produced:
- **Compression Efficiency**: `compression_initiated` vs `compression_completed` vs `compression_failed` by `media_type` (`video`, `live_photo`, `image`).
- **Storage Volume Saved**: `bytes_saved` aggregated into Total GB saved and Average MB saved per item.
- **Swipe & Triage Depth**: Total swipes, average swipes per active user, and review confirmations.

### 3. Retention & Churn Dynamics
- **Cohort Day-N Retention**: True D1, D3, D7, D14, and D30 return rates based on active user engagement.
- **Activity Depth Spectrum**: Breakdown of user lifespan (1 day only, 2 days, 3-5 days, 6-10 days, 11+ days).
- For utility and cleaner apps, an 80%+ 1-day concentration is standard; retention is driven by re-engagement triggers (e.g. notifications when camera roll accumulates new media) rather than natural daily habit.

### 4. Paywall & Monetization Entry Points
Breakdown of paywall performance by trigger context (`entry` parameter):
- `onboarding`: First-session paywall during onboarding.
- `hard`: Paywall triggered by hitting a free-tier usage limit.
- `settings`: Intent-driven paywall opened via user navigation in settings.
- `soft`: Dismissible optional paywalls.
Calculates unique paywall viewers, purchase attempts, completed buyers, and true CVR by entry point.

## Configuration & Safety

In `$STORE/config.md`, ensure the following are declared:
```markdown
**Firebase Project ID**: <gcp-project-id>
**GA4 Property ID**: <numeric-property-id>
```

When executing BigQuery queries via CLI or scripts, mandatory attribution must always be applied:
- Environment variable: `CLOUDSDK_METRICS_ENVIRONMENT="... datacloud.antigravity"`
- CLI label flag: `--label datacloud:antigravity`
