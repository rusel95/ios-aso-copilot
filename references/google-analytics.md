# Google Analytics 4 / Firebase product analytics

Use this reference only when the app has configured GA4/Firebase access and the requested question needs
in-app behavior. Treat GA4 as an observation source, not as proof of attribution or causality.

## Identity, credentials and collection

- `STORE/config.md` must name the numeric `**GA4 Property ID**` for this app. A one-off query may pass
  `--property-id <ID>`. Property selection never comes from environment variables, `STATE.md`, or an
  App ID mapping. `copilot cycle` uses only the configured property and marks the stage unavailable if
  it is missing.
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
