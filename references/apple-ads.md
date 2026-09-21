# Apple Ads — Strategy, Auction Dynamics, Economics & Operational Playbook

Historical app/account figures below are examples, not current configuration. Resolve identity, price, proceeds, trial duration, attribution window, and account access from the current app. All calculator outputs are scenarios; they do not justify scaling without mature cohort economics and a bounded loss budget. Paid installs have no guaranteed permanent organic-rank effect.

---

## 1. Quick Diagnostics: Why Are Impressions / Spend at Zero?

When a newly launched campaign or ad group shows **$0.00 spend and 0 impressions**, evaluate this checklist in order:

| Cause | Mechanism | Verification & Fix |
|---|---|---|
| **1. Broad Negative Keywords Trap** | Setting a category word as a **BROAD** negative blocks **100% of queries** containing that word (e.g., negative `cleaner` blocks `storage cleaner`, `photo cleaner`). | Run `asc ads negative-keywords find`. Delete category root broad negatives immediately. Only use **EXACT** negatives (`[query]`) for category terms. |
| **2. Cold-Start Auction Reserve Price** | Apple uses a second-price auction where $\text{Ad Rank} = \text{Bid} \times \text{Relevance} \times \text{Historical TTR}$. A new app has $0$ historical TTR. Bids under $0.30–$0.50 fail to clear Apple's reserve price against established incumbents. | Apply the **"Bid High to Learn"** rule: Raise default CPT bid ceiling to **$0.75–$1.25** while keeping a strict daily budget ($5.00/day). The second-price auction charges only the market clearing price ($Bid_{2nd} + \$0.01$). Step bids down after TTR is proven. |
| **3. Search Match Disabled** | When Search Match is OFF and exact keywords are narrow, only exact query matches can trigger impressions. | In ad group settings, set `automatedKeywordsOptIn: true`. In early discovery, Search Match is the primary discovery engine. |
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
(few, weak competitors) for opposite underlying reasons, and neither `rank_audit.py` nor any Apple
API used in this skill currently distinguishes them (see `references/provenance.md` — no working
Apple endpoint returns per-keyword, per-country search volume as of 2026-09; `KeywordSuggestionV6`
rejects a term/country filter, the legacy v5 popularity endpoint 404s).

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
    {"field": "campaignId", "operator": "EQUALS", "value": ["DISCOVERY_CAMPAIGN_ID"]}
  ]
}
```

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
