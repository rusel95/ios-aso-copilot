# Apple Ads — Strategy, Auction Dynamics, Economics & Operational Playbook

Historical app/account figures below are examples, not current configuration. Resolve identity, price, proceeds, trial duration, attribution window, and account access from the current app. All calculator outputs are scenarios; they do not justify scaling without mature cohort economics and a bounded loss budget. Paid installs have no guaranteed permanent organic-rank effect.

---

## 1. Diagnose missing delivery before changing bids

A fresh campaign with an empty report has **unknown delivery from that response**, not an explicit
zero metric. Read eligibility/status/limiting reasons, account timezone, report range and pagination.
Keep the complete inventory joined by IDs to the campaign-scoped keyword report and search-term report.

| Check | Action |
|---|---|
| Relevant terms accidentally blocked | Inspect campaign- and group-level negatives. A broad negative blocks when **all its words** occur; do not remove a category negative without checking the user's exclusion intent. |
| New launch or changed bid | Allow report/setting lag. No published reserve-price number establishes that the bid is too low. |
| Search Match OFF | Exact still includes close variants. Keep OFF for a controlled Exact experiment; use a separate bounded discovery test when authorized. |
| Entire campaign has little delivery | Verify targeting, app availability, ad eligibility, language/product fit and budget before isolating a bid experiment. |
| Some keywords deliver, others do not | Distinguish weak phrases from natural rare seeds. Do not delete core seeds just because their row is missing or impressions are zero. |

Apple describes relevance and bids as auction factors, with ineligible irrelevant apps excluded:
[Search results](https://ads.apple.com/app-store/help/ad-placements/0082-search-results).
The keyword policy and stable-window rules are in §10. No minimum daily search count is inferred.

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

## 3. Bids and budgets: published mechanics and evidence boundaries

A max CPT bid is a per-tap ceiling; the actual price may be lower. Apple's dynamic pricing considers
relevance, bids, other bidders, user experience, a possible auction reserve and other factors. Apple
does not publish a universal $0.05–$0.10 floor, an exact ranking formula or a guaranteed
second-bid-plus-$0.01 payment rule. Do not use a folk equation to diagnose missing impressions.
[Set and adjust bids](https://ads.apple.com/app-store/help/bids-and-budget/0062-set-and-adjust-bids).

A daily budget is an **average**, and spend may exceed it on a particular day. Apple describes a
monthly limit of daily budget × 30.4 and a duration limit when an end date is set; mid-month budget
changes need their own reconciliation. Native end times and bounded budgets must be configured
before activating an experiment. A credit balance does not stop a PAYG account from billing after
credit is used. Verify the balance if available; preserve a user-provided balance as `user:`, not live.
[Manage budgets](https://ads.apple.com/app-store/help/bids-and-budget/0016-manage-budgets).

Shared budget orders require an invoiced account/line of credit; do not create one as a workaround for
PAYG spend controls. [Monthly invoicing](https://ads.apple.com/app-store/help/billing/0031-monthly-invoicing).

Compute per-tap economics with §3c. If a delivery test changes bids, change one market or intent group
under a loss limit, hold its dictionary stable, record the new phase, and check it before copying.
No arbitrary number of impressions or historical TTR authorizes a universal bid increase.

## 3b. Keep discovery batches interpretable

Use a small reviewed batch of broad seeds as an operational choice, not a claim that every keyword
gets `budget / N` spend. Keywords have no equal budget allocation. Adding many low-volume or weak
seeds makes interpretation harder; it does not mathematically starve each term of a fixed share.

Compresso's September 2026 historical broad expansion found off-topic terms, including `immich`;
that observation motivated smaller discovery batches, but it did not isolate a causal batch-size effect.
For a new test, choose the batch size from the current budget, intent coverage and review capacity.
A default proposal of 5–10 broad seeds is an operator heuristic, not an Apple limit.

After an authorized expansion, inspect disclosed search terms early (for example within 48 hours)
for relevance and spend. Withheld terms and empty reports stay unknown. Add appropriate negatives
for observed off-topic traffic. Review results before adding another batch. Do not infer auction
failure, remove a core seed or raise its bid solely because 3–5 days passed with no impressions.
The Exact rotation policy in §10 requires a stable observation window.

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
   every EXACT keyword's traffic. For the long tail, the **keyword report**
   (`reports apps keywords`, ORTZ) aggregates traffic matched to that bid keyword, including close variants.
   It does not disclose every actual query. Its rows carry a keyword id; join them to
   `targeting-keywords find` (filter `campaignId`) for text, match type and bid.

**Long-tail Exact under a bounded learning budget.** A founder's thousands-of-phrases method is an
experiment idea, not measured low-cost inventory. Build natural product-matched phrases using §10,
keep Search Match OFF, and choose the bid from an explicit economics scenario. Apple's 5,000-keyword
limit is a ceiling per ad group, not a required basket size. Exact includes spelling variations,
reordered words and translations, so count neither permutations nor keywords as independent searches.
[Match types](https://ads.apple.com/app-store/help/keywords/0059-understand-keyword-match-types),
[keyword limits and relevance](https://ads.apple.com/app-store/help/keywords/0014-add-and-manage-keywords).
Compresso's old Exact/Broad CPI contrast was observational, dominated by one Exact head term;
it does not establish the ROI of a newly generated long tail.

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

Apple Ads provides paid keyword metrics and some disclosed actual queries. Low-volume search terms may
be withheld; installs are attributed downloads, not proof of payer conversion or organic-rank causality.

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

Rows with `searchTermText: null` have an undisclosed query. Preserve their metrics as withheld traffic;
do not invent its text. The keyword report helps analyze matched traffic (§3c), but cannot recover the query.

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
  2. Testing delivery of relevant paid traffic under a fixed budget; organic rank tracked separately,
     without claiming that paid installs cause a rank lift.
prediction: >
  Define paid delivery, activation and spend thresholds from this app's current baseline.
  Organic rank is an observational secondary signal, with its source and confounds recorded.
kill_criterion: >
  Average CPT exceeds $0.40 or Tap-to-Install CVR falls below 25% after 30 taps.
kill_criterion_written: 2026-09-18
went_live: 2026-09-18
window_days: 7
primary_signal: paid_delivery
```

---

## 10. Automatic Exact creation, repair and future rotation

The output target is **accepted natural phrases**, not 5,000 rows. A set of action × object ×
modifier permutations, random set iteration followed by `[:5000]`, translated token fragments and
synthetic typos must not feed an upload. In the Compresso 2026-10-01 audit the historical IL/RO
programs reproduced this selection defect and dropped relevant tracked seeds; that is a generator
bug, not evidence of market demand or a reason to raise all bids.

### A. Collect a product contract and seeds automatically

Use the configured app's current metadata, the full tracked basket (`radar.read_basket`),
campaign-scoped keyword/search-term reports joined to the complete inventory, and Apple hints
(`harvest_keywords.py`). Keep `text`, language, storefront, source and evidence type:

- `seed`: our relevant metadata/tracked query; a tracked rank alone does not measure searches.
- `suggestion`: Apple hint or recommendation; names of apps are not measured generic demand.
- `keyword_delivery`: observed traffic matched to a bid keyword; close variants are included.
- `search_term`: an actually disclosed relevant paid query, with report range and metrics.
- `model`: a newly generated phrase with no measured demand.

Filter app titles, wrong platforms and unsupported outcomes with semantic review. Never promote
hints into popularity. A source spelling that is a typo or unsupported intent is reviewed before
being protected. Mark relevant core seeds `protected=true` **before expansion**. Protect them even
if capacity is low; split the group rather than silently discard seeds.

Use shipped capability docs/code and limitations. Manual photo review can help delete duplicates a
person notices; it does not promise an automatic duplicate finder. A storage complaint may be an
adjacent Photos use case; RAM/cache/system-data cleanup is a separate unsupported outcome unless
verified for this product. Lossless, exact byte-size and absolute quality promises need actual support.
Do not indiscriminately ban the words `similar`, `iCloud` or `quality`; judge the expected result.

### B. Have the agent generate and review whole phrases

No human needs to type thousands of keywords. The running language model does this work in batches
of roughly 100–200 candidates by language and intent.

#### The 4 High-Converting Intent Clusters (Empirical Oct 2026 Telemetry)
In international storefronts, single-word or broad generic phrases either fail or trigger expensive auctions.
High-converting, low-CPT ($0.15–$0.25) delivery concentrates around 4 specific intent structures:

1. **Explicit Tool / Utility Suffixes (`[Action] + [Local "App" Word]`)**:
   Non-English users heavily qualify intent with words meaning app/program/free tool:
   - Indonesian: `aplikasi kompres video` (proven winner: 16 taps at $0.16 CPT)
   - Polish: `aplikacja do kompresji wideo`, `program do zmniejszania rozmiaru wideo`, `darmowa aplikacja do kompresji wideo`
   - German: `app um videos zu verkleinern`, `programm zur videokomprimierung`
   - Spanish: `aplicacion para comprimir videos`, `reducir tamaño video app`
2. **Scenario & External Friction Constraints (Jobs-to-be-Done Triggers)**:
   Users search when blocked by third-party size limits:
   - Messaging limits: `kompresja wideo whatsapp`, `zmniejsz wideo do maila`, `video compress for discord`, `film za duzy na email`
3. **Acute Storage Exhaustion (Device Lockup Pain)**:
   Users confronting "Storage Almost Full" system warnings:
   - `brak miejsca na iphone`, `jak zwolnic miejsce w telefonie`, `pamiec iphone pelna`, `czyszczenie pamieci iphone`
4. **Heavy Asset & Format Targets**:
   Users targeting specific large media:
   - `kompresja wideo 4k`, `zmniejsz rozmiar mp4`, `zmniejsz duze pliki wideo`

#### Apple Ads Search Popularity & Long-Tail Arbitrage
- **Apple Ads Insights API** (`asc ads insights search-term-popularity find --ad-account <ID>`):
  Official popularity scores (1–100) are heavily head-skewed. Across genres, the top 1,000 terms in any country
  are dominated by institutional brands (`capcut`, `canva`, `cleanup` Pop 58 in PL) and broad categories (`photo editor` Pop 70).
  Institutional competitors bid $1.50–$3.00+ on these head terms.
- **The Long-Tail Reality**: Specific scenario terms (`kompresja wideo whatsapp`, `brak miejsca na iphone`)
  sit below Apple's head-tier index (popularity 10–35), but represent uncontested, high-intent traffic where
  Exact bids at $0.15–$0.25 clear taps with zero competitor pressure.

#### Storefront Localization Vacuum Audit (iTunes Search API)
Before finalizing a candidate basket for a country, probe the App Store search index:
```bash
curl -s "https://itunes.apple.com/search?term=<query>&country=<country>&entity=software&limit=10"
```
If a query in the native language (e.g. `kompresor wideo` in PL) returns only foreign English apps with low
rating counts (<50), it confirms a **Localization Vacuum**: native users search the query, but no competitor
has localized their listing. This represents the highest-converting opportunity for localized Exact match.

#### Expansion Prompt
Use the following prompt with the real seeds, product contract, and the 4 clusters above:

> Generate complete natural App Store search phrases in {language} for {intent}.
> Structure candidates across the 4 high-converting clusters:
> 1) [Action] + [Local App/Tool word] (aplikacja, program, app, darmowa)
> 2) Scenario/sharing constraints (WhatsApp, email limit, Discord)
> 3) Acute storage friction (storage almost full, brak miejsca, zwolnij pamiec)
> 4) Heavy asset formats (4K video, MP4, large files)
> Each phrase must express one understandable job this product can satisfy.
> Keep relevant seeds unchanged. Do not pad with typos, years, or competitor brands.
> Return text, language, intent, source, evidence, full Ukrainian translation, expected product path.
> New phrases have evidence=model; never invent demand, competition or a score.

Then review every phrase in a separate pass: native-language naturalness, expected result, one task,
product path, and a complete Ukrainian translation. Return `core`, `adjacent` or `reject` and an
explicit `review_reason`. Adjacent storage/organizing queries remain a separate evaluation bucket.
Record model/pass/date and whether a native human reviewed it; Python does not certify fluency.
Rejected examples and reasons stay in the file to prevent regeneration of the same defects.

### C. Validate and export deterministically

CSV fields are exactly documented by `scripts/ads_keywords.py`: `text,language,intent,source,evidence,
translation_uk,classification,product_path,review_reason,protected` (`protected`: true/false).

```bash
python3 "$SKILL_DIR/scripts/ads_keywords.py" \
  --input "$STORE/ads/batch/candidates.csv" --output "$STORE/ads/batch/reviewed" \
  --brand compresso --brand 'media cleaner'
python3 "$SKILL_DIR/scripts/ads_keywords.py" --self-check
```

Replace the example brands with this app's brand and the competitor tokens excluded by the user's
strategy. The script writes accepted/rejected CSV with reasons and a newline keyword basket. It
normalizes NFC/case/whitespace, deduplicates exact normalized texts, checks required review fields
and control/length limits, filters whole brand tokens (`compresso` must not drop `compressor`), and
selects stably: protected seeds → disclosed relevant terms → observed keywords → seeds → suggestions
→ model expansions. A protected invalid seed stops export; excess protected seeds stop cap slicing.
Word-order family labels are for review; never delete an order variant solely because the label matches.
The local 80-character ceiling is a conservative export check; verify the installed API contract too.

Diff against the full fresh inventory with concrete campaign/group/keyword IDs, current status and
metrics. Export create and pause lists and their reasons. Keep historical IDs and attributed traffic.
An accepted phrase with an existing identical active keyword does not need another active copy.

### D. Apply authorized repairs and read back

Inspect the exact installed `asc ads ... --help` and use existing credentials. When the user has
already authorized repairs, apply them; otherwise leave a concrete local plan for final approval.
Never turn the local generator into an unattended spending tool.

For a wholly defective basket, prepare a new PAUSED ad group, upload its reviewed Exact phrases,
set Search Match OFF, copy the intended scoped negatives, inspect every bulk item result and fully
read back. Only then pause the old group and enable the verified replacement. Pausing preserves
history; it is not assumed to free the 5,000 slots. For partial repairs, pause specified keyword IDs
and keep observed relevant winners. Do not increase bids during a dictionary repair.

Bulk shape: `allowPartialSuccess` plus `items[{correlationId, data}]`. Use <=500 items per batch as
an operator choice. Correlation IDs must be unique in the request. Check CLI exit status, valid JSON,
expected result count, unique returned correlation IDs and success for **every** item. A parse error
or partial failure is failure, never assumed success. Read back every keyword page, parent IDs, texts,
match types, statuses, bid currency/value, Search Match, negatives, daily budgets and native end times.
Save before/after snapshots and the actual repair manifest. Preserve original hypotheses, but add a
dated operational amendment which supersedes unsupported/currently unsafe instructions.

### E. Treat future zeros as a queue, not a verdict

The following intervals are experiment heuristics, not Apple thresholds:

| Stable observation | Action |
|---|---|
| First 14 completed days | Observe. No zero-only deletion, rotation or automatic bid increase. |
| Whole campaign lacks delivery | Verify eligibility/report completeness/timezone and isolate causes; core seeds remain. |
| At least 28 completed stable days, campaign has delivery, weak phrase has explicitly observed zero | Queue the weak phrase for replacement with a reviewed candidate. |
| Same window, natural relevant protected core seed has zero | Keep it; rare/expensive demand is unresolved. |
| Off-topic traffic, unsupported intent or sufficient spend without the declared result | Review sooner against sample, attribution lag and the bounded loss criterion. |

Rotation may replace at most 10–20% of a basket per fortnight as a chosen operator ceiling; it is
not an obligation to fill that amount. Export existing IDs, metrics, created time, stable bid phase,
reason and replacement first. Missing rows remain unknown. Never change bids and vocabulary together
and claim their effects were isolated. A one-week experiment ends after a week; 14/28-day rules do
not silently extend spending or authorize a relaunch. An end-of-week report is a checkpoint, not
proof that the new dictionary paid back or caused an organic lift.
