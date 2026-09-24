# Google Analytics 4 / Firebase product analytics

Use this reference only when the app has configured GA4/Firebase access and the requested question needs
in-app behavior. Treat GA4 as an observation source, not as proof of attribution or causality.

## Identity, credentials and collection

- `STORE/config.md` must name the numeric `**GA4 Property ID**` for this app. A one-off query may pass
  `--property-id <ID>`. Property selection never comes from environment variables, `STATE.md`, or an
  App ID mapping. `copilot cycle` uses only the configured property and marks the stage unavailable if
  it is missing.
- Resolve Firebase identity with the Firebase CLI and an explicit project ID. In SDK-only app repos,
  do not run `firebase init` just to select a project: there may be no `firebase.json`, and `firebase use`
  then refuses to run. `--project` works for read commands without initializing Hosting/Firestore/etc.

```bash
firebase projects:list --json
firebase apps:list --project "$FIREBASE_PROJECT_ID" --json
firebase apps:sdkconfig IOS "$FIREBASE_APP_ID" --project "$FIREBASE_PROJECT_ID" --json
```

`apps:sdkconfig` returns SDK configuration that can include an API key; do not paste its raw JSON into
reports or logs. Read only the project ID, app ID, bundle ID and analytics-enabled flag. Firebase CLI
has no historical GA4 event-report command. Resolve the numeric property through the Firebase Management
API `projects.getAnalyticsDetails`, and accept it only when the returned iOS stream maps back to the
selected Firebase App ID. Save that verified number in this app's `STORE/config.md` as `**GA4 Property
ID**`.

```bash
TOKEN="$(gcloud auth print-access-token)"
curl --fail --silent --show-error \
  -H "Authorization: Bearer $TOKEN" \
  -H "x-goog-user-project: $FIREBASE_PROJECT_ID" \
  "https://firebase.googleapis.com/v1beta1/projects/$FIREBASE_PROJECT_ID/analyticsDetails"
unset TOKEN
```

- GA4 report access is separate from Firebase CLI project access. The Data API requires an OAuth token
  with `https://www.googleapis.com/auth/analytics.readonly` (or full `analytics`) and access to the GA4
  property. If a token lacks the scope, stop on the 403 and record the missing scope; do not report an
  empty funnel or zero events. `gcloud auth application-default login --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/analytics.readonly`
  creates or refreshes persistent local ADC credentials and requires explicit authorization before use.
- Credentials resolve in this order: explicit `--credentials`, then the app-specific
  `**GA4 Credentials**` path in `STORE/config.md`, then `GOOGLE_APPLICATION_CREDENTIALS`. Do not search another app's config,
  credential files, or cached state. Keep credential values out of reports and model context.
- The `google-analytics-data` Python package must already be available in the selected environment.
  Do not install dependencies or create credentials during a status check.

```bash
GA="$SKILL_DIR/scripts/pull_ga.py"
python3 "$GA" --store "$STORE" --days 7
python3 "$GA" --store "$STORE" --days 14 --export-csv
python3 "$GA" --store "$STORE" --realtime
python3 "$GA" --store "$STORE" --days 7 --include-debug
```

`--include-debug` changes the population by including app version `0`; label that explicitly. The report
uses its declared date range and version filter. Preserve those with the capture time when recording
results. A successful command or a blank table does not establish that tracking is complete.

`pull_ga.py` returns separate event counts and per-event users; those are not a sequential user funnel.
Never divide one event's users by another event's users and label the result a step conversion unless a
user-level funnel report explicitly links the same cohort. GA4's `runFunnelReport` is currently v1alpha;
label its preview status if used. Retention requires a cohort report using `cohortActiveUsers` and
`cohortTotalUsers` over the same defined cohort; a 14-day event snapshot is not a retention measure.

## Event and metric interpretation

These are examples only. Confirm that this app emits each event, uses the same definition, and has
complete instrumentation before using it. Do not infer a missing event from another app's taxonomy.

| Funnel area | Example signals | Interpretation constraint |
|---|---|---|
| Acquisition | ASC impressions, product page views, downloads | Store metrics and GA users are different populations and may use different attribution windows. |
| First use | `first_open`, `newUsers`, `session_start` | Validate event meaning, consent, install attribution, reporting delay and market alignment. |
| Activation | App-specific core-action events | Define the action and eligible user denominator for this app. |
| Monetization | `paywall_shown`, trial, purchase events | Check event definitions, billing source, test traffic and attribution before interpreting conversion. |
| Feedback | App-specific rating prompt events | A prompt request is not a submitted App Store rating. |

For rates, state numerator, denominator, source, filters, time window and timezone. Compare the same
storefronts and compatible periods; GA4 country dimensions may not equal ASC storefronts. Small counts,
privacy thresholds, consent loss, event delays and instrumentation changes can make an apparent zero
inconclusive. ASC downloads with no observed `first_open` is a measurement gap unless coverage, window,
country and denominator have been reconciled; it does not prove that each downloader never opened the app.

## Diagnosis and recommendations

- Separate internal/test cohorts from customer traffic when the source supports it. If cohort identity is
  unavailable, say the mix is unknown rather than calling the observed users organic.
- Low observed paywall events can reflect exposure, eligibility, event instrumentation, traffic volume or
  filtering. Do not diagnose a quota or product issue from the count alone.
- Zero observed trials or purchases can reflect low exposure, delays, event loss, store billing records,
  or insufficient volume. Verify the purchase source and comparable window before recommending paywall,
  pricing or product changes.
- Use the evidence to form a testable hypothesis with a baseline, primary metric, guardrails, window and
  confounds. Do not turn generic benchmarks or unjoined totals into a causal diagnosis.

Record only fields the source provides: app/property identity, date range, `captured_at`, filters,
timezone, units, completeness and source export path. Keep `captured_at` distinct from the measured
period. If a field or history is unavailable, label it unavailable; do not invent a baseline or backdate
an observation.
