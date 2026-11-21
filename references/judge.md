# Judge and propose: reading the ledger

Judging is done by a person or a model reading what the store holds; no command writes a verdict. Start
from `STATE.md` or the page, then the ledger report with the day fixed.

```bash
python3 "$COPILOT" due --store "$STORE"                      # which rank reads the live hypotheses still need
python3 "$COPILOT" ledger --store "$STORE" report --as-of YYYY-MM-DD
```

`due` lists, per storefront and day, the reads a live rank hypothesis needs in the last three days of its
window; a day already gone by is marked `(missed)`, and a window judged on missed reads is thin evidence.

## What an answer holds, in order

For status and full-audit answers, use these sections in this order: **Store Funnel & ASC Analytics (impressions, views, downloads, CVR); RevenueCat & Cashflow (Gross, Net of Tax, Proceeds vs Apple Ads Spend); A · what is already live and what happened to it; B · what moved; C · what to do next.** Include only the requested scope and cite each decision-relevant fact with its provenance tag. **Do not draft a new hypothesis before the live funnel metrics, cashflow, and section A are on screen.** Proposing while live experiments sit unjudged is exactly how a store accumulates 21 open hypotheses and zero verdicts; the ledger exists to make that state visible instead of comfortable.

- **Store Funnel & ASC Analytics (Impressions & Conversion).** Mandatory for every full-cycle audit (`--full`, full cycle). Collects and reports the App Store Connect acquisition funnel:
  - Total Impressions and breakdown by source type (App Store Search, Browse, App Referrer, Web Referrer).
  - Product Page Views and First-time Downloads.
  - Conversion Rates: Page View CVR (`PV ÷ Impressions`), Download CVR (`Downloads ÷ PV`, `Downloads ÷ Impressions`).
  - Breakdown by Top Storefronts / Territories (US, UA, DE, NO, PL, etc.).
  - Week-over-Week Impression Trajectory: recent weekly trends to assess whether organic search volume is climbing or declining.
- **RevenueCat & Cashflow (Monetization & Ad ROAS).** Mandatory whenever `**RevenueCat Project ID**` is configured in `config.md`. Always report all 3 revenue tiers side-by-side against Apple Search Ads spend (`scripts/pull_revenuecat.py` / `ios-aso-copilot rc`):
  - **Gross Revenue (`revenue`)**: Customer store price before taxes and commission (what RevenueCat displays by default).
  - **Net of Taxes (`revenue_net_of_taxes`)**: After storefront VAT/sales tax (e.g., 20% VAT in Ukraine).
  - **Proceeds (`proceeds` / "чистими")**: Actual developer take-home after Apple's 15%/30% commission.
  - **Cashflow & ROAS**: Report `Net Cashflow = Proceeds − Ad Spend` and `Net ROAS = Proceeds ÷ Ad Spend` (alongside Gross Cashflow/ROAS) for active ad flights, rolling 14d/28d windows, and per-country breakdown, plus active trials and MRR. Never rely on static pricing notes or unverified GA4 `purchase_finished` counts (which include free-trial starts) when judging campaign profitability.
- **A · Hypothesis ledger.** Every hypothesis carries a state: `judged` / `due` / `open` /
  `not shipped`. `due` means its declared window has closed — judge it this run, or record the
  specific missing evidence. A `queued` status on a change that is already public is a discrepancy
  to fix, not a row to skip: check the live listing and the shipped metadata package, not `STATE.md`.
  `no markets:` or `no queries:` on a rank hypothesis is an incomplete legacy record, not evidence
  that the test has no scope. Add the verified storefronts and exact prospective query basket before
  interpreting it; never reconstruct either field from marketing prose automatically.
  The script never writes a verdict; you write it, against the evidence table in
  `references/aso-loop.md`. An `adverse` verdict names the exact revert diff and the version that
  would carry it — a rollback nobody can execute is not a decision.
- **B · Progress and regress per key.** Every tracked non-brand key, paired first-to-latest (brand-token queries are strictly excluded from all calculations, reports, and rankings). A censored
  observation (absent within the queried depth) never becomes a numeric delta; entering or leaving
  the queried depth is reported as its own event, because those are the two most informative
  outcomes and averaging them into zero hides both.
- **C · What to do next.** Ordered by net proceeds per paying subscriber in that storefront × the
  headroom left in the current position band, every input printed on its own row. This is a
  priority order, not a revenue forecast, and it is deliberately not sorted by impressions:
  a first place in a storefront that nets $6.37 a subscriber is worth less than a fifth place in
  one that nets $29.88. Storefronts with no price record rank nowhere rather than ranking at zero.
  Where `radar pull` has run, each row also shows Apple's search popularity for the key (`head N`; `below N` = not listed,
  so under the storefront's cut: unknown, not zero; `no data`). It informs the order and is not part of the score.

## The day the ledger is read for

Ledger `due`/`open` labels use the current local date unless you pass `--as-of YYYY-MM-DD` to `report`
or `draft`; use that flag to reproduce a prior evaluation. It does not change an observation's date,
and is rejected for `ingest`/`refresh`. Record the date data was actually observed; never backdate a
snapshot to make it fit a hypothesis window.

The ledger's inputs are `$STORE/metrics/ranks.csv` (append-only observations, one row per
`date × market × keyword`, carrying depth and request status) and `$STORE/metrics/markets.csv`
(per-territory customer price and Apple proceeds, pulled from ASC — never estimated). Refresh the
first with `python3 "$COPILOT" ledger --store "$STORE" refresh --bundle "$BUNDLE_ID"`, using the app's
exact bundle ID from its project configuration. This re-queries the basket `ranks.csv`
already holds and ingests it **one storefront at a time**, dating each row by its own `observed_at`
(a crash or a hung storefront does not cost the ones already finished). It exits **3** when any storefront
failed or any key got no response: what finished is already in `ranks.csv`, the basket is not complete.
Add `--failed-only` to retry keys whose latest request status
is `error`, after correcting terminal auth or configuration problems; retry one storefront with `--markets us`. Apple
currently documents an approximate 20 calls per minute, subject to change ([Search API](https://performance-partners.apple.com/search-api)).
The ledger's 3s minimum is a local guard based on this account's recorded failures, not a guarantee
that Apple's service will accept every request. Do not parallelize or shorten it to save time; at 1s
more than half the queries failed in the recorded run. Use `--failed-only` for the supported retry and
respect a server-provided retry delay when available. Refresh `markets.csv` when prices change.

## Closing a window

5. Review hypotheses whose declared windows have closed. Use `references/aso-loop.md`. Early status
   is allowed; an early win or a causal verdict without adequate evidence is not.
6. Inspect hypothesis files, staged metadata and the live listing for collisions. Include queued
   changes that may already have shipped. Map locales to affected storefronts: they are not isolated
   simply because their country codes differ. Preserve the original prediction and add dated amendments.

## Propose a hypothesis

```bash
python3 "$COPILOT" propose --store "$STORE" [--limit 5] [--basket 4] [--as-of YYYY-MM-DD]
```

`propose` is the deterministic half of generating a hypothesis. It names what is due first, then lists the
storefronts with no window in flight, best first by net proceeds x unclaimed gain x reach of their strongest key,
each with the keys to aim at (those Apple lists a demand score for come first: a target needs shown demand), a
note of any draft there that never shipped, and the `ledger draft` line. The other half is the argument: what
changes, and why that should move these keys. Write it from the store's own figures and save the file under
`hypotheses/`; a hypothesis about the funnel, the app or the paywall carries `primary_signal: funnel` and
names the figure in `data/` its prediction is read from.


Draft with `python3 "$COPILOT" ledger --store "$STORE" draft --market X --queries "a; b"`. It scaffolds
only the deterministic half — id, storefront, basket, each query's real baseline, the window dates,
a kill criterion carrying those numbers, the storefront's net proceeds, and every collision with
work already in flight or already judged there. **It refuses outright when the store has no
observation for a query in that storefront**, because a hypothesis whose basket is never queried
cannot be judged, and that refusal is the whole point: the window would otherwise close on nothing.
`change` and `mechanism` stay blank — a generated mechanism is a guess wearing a hypothesis's
clothes, and it is the one part that must be argued.

## Evidence rules that affect decisions

- RespectASO `popularity` can mix Apple data and an internal fallback. Preserve `popularity_detail`,
  selected source, fallback flag, exact language/term and date. Scores do not transfer across translations.
- iTunes API order is discovery evidence. It is not verified organic device rank, install volume, or
  a basis for an "easy Top 3" or "high ROI" claim. The bundled rank script no longer fabricates these scores.
- Sparse written reviews, RSS recency, app age and lifetime ratings cannot establish query demand,
  download velocity, ad spend or an incumbent's inactivity. No formula promises a rank from N reviews.
- **NEVER include brand queries or own-metadata phrases in calculations, and NEVER use brand/own-title rank as evidence of market demand, competitive advantage, launch opportunity, or ranking success.**
  **A brand-token query is never tracked at all**: `ledger.py refresh` does not ask Apple for it, `ledger.py ingest` skips it, and the keyword registry refuses it. `ledger.py drop-brand --store` removes brand rows a store already holds (git keeps the old file).
  **Brand-token and own-metadata queries are strictly excluded from all ASO calculations, ranking metrics, movement reports (Section B), priority scoring (Section C), hypothesis drafting, and top-position band counts (Top 1 / Top 3 / Top 10 / Top 20 / Top 200).**
  - **Brand tokens:** App brand name in any language (e.g. `myapp`, `brandname`), developer names, and trademarked terms.
  - **Own-metadata strings:** Any query that reproduces the app's own localized Title/Name (e.g. `MyApp: <Title>`, `<Title>`), full localized Subtitle, or multi-word fragments thereof (e.g. a localized subtitle copied verbatim, or two of its words in order). Ranking #1 or Top 3 for an exact phrase pulled from the app's own title or subtitle is a trivial metadata indexing artifact, NOT organic search traffic or user demand. Any such query must be tagged `[EXCLUDE: OWN_METADATA_STRING]`.
  - Counting `#1` on the app's own title/subtitle or claiming "we are Top 3 in 20 countries" based on own-metadata phrases is a vanity metric and false signal. Only genuine generic search queries (generic category terms, color noises, symptom queries) count.
- **Form Top Target Query Baskets via Search Popularity & Reachability (Not Guessed Phrases):**
  Target queries per storefront must NOT be invented arbitrary phrases. They must be constructed and validated through proven search demand:
  1. **Demand Validation:** Every target query must have verified search volume via **Apple Autocomplete (`MZSearchHints`)** or **Apple Ads Search Popularity (score 20–60)**. If Apple does not suggest the term in autocomplete or its search popularity is negligible (<15), real users do not type it — reject it.
  2. **Tri-Tier Target Portfolio per Focus Market (20 queries total):**
     - **Tier 1 — High-Intent Reachable Long-Tail (10 keys, Popularity 20–45):** Specific color noises, sleep fans, rain variations (e.g. `brown noise for sleep`, `rain sounds for focus`). Competitor review counts are moderate, which makes a Top 1–5 rank realistic.
     - **Tier 2 — Symptom & Persona Niches (5 keys, Popularity 25–50):** Acute user problems with high intent-to-install (e.g. a symptom or a user group, such as `<symptom term>` or `<persona term>`).
     - **Tier 3 — Broad Category Head Terms (5 keys, Popularity 50–80):** High-volume category terms (e.g. `white noise`, or a broad category name in each market's language) to monitor general visibility, but never as the sole criterion for a hypothesis win.
- Apple Ads query reports describe paid traffic; ASC Search can include ads. Organic installs per
  exact keyword are not directly observed in ASC. Browse is context, not a randomized control.
- Product claims must match shipped behavior. Reject keywords implying unsupported features. Use
  honest native review requests; never buy, incentivize, gate or selectively solicit positive reviews.
- A 21-day window is a scheduling default. An inconclusive result can remain inconclusive after it.
  Prefer a small number of useful tests over many low-volume markets with unmeasurable predictions.
