# Google Analytics 4 / Firebase In-App Product Analytics

In-app telemetry connects top-of-funnel App Store acquisition (impressions and downloads) with downstream product activation, engagement, and monetization. An ASO iteration that only looks at downloads cannot tell whether acquired users ever opened the app, engaged with core mechanics, encountered the paywall, or dropped off.

---

## 1. Environment & Setup

The project includes a ready-to-run extraction script at `marketing/scripts/pull_ga.py`.

### Requirements & Credentials
* **Python Environment**: Run via the project's virtual environment:
  ```bash
  .venv/bin/python marketing/scripts/pull_ga.py [options]
  ```
  *(Package `google-analytics-data` is pre-installed in `.venv`)*.
* **Credentials**: Service account key JSON is located at:
  ```
  ~/.config/mediacleaner-analytics-key.json
  ```
  *(Automatically picked up by default)*.
* **GA4 Property ID**: `552518102` *(pre-configured as default)*.

---

## 2. Extraction Commands

Run during the weekly audit or when diagnosing hypothesis performance:

```bash
# Standard weekly pull (last 7 days, release traffic only)
.venv/bin/python marketing/scripts/pull_ga.py --days 7

# Two-week / cohort view (last 14 days)
.venv/bin/python marketing/scripts/pull_ga.py --days 14

# Real-time traffic check (last 30 minutes, useful after a release or marketing push)
.venv/bin/python marketing/scripts/pull_ga.py --realtime

# Include local debug / simulator traffic (appVersion == '0')
.venv/bin/python marketing/scripts/pull_ga.py --days 7 --include-debug
```

---

## 3. In-App Metrics & Funnel Mapping

| Step | Metric / Event | Source | Meaning & Denominator |
|:---|:---|:---:|:---|
| **Acquisition** | First-time Downloads | ASC Analytics | Users who downloaded the app from the App Store. |
| **First Open** | `first_open` / `newUsers` | GA4 / Firebase | Devices opening the app for the first time. **Install-to-Open Rate** = `first_open` / `First-time Downloads`. |
| **Permission Gate** | `photo_access_gate_shown`<br>`photo_access_answered` | GA4 (v1.1.4+) | User encounters the system photo permission dialog and answers (granted / limited / denied). Critical onboarding bottleneck. |
| **Activation** | `session_start`<br>`user_engagement` | GA4 / Firebase | User launches a session. **Session Frequency** = `sessions` / `activeUsers`. **Engagement** = `userEngagementDuration` / `activeUsers`. |
| **Core Engagement** | `media_swiped` | GA4 / Firebase | User reviews photos/videos (keep, delete, compress). **Swipes/User** = `media_swiped` / users. |
| **Action / Value** | `cleanup_completed` | GA4 / Firebase | User successfully executes batch deletion or compression. |
| **Monetization Gate** | `paywall_shown` | GA4 / Firebase | User encounters the paywall (e.g. hitting the free monthly limit or tapping Pro features). |
| **Conversion** | `trial_starts`<br>`in_app_purchase` | ASC / GA4 | Subscription trial started or purchased. |
| **App Store Feedback** | `rating_prompt_requested` | GA4 / Firebase | System review prompt requested (governed by 3-per-year ceiling). |

---

## 4. How to Use GA4 Data in Weekly Audits & Recommendations

### Rule 1: Reconcile Storefront Acquisition with Real App Openings
* Compare ASC downloads by country against GA4 `activeUsers` and `first_open` by country.
* If a country shows downloads in ASC (e.g. 2 downloads in Japan) but 0 `first_open` events, users downloaded but never launched the app.
* If `first_open` is high but `photo_access_answered` is low or denied, onboarding friction is losing users before they see the library.

### Rule 2: Distinguish Organic Users from Internal Test Confounds
* As documented in `marketing/decisions.md` (2026-09-10), internal testers (e.g. Ruslan and family) can heavily skew activation and trial numbers in Ukraine (`ua`).
* Always verify whether `paywall_shown` or `trial_starts` come from test devices or genuine organic storefronts before claiming monetization traction.

### Rule 3: Diagnose the Monetization Bottleneck
* **Scenario A: High downloads, low paywall exposure**
  * Users are downloading and swiping, but `paywall_shown` count is near zero.
  * **Diagnosis**: Users never exhaust the free monthly quota (the paywall trigger is too permissive or users drop off before reaching it).
  * **Recommendation**: Introduce earlier value hooks, contextual Pro feature indicators, or refine the free quota model.
* **Scenario B: Paywall shown, zero conversion**
  * Users reach `paywall_shown`, but zero trials start.
  * **Diagnosis**: Paywall creative, pricing, or value proposition is unconvincing in that market.
  * **Recommendation**: Test paywall copy, local PPP pricing (`asc-ppp-pricing`), or alternative billing periods.
* **Scenario C: High engagement, low downloads**
  * Existing users have high average engagement (>10 minutes/user, multiple sessions), but new user acquisition is low.
  * **Diagnosis**: Product value and retention are strong; top-of-funnel ASO reach and keywords are the growth constraint.
  * **Recommendation**: Expand keyword baskets, iterate screenshots, or explore Apple Search Ads / external channels.

---

## 5. Integrating with the Weekly Routine

On every weekly audit or status review:
1. Run `marketing/scripts/pull_funnel.py` to get the latest App Store Connect analytics.
2. Run `.venv/bin/python marketing/scripts/pull_ga.py --days 7` (or `--days 14`) to get in-app activation metrics.
3. Cross-reference country breakdown: compare ASC download countries with GA4 active user countries.
4. Record both acquisition and activation figures in `marketing/STATE.md` and report to the user.
