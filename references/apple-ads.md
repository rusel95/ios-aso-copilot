# Apple Ads — Strategy, Auction Dynamics, Economics & Operational Playbook

Historical app/account figures below are examples, not current configuration. Resolve identity, price, proceeds, trial duration, attribution window, and account access from the current app. All calculator outputs are scenarios; they do not justify scaling without mature cohort economics and a bounded loss budget. Paid installs have no guaranteed permanent organic-rank effect.

---

## 1. Quick Diagnostics: Why Are Impressions / Spend at Zero?

When a newly launched campaign or ad group shows **$0.00 spend and 0 impressions**, evaluate this checklist in order:

| Cause | Mechanism | Verification & Fix |
|---|---|---|
| **1. Broad Negative Keywords Trap** | Setting a category word as a **BROAD** negative blocks **100% of queries** containing that word (e.g., negative `cleaner` blocks `storage cleaner`, `photo cleaner`). | Run `asc ads negative-keywords find`. Delete category root broad negatives immediately. Only use **EXACT** negatives (`[query]`) for category terms. |
| **2. Cold-Start Auction Reserve Price** | Folk model — Apple does not publish its ranking formula: a second-price auction where $\text{Ad Rank} = \text{Bid} \times \text{Relevance} \times \text{Historical TTR}$, so a new app with $0$ TTR may lose contested head terms at bids under $0.30–$0.50. **Untested as a rule**: Compresso never ran an enabled bid under $0.45 (2026-09), so zero delivery at a low bid was never observed either. | For contested head terms, a higher ceiling (**$0.75–$1.25**) under a strict daily budget is one option; step down once TTR exists. For the long tail, where there may be no other bidder, a cap at what an install is worth is the other (§3c). Decide from the account's own delivery, not from this row. |
| **3. Search Match Disabled** | When Search Match is OFF and exact keywords are narrow, only exact query matches can trigger impressions. | Search Match finds new terms and also buys other apps' names: in Compresso's 2026-09 flights it served on `4ka` (a Slovak telecom), picme and immich. Use it only in a bounded, negated discovery batch (§3b); keep it OFF when harvesting EXACT keywords. |
| **4. Reporting Lag (3–6 Hours)** | Apple Ads analytics does **not** update in real time. Apple explicitly notes: *"Reporting is not in real time and may not reflect data received in the last three hours."* | Wait at least 3–6 hours before assuming auctions are stagnant. Check the timezone (ORTZ vs UTC). |
| **5. Small Market Query Volume** | Niche phrases (e.g., `стиснути відео` in UA) may have only 10–30 searches/day nationwide. | Broaden keyword coverage to high-intent adjacent problems (e.g. `очистити пам'ять`, `звільнити місце`, `photo cleaner`). |

---

## 1b. A Weak Competitor Field Is Not the Same Claim as Real Demand

An organic keyword can sit at a strong position (top-10, even top-5) with `total_results` in the
single or low double digits and every visible competitor holding zero or near-zero ratings. This
reads as "an unclaimed, easy market" — and it might be. It might just as easily be a market nobody
searches, where the low competitor count is an effect of the same cause as our own uncontested rank:
there is nothing there to compete for. iTunes Search API order and `total_results` measure **who
else is trying**, never **how many people are looking**. The two produce an identical-looking result
(few, weak competitors) for opposite underlying reasons, and `rank_audit.py` cannot distinguish them.
Apple's own popularity data covers only part of the gap (§3c): `insights search-term-popularity`
lists each genre's head terms, so a niche term is usually absent — censored, not zero — and
`insights impression-share` only covers terms the app's ads already showed on. (`KeywordSuggestionV6`
rejects a term/country filter; the legacy v5 popularity endpoint 404s.)

**The MediaCleaner precedent this generalizes from** (`docs/closed-questions.md`, "Should Compresso
ship a macOS port?", researched 2026-08-01): a genuinely unfilled competitive gap existed — no macOS
tool compressed the Photos library in place — but the analysis did not stop at "no competitors,
therefore opportunity." It asked *why* the gap might be empty of demand rather than just of
competitors: a free first-party alternative already solved most of the underlying anxiety (Optimise
Mac Storage), the forcing event was weakening (bigger default storage), and the target platform's
users skewed toward the opposite of the product's core promise (preservation-minded, not
delete-averse). None of those are competitor-count signals; all of them bear on whether the job the
product solves is one people in that segment actually have. The port was shelved not because a
competitor analysis said no, but because independent demand-adjacent signals did, while the
competitive-gap finding stayed true and recorded.

**The independent signals worth checking before reading a thin competitor field as opportunity**,
none of which come from the rank/competitor pull itself:

1. **A free or already-bundled alternative solving the same anxiety.** If the OS, a dominant free
   app, or the user's existing habit already resolves the pain point at zero cost, a thin paid/organic
   field may reflect that solved problem, not an open one.
2. **A weakening or absent forcing event.** Does something concrete push this segment toward the
   product's job right now (storage pressure, a platform change, a price change), or is the need
   chronic-background rather than acute?
3. **Segment fit with the product's actual promise**, not just the platform/language. A market can
   have the right language and country code and still skew toward the opposite psychological
   disposition the product needs (e.g. preservation-minded users being sold a "delete less, compress
   instead" pitch — see the macOS precedent — versus a segment that is actively anxious about running
   out of space).
4. **Direct behavioral evidence from a bounded paid test** (§6 below) — the one signal this skill can
   actually produce today, because it observes real people issuing real queries rather than inferring
   intent from an absence of competitors.

**Do not** promote a thin competitor field into an "easy win" or "high ROI" claim on its own — that
repeats exactly the fabricated-confidence failure `provenance.md` and the SKILL.md evidence rules
exist to block. Frame it as **unresolved**: a real competitive opening whose demand is currently
`absent:no popularity source available` until a demand-adjacent signal (above) or a bounded ASA test
narrows that gap.

## 2. Authentication & Account State

Apple Ads credentials are **independent** from App Store Connect. `asc` maintains two separate credential stores:

```bash
asc auth status        # App Store Connect (metadata, versions, reviews, analytics)
asc ads auth status    # Apple Ads (campaigns, keywords, bids, reports)
```

Verify the active profile and account:
```bash
asc ads auth discover --output json
asc ads acls list --output json
```

Platform API v1 leaf commands require `--ads-profile` and `--ad-account` (or `ASC_ADS_AD_ACCOUNT_ID`).

---

## 3. Auction Mechanics & The Cold-Start "Bid High to Learn" Rule

> **Status: an industry folk model, not verified here.** Apple publishes neither the ranking formula
> nor a reserve price. In Compresso's 2026-09 flights no enabled bid was below $0.45, so the "zero
> impressions at $0.15–$0.25" claim below was never observed — neither was its opposite. The UA and PL
> taps cleared at an average of $0.54 and $0.55 (keyword report, whole flight), not the $0.08–$0.25 quoted below. Treat the playbook as
> one option for contested head terms; §3c is the other for the long tail.

### The Vickrey Second-Price Auction
In Apple Search Ads:
- Your **CPT Bid** is the maximum you are willing to pay per tap.
- You do **NOT** pay your maximum bid. You pay **$0.01 more than the second-highest bidder's Ad Rank equivalent**.
- The winning bidder is decided by:
  $$\text{Ad Rank} = \text{CPT Bid} \times \text{Relevance Score} \times \text{Historical TTR}$$

### Cold-Start Penalty
For a brand new app (0 reviews, no historical tap-through rate):
- $\text{Historical TTR}$ is assumed to be baseline or zero.
- If incumbents bid $0.80 with a proven 8% TTR, their Ad Rank is significantly higher.
- If you bid $0.15–$0.25, your Ad Rank fails to meet the minimum clearing threshold (Reserve Price) and you receive **zero impressions**.

### The Cold-Start Playbook
1. **Cap Risk with Daily Budget**: Set campaign daily budget strictly to **$5.00/day** (or your bounded loss limit). You can never lose more than this daily cap.
2. **Set High CPT Bid Ceiling ($0.75 – $1.25)**:
   - This unlocks auction liquidity, clears the reserve price, and wins initial impressions.
   - The second-price auction prevents paying $1.00 unless an incumbent is bidding $0.99. In smaller markets (UA, PL), actual clearing CPT often settles at $0.08–$0.25.
3. **Step Down Bids**: Once 50–100 impressions are logged and initial TTR is established (>5%), gradually lower keyword bids by 10–15% every 48 hours to find the optimal volume/cost equilibrium.

---

## 3b. Discovery Batch Size — Never Expand a Keyword List All at Once

**The failure mode**: on 2026-09-19, a Compresso UA campaign went from 12 to 47 active keywords and
a PL campaign from 18 to 46 in a single batch — 29 and 28 new BROAD terms added at once, on a
$5.00/day budget each. A `reports/apps/search-terms` pull 24–48 hours later showed every added term
carrying 0–2 impressions — no usable signal in the campaign's 7-day window — while the one keyword
that already had traction (`video compressor`, EXACT) still carried the majority of all impressions.
Worse, the PL BROAD batch auto-discovered the query **"immich"** (an unrelated open-source
self-hosted photo-backup app) with real impressions before anyone caught it — a bleeding query per
§6 Step B.2, sitting live because no one had reviewed search terms since the batch shipped.

**Root cause**: a fixed daily budget divided across N keywords gives each keyword roughly
`budget / N` of auction liquidity per day. At N=5–10 that's enough to clear a cold-start reserve
price occasionally. At N=40+, most keywords never see enough auction participation in a 4–7 day
window to produce a judgeable sample — this is budget atomization, not discovery breadth. Broad
match makes it worse: each additional broad seed doesn't just split the budget, it also grows the
query-matching surface Apple's algorithm can wander into unsupervised.

**The rule**: a single Discovery-campaign expansion is capped at **5–10 new BROAD seeds** per
campaign per batch, never the full harvested basket at once. After any expansion:
1. Pull `reports/apps/search-terms` within 48 hours of the batch going live — not at the end of the
   test window — specifically to catch off-topic auto-discovery (like "immich") while spend is still
   near $0, per the Quick Diagnostics table in §1.
2. Do not add a second batch of seeds until the first batch has either produced a promotable winner
   (§6 Step B.1) or been judged a dead end and paused. Seeds compete for the same fixed daily budget;
   stacking unjudged batches is the same mistake as stacking unjudged ASO hypotheses.
3. A keyword added to a live campaign with **zero measured impressions** after 3–4 days in a
   `$5/day` test is not "still gathering data" — it never cleared the auction. Pause it; it is not
   occupying budget, but it is diluting the operator's ability to read the report at a glance.

**The connection to organic ASO discipline**: this is the same failure the hypothesis ledger exists
to prevent (see the opening of this SKILL.md — "do not draft a new hypothesis before section A is on
screen"). A keyword-list expansion is a hypothesis with a batch size; treat oversized batches as a
`due` ledger row that never got a verdict, not as free exploration.

**Scope**: this rule is about BROAD seeds on a shared budget. It does not forbid a long-tail EXACT
harvest (§3c): there, Search Match is off, so nothing wanders off-topic. The question is also a
different one. It is the blended cost per install across the whole set, plus which terms deliver at
all, not a per-keyword verdict.

## 3c. Measuring Demand: Popularity, Impression Share, and the Low-Volume Wall

Three Apple sources, each with a blind spot (verified 2026-09-28 on Compresso's account):

1. **Head popularity** — `asc ads insights search-term-popularity find`
   (`POST v1/insights/apps/search-term-popularity/query`): `searchPopularity1to100` per term ×
   storefront × week (`WEEKLY_SUN_SAT`, UTC; `pageSize` ≤ 5000, page with `offset`; filter
   `countryOrRegion` and optionally `searchTerm` `CONTAINS`). Only each genre's head: ~100–350 terms,
   lowest listed score ~40–68 by storefront; RU, LT and MD returned no rows. 7 of Compresso's 728
   tracked non-brand pairs appeared. An absent term is below the cut, not zero.
2. **Impression share** — `asc ads insights impression-share find`
   (`POST v1/insights/apps/impression-share/query`): share range, rank and popularity 1–5 per term the
   app's ads showed on (`DAILY` ≤ 30 days or `WEEKLY_SUN_SAT` ≤ 4 weeks). Total volume ≈ own
   impressions ÷ share. The CLI's starter payload is wrong: `promotedObjectId` needs
   `{"field":"promotedObjectId","operator":"IN","value":["<adamId>"]}` — `EQUALS` returns 400, and the
   CLI rejects a `values` key.
3. **Search terms** — `reports apps search-terms` withholds every term under 10 impressions as low
   volume. In Compresso's September flights that was **96% of spend and 95% of taps**, and all of
   every EXACT keyword's traffic. For the long tail, the per-query lens is the **keyword report**
   (`reports apps keywords`, ORTZ). Its rows carry only a keyword id; join them to
   `targeting-keywords find` (filter `campaignId`) for text, match type and bid.

**Long-tail EXACT at a break-even cap** (the design this enables, from a founder running it across 29
localizations): thousands of EXACT keywords per language — intent × inflections × modifiers ×
transliteration and wrong-layout spellings, no competitor brands. Search Match stays OFF. The max CPT
is set to what an install is worth in that storefront (net proceeds × share of installs that pay ×
tap→install). Apple allows 5,000 keywords per ad group (`targeting-keywords create-bulk`). Run
everything at the cap, read which terms deliver, move the good ones into title/subtitle, and keep only
the profitable ones paid. Exact match still serves close variants (plurals, misspellings), so some
generated spellings are redundant. That is harmless. Compresso's own data: EXACT 20 installs from 25
taps ($0.57 each) against BROAD 37 from 96 ($1.37) — observational, and EXACT was mostly one head term.

### The radar: `scripts/radar.py`

One weekly, read-only pull turns the three sources above into history in the store
(`copilot.py radar …`; also step 5 of `copilot.py cycle`, which skips it quietly when config.md has no Apple Ads lines):

| Command | Reads | Writes |
|---|---|---|
| `radar pull` | popularity for every market in `metrics/ranks.csv`, filtered server-side to the app's genres; four weeks of impression share for the app's own ads | `metrics/popularity.csv` (tracked terms inside the head, plus head terms that contain a configured topic word), `metrics/popularity_cut.csv` (per market × genre: terms listed, lowest score listed), `metrics/impression_share.csv` |
| `radar report` | those files, no network | the cut per market, tracked terms inside the head beside our search-API position, topical head terms we do not track, our impression share |
| `radar keywords [--campaign ID]` | keyword report + `targeting-keywords find` + search-terms report | keyword text, match type, bid, spend, installs, and how much spend sits under withheld terms |
| `ledger.py report` | the radar files | section C gains a **Demand** column: `head N`, `below N`, `no data`, `—` |

config.md, all optional; without profile and account the radar refuses to guess an account:
`**Apple Ads profile**:` (an `asc ads auth` profile name), `**Apple Ads account**:` (numeric ad account id),
`**Apple Ads genres**:` (the app's categories in Apple's spelling; Compresso is UTILITIES + PHOTO_AND_VIDEO in ASC and
`PRODUCTIVITY_UTILITIES` + `PHOTO_VIDEO` here; the others are `GAMES`, `BUSINESS`, `EDUCATION`, `ENTERTAINMENT`, `FINANCE`,
`FOOD_DRINK`, `HEALTH_FITNESS`, `LIFESTYLE`, `NEW_PUBLICATION`, `SHOPPING`, `SOCIAL_NETWORKING`, `SPORTS`, `TRAVEL`),
`**Apple Ads topic words**:` (substrings; head terms containing one are stored).

What it enforces: a tracked term that is not listed is **below the cut** (the lowest score Apple lists there), never zero;
a storefront where Apple lists nothing (RU, LT and MD in 2026-09) is `no data`, not "no demand"; a week Apple has not
published yet falls back one week and stores nothing for the empty one; a market already stored for a week is not pulled
twice. Pull weekly: Apple's weeks run Sunday to Saturday.

First real run (Compresso, week 2026-09-20): 7 of 728 tracked non-brand pairs inside the head — jp `動画圧縮` 55 (our
search-API position 160), cn `视频压缩` 48, us `video compressor` 48, four India `compressor` queries at 44–46. Head terms on the app's topic that
were not tracked: us `clean up iphone` 63, it `clean up iphone gratis` 58, au `clean up iphone free` 57, mx `clean up
gratis` 55. Popularity is a relative score, not a search count, and the cut differs by storefront (44 in GB, 56 in NO), so
`below 56` in Norway and `below 44` in Britain are not comparable statements about volume. A candidate is a reason to
observe the term (`rank_audit.py`, `ledger.py ingest`) and then draft a hypothesis, not a keyword to ship. Generic topic
words match brand names.

`radar report` reads offline; `radar pull` is the only network step. RespectASO's `get_top_search_terms` reaches the same
weekly data with a license; the radar needs only the app's own Ads account and keeps the history in the store.

### Ceiling for a per-tap bid

Apple Ads bills taps, so the ceiling is per tap:
`economics.py --net-per-payer <first-year net, metrics/markets.csv proceeds_usd> --pay-rate <payers per install>
--tap-to-install <installs per tap, from the Ads report> [--cpt <the bid>]`. At 0.5 % payers per install and 0.8 installs
per tap a $29.88-net storefront allows $0.12 a tap and a $6.68-net one $0.03. The pay rate stays a scenario until
RevenueCat has enough paying customers to measure it; print it next to the ceiling every time.

### Ads → ASO loop (from a founder call, 2026-09-28)

Run long-tail EXACT keywords at the ceiling → read `radar keywords` → the terms that deliver become candidates → check who
holds them in title and subtitle (`rank_audit.py`, competitor listings) → move a winner into organic metadata as a
hypothesis with a kill criterion → pause the paid keyword once organic holds it. Ads matching is looser than the keyword
field's: an EXACT keyword also serves close variants (plurals, misspellings, word order), which the keyword field does not,
so a finding from an ad report is never a reason to delete variants from a keyword field.

## 4. Negative Keyword Match Rules & Hazards

Apple Ads supports two negative keyword match types. Confusing them can silently destroy campaign traffic:

| Match Type | Behavior | Example Rule |
|---|---|---|
| **EXACT Negative** (`[word]`) | Blocks the ad **only** when the user searches the exact query, with no other words before or after. | **SAFE**: Use `[cleaner]` if you only want to avoid the isolated 1-word query "cleaner". |
| **BROAD Negative** (`word`) | Blocks the ad if the user search contains the word **in any order or combination**, including with other words. | **HAZARD**: Adding `cleaner` as broad negative blocks `phone cleaner`, `storage cleaner`, `photo cleaner`, and `video cleaner`. |

### Hard Negative Rules:
1. **NEVER** use Broad Match Negative for category terms, action verbs, or core user problems (`cleaner`, `compress`, `photo`, `video`, `storage`).
2. **Use Broad Negatives ONLY** for completely irrelevant industries or platforms (e.g. `android`, `windows`, `free movie`, `hack`, `torrent`).
3. **Use EXACT Negatives for Campaign Cross-Isolation**:
   - When a keyword lives in the Exact Category campaign, add it as an **Exact Negative** (`[query]`) in the Discovery campaign. This prevents Discovery from bidding against your own Category campaign.

---

## 5. Four-Campaign Architecture

The standard industry structure for sustainable ASA management (`doc:HANDBOOK.md` Part 2.2):

```
┌──────────────────────────────────────────────────────────┐
│                   APPLE SEARCH ADS                      │
├─────────────┬─────────────┬─────────────┬────────────────┤
│    Brand    │  Category   │ Competitor  │   Discovery    │
│ (Exact / NO)│ (Exact / NO)│ (Exact / NO)│(Broad+Match/YES│
└──────┬──────┴──────┬──────┴──────┬──────┴───────┬────────┘
       │             │             │              │
       └─────────────┴─────────────┴──────────────┘
              Cross-Negatives (Exact Match)
              protect Discovery from cannibalism
```

| Campaign | Match Type | Search Match | Role | Negative Wiring |
|---|---|---|---|---|
| **1. Brand** | Exact | OFF | Defend app name & close variations at lowest CPT. | None. |
| **2. Category** | Exact | OFF | High-intent problem terms (`стиснути відео`, `kompresor wideo`). | Brand terms as negative exact. |
| **3. Competitor** | Exact | OFF | Competitor brand names surfaced via iTunes / Astro. | Brand terms as negative exact. |
| **4. Discovery** | Broad | **ON** | Mine new unknown search terms and algorithm matches. | **All Exact terms from Brand, Category, Competitor added as EXACT negatives.** |

---

## 6. Search Term Harvesting Pipeline (ASA ↔ ASO Synergy)

The true power of Apple Search Ads is providing **unfiltered query and conversion data** to feed organic ASO.

### Step A: Pull Search Term Report
Run weekly via `asc ads reports apps search-terms`:
```bash
asc ads reports apps search-terms \
  --ads-profile "ProfileName" \
  --ad-account "ACCOUNT_ID" \
  --file report-query.json \
  --output json
```

Query shape (`report-query.json`):
```json
{
  "timeRange": {
    "start": "2026-09-10",
    "end": "2026-09-17",
    "timeZone": "ORTZ",
    "granularity": "DAILY"
  },
  "pagination": {"offset": 0, "pageSize": 50},
  "filters": [
    {"field": "campaignId", "operator": "EQUALS", "value": "DISCOVERY_CAMPAIGN_ID"}
  ]
}
```

Rows with `searchTermText: null` are terms under Apple's 10-impression line, not missing data. When
they dominate the spend, read the keyword report instead (§3c).

### Step B: The Promotion / Pruning Engine

1. **Winning Query ($\text{TTR} \ge 5\%$, $\text{CVR} \ge 20\%$, Installs $\ge 2$):**
   - **Promote to Exact**: Add as Exact match targeting keyword in Category campaign (`asc ads targeting-keywords create-bulk`).
   - **Isolate in Discovery**: Add as **Exact Match Negative** in Discovery campaign (`asc ads negative-keywords create-bulk`).
   - **Feed Organic ASO**: Add the term to the organic candidate basket. Consider placing it in the **Subtitle** or **Keyword Field** for the next App Store version release.

2. **Bleeding Query ($\ge 10$ Taps, 0 Installs):**
   - User intent does not align with the product/paywall.
   - Add immediately as **Exact Match Negative** in Discovery to stop budget leakage.

---

## 7. Native Apple Ads ML Suggestions API

Apple provides first-party algorithmic keyword suggestions and target CPA benchmarks based on the App Store metadata:

### Get Keyword Suggestions for an App
```bash
asc ads suggestions keywords find \
  --ads-profile "ProfileName" \
  --ad-account "ACCOUNT_ID" \
  --file - << 'EOF'
{
  "filters": [
    {"field": "promotedObjectId", "operator": "EQUALS", "value": ["YOUR_APP_ID"]},
    {"field": "promotedObjectType", "operator": "EQUALS", "value": ["APPSTORE_APP"]}
  ],
  "pagination": {"offset": 0, "pageSize": 30}
}
EOF
```

### Get Target CPA Recommendations
```bash
asc ads suggestions target-cpas find \
  --ads-profile "ProfileName" \
  --ad-account "ACCOUNT_ID" \
  --file - << 'EOF'
{
  "filters": [
    {"field": "promotedObjectId", "operator": "EQUALS", "value": ["YOUR_APP_ID"]},
    {"field": "promotedObjectType", "operator": "EQUALS", "value": ["APPSTORE_APP"]}
  ],
  "pagination": {"offset": 0, "pageSize": 10}
}
EOF
```

---

## 8. Economics & LTV / CAC Guardrails

Use `$SKILL_DIR/scripts/economics.py` to evaluate whether paid traffic can achieve profitability:

```bash
python3 $SKILL_DIR/scripts/economics.py \
  --price 49.99 \
  --commission 0.15 \
  --retention 0.221 \
  --trial-to-paid-cvr 0.38 \
  --cpi <observed_cpi>
```

### Core Equations:
- $\text{Tap-to-Install CVR} = \frac{\text{Installs}}{\text{Taps}}$
- $\text{Cost Per Install (CPI)} = \frac{\text{CPT}}{\text{CVR}}$
- $\text{Customer Acquisition Cost (CAC)} = \frac{\text{CPI}}{\text{Install-to-Paid CVR}}$
- **Scale Rule**: Only scale budget beyond discovery ($5/day) when $\text{LTV} \ge 2.5 \times \text{CAC}$ on a mature 30-day cohort.

---

## 9. ASA Hypotheses Format (`marketing/hypotheses/H0xx-*.md`)

When testing a paid acquisition hypothesis, maintain the same rigorous standard as organic ASO hypotheses:

```markdown
---
id: H0xx
markets: ua
queries: стиснути відео; зменшити розмір відео
status: live
phase_at_start: P2-cold
change: >
  Launched targeted 7-day Apple Search Ads campaign in Ukraine (ua) at $5.00/day.
  Exact match ($0.75 bid ceiling) and Search Match ON ($0.75 default).
mechanism: >
  1. Buying clean in-app conversion telemetry in GA4 (install -> permissions -> paywall -> trial).
  2. Injecting 72-hour download velocity into Ukrainian exact queries to move organic rank from #9 to Top 3.
prediction: >
  1. 100+ downloads delivered at CPT <= $0.25, CVR >= 35%.
  2. Organic rank for 'стиснути відео' advances into Top 5 by Day 7.
kill_criterion: >
  Average CPT exceeds $0.40 or Tap-to-Install CVR falls below 25% after 30 taps.
kill_criterion_written: 2026-09-18
went_live: 2026-09-18
window_days: 7
primary_signal: rank
verdict:
---
```
