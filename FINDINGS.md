# Findings

Empirical observations from running this skill against real apps.
Each finding is dated and sourced. Findings that drove roadmap items name the item.

---

## ASA — Apple Search Ads API multi-app and organization setup

**Date:** 2026-08-26  
**Source:** live asc ads API calls [live:asc-ads-api@2026-08-26]

### Current state
- ASA credentials configured in `~/.asc/config.json` under an organization (e.g. orgId: `<ORG_ID_A>`)
- When an org has 0 campaigns for an app, `POST /v5/search/targeting/keywords/suggestions` may return HTTP 404 for `adamId=<APP_ID_B>`
  because the app is not yet associated with active campaign context in that organization.

### UI correction (2026-08-26)
Apple Ads UI does **not** have a `Settings → Apps → Add App` screen — that step does not exist.
Apps are available across all orgs on the same Apple Developer account automatically.
Apps appear in the app chooser within the org without any manual step.
**However**: `POST /v5/search/targeting/keywords/suggestions` with `adamId=<APP_ID>` still
returns HTTP 404 until a campaign shell exists. The UI app picker and the API access are separate concerns.
Reason: If an app has never had a campaign in that org, the API lacks the campaign context
it needs to return suggestions. Creating any campaign (even $0 budget, draft/never started) enables it.

### What's needed to get real popularity scores
1. Go to [ads.apple.com](https://ads.apple.com) → your organization
2. Create a new Search Ads campaign → choose your target app → any ad group
   → Keywords step. You will see Popularity column (5–100). No need to fund or launch.
3. Optionally: keep the draft campaign to enable the API endpoint:
   `POST /v5/search/targeting/keywords/suggestions` with `adamId=<APP_ID>` works after
   a campaign shell exists. Test with the curl command below after creating the draft.
4. Configure `asc ads` if needed:
   ```bash
   asc ads auth login --name "My App Ads" \
     --client-id "SEARCHADS.xxx" \
     --team-id "SEARCHADS.xxx" \
     --key-id "KEY_ID" \
     --private-key ./key.pem \
     --org "TARGET_ORG_ID"
   ```
5. Test:
   ```bash
   echo '{"adamId":"<APP_ID>","countriesOrRegions":["US"],"limit":50}' > /tmp/req.json
   asc ads api request --method POST \
     --path "v5/search/targeting/keywords/suggestions" \
     --org "TARGET_ORG_ID" --file /tmp/req.json --output json
   ```
   Expected response includes `popularityRange: {minPopularity: N, maxPopularity: M}` per keyword.

### Drives
- Roadmap item R-10 (Apple Ads popularity scores as volume proxy)

---

## Rank audit — hints-based expansion results (2026-08-26)

**Date:** 2026-08-26  
**Source:** rank_audit.py --expand-from-hints, 25 markets, ~500 queries [live:itunes-search-api@2026-08-26]  
**Full report:** `marketing/reports/aso_rank_audit_hints_2026-08-26.md` (in app repo)

### Key findings

**Niche terms are systematically under-optimised across non-English markets.**
In multi-market testing, localized regional terms often rank well organically simply because major competitors fail to target native vocabulary. Adding them explicitly to metadata consistently improves rank.

**India surprise: #7 for a category-adjacent query.**
`IN` market weight=8 (same as KR). High traffic volume with lower competitive barrier for well-localized English metadata.

**DE is frequently a high-opportunity market by composite score.**
Relatively high purchasing power combined with moderate competition in specific utility and lifestyle niches.

**Apple autocomplete hints differ significantly from manual keyword lists.**
Hint expansion returns real search suggestions that manual brainstorming misses entirely.
This confirms: hint expansion is the right approach, manual lists are an inferior substitute.

### Drives
- Roadmap items R-13 (historical tracking), R-17 (rank_audit in auto cycle)

---

## iTunes Search API — observed behaviour

**Date:** 2026-08-19 to 2026-08-26  
**Source:** harvest_keywords.py, rank_audit.py repeated runs

- Returns up to 200 results per query (app results, not web results)
- `total_results` varies 0–200; 200 means the category is large, not that there are exactly 200 apps
- Rate limit: no documented limit; empirically 2 req/sec is stable, 5 req/sec occasionally returns
  empty arrays (not 429, just `{"resultCount":0,"results":[]}`) — treated as "absent" which is wrong
- Autocomplete hints endpoint (`MZSearchHints`) returns 0–10 suggestions, popularity-ordered;
  more sensitive to rate than search endpoint — 1 req/sec recommended
- Storefront header `X-Apple-Store-Front` is required for hints; wrong value → wrong market results
- `bundleId` field in results is reliable for identifying the app

### Drives
- Roadmap item R-12 (rate limiting and retry)

---

## Skill portability — cross-app test

**Date:** 2026-08-26  
**Source:** running skill across multiple standalone app repositories

The skill correctly resolved `$APP_ID` and `$VERSION` from
`marketing/config.md`. All script paths resolved via `$SKILL_DIR`. No app-specific
assumptions leaked during a full status + rank_audit run.

### Drives
- Roadmap item R-16 (multi-app support tested and verified)

---

## Apple Search Popularity is Relative, Not Absolute — Storefront Scale & ASA Sweet Spot

**Date:** 2026-09-05  
**Source:** Live production app audit & feedback

### Findings
1. **Search Popularity (1–5 dots in UI / 5–100 index)**:
   - Apple Search Popularity is a *storefront-relative* metric, not absolute monthly search count.
   - A score of 70 in Ukraine (UA) may represent 20–50 searches/month, whereas a score of 70 in Spain (ES) or US represents thousands. Raw KEI ranking without storefront market weight falsely inflates micro-markets over tier-1/tier-2 commercial markets.
2. **ASA to Organic Top 3 Mechanics**:
   - Downloads from exact-match ASA queries boost query-specific download velocity and conversion rate, signaling App Store relevance and pulling organic rank up into Top 3.
   - **Sweet Spot (#4–#15)**: Bidding on keywords already ranked #4–#15 with weak competitor defense (<500 reviews) delivers the highest organic rank lift per dollar spent.
   - Bidding on #1–#3 is redundant (organic is free), while bidding from #50+ without prior ASO metadata optimization is cost-prohibitive.

### Drives
- Closes R-17 (Market scale weighting) and R-18 (ASA Strike Zone algorithm) in v0.4.0.

## ASA — Oversized Discovery batch caused budget atomization and an off-topic auto-discovered query

**Date:** 2026-09-20
**Source:** live `asc ads` API calls against Compresso's UA (`2144693006`) and PL (`2144698265`)
campaigns [live:asc-ads-api@2026-09-20]

### What happened
On 2026-09-19, both campaigns' keyword lists were expanded in a single batch: UA from 12 to 47
(+29 BROAD), PL from 18 to 46 (+28 BROAD). Both campaigns run at $5.00/day.

### Evidence
`asc ads reports apps search-terms` (requires `timeRange.timeZone: "ORTZ"`, not `"UTC"`, or the
endpoint 400s) for 2026-09-16 → 09-20 showed:
- UA: 78 total impressions across all 47 keywords. 53 of those 78 belonged to one EXACT keyword
  (`video compressor`) that predated the batch. The 29 newly added keywords logged 0–2 impressions
  each — no keyword in the new batch reached a sample large enough to judge in the campaign's 7-day
  window.
- PL: the BROAD batch auto-discovered the search term **"immich"** — 13 impressions, $0 spend,
  0 taps. Immich is an open-source self-hosted photo-backup app; it has no topical relationship to
  Compresso's compression/cleanup product. This is a live instance of the bleeding-query pattern in
  `references/apple-ads.md` §6 Step B.2, except it was BROAD-match auto-discovery finding an
  off-topic query rather than a user searching a wrong-intent phrase directly — the risk case that
  large, unreviewed BROAD batches create.

### Root cause
A fixed daily budget divided across dozens of keywords gives each one only a fraction of daily
auction liquidity — most never clear the cold-start reserve price (§3 second-price auction
mechanics) often enough to produce a judgeable sample before a 7-day test window closes. Broad
match compounds this: each additional seed also expands the algorithmic query-matching surface
without human review between batches.

### Fix applied
Paused all 29 (UA) and 26 of 28 (PL) newly added BROAD keywords that showed no measurable signal;
kept only the ones with an observed tap. Added `immich` as an EXACT campaign-level negative on the
PL campaign. Raised bids only on keywords with at least one observed tap in the search-terms report.

### Roadmap item this drove
Added §3b "Discovery Batch Size" to `references/apple-ads.md` and a one-sentence cap in `SKILL.md`
step 2b: cap a single Discovery-campaign expansion at 5–10 new BROAD seeds, and pull search-terms
within 48 hours of any batch (not at window close) specifically to catch off-topic auto-discovery
while spend is still near $0.

## Skill bugs found and fixed — storefront coverage, hidden progress, and a lenient "covered" bar

**Date:** 2026-09-20
**Source:** live usage of `rank_audit.py`, `harvest_keywords.py`, `copilot.py cycle`, and `ledger.py
report` against Compresso's real store, during the NO/IL/RO ASA candidate research documented in
the previous entry.

### Bug 1 — `harvest_keywords.py` and `rank_audit.py` each hard-coded a different, incomplete storefront list

`harvest_keywords.py hints --storefront ro ...` failed with `invalid choice: 'ro' (choose from
'de', 'gb', 'ua', 'us')` — not because Apple doesn't run a Romanian App Store (it does; storefront
ID 143487), but because the script's own `STOREFRONTS` dict only ever had 4 entries, added when the
file was first written for a different app (marketing/README.md's "weekly" 4-market set). Separately,
`rank_audit.py`'s own `STOREFRONTS` dict had grown to 24 markets over time but never included `ro`,
`no`, or dozens of other real storefronts — so `--expand-from-hints --markets ro,no` returned
"0/0 ranked" silently (the `country in STOREFRONTS` check in `run_audit()` just fell through to the
fallback-keyword branch with no error). Two files, two independently incomplete copies of the same
fact, each missing different markets, meant a fix to one never protected the other.

**Fix**: extracted `scripts/storefronts.py` — one dict, all 155 real Apple App Store storefronts
(sourced from Apple's own affiliate storefront ID table), self-checked. Both `harvest_keywords.py`
and `rank_audit.py` now import from it. `rank_audit.py`'s `MARKET_WEIGHT` (used only for query-budget
sizing) keeps its curated 25-market set with an explicit `DEFAULT_MARKET_WEIGHT` fallback for any
other storefront rather than a silent `.get(..., 3)`.

### Bug 2 — `copilot.py cycle`'s funnel step suppressed all its own subprocess's output

`subprocess.run([...], stdout=subprocess.DEVNULL)` around the `pull_funnel.py` call meant a normal,
multi-minute ASC analytics pull (Apple documents funnel reporting as "not real-time") produced zero
visible output until the whole thing finished. An operator watching the cycle had no way to tell
"still pulling" apart from "hung" — which led directly to killing a perfectly healthy process
mid-pull and losing that data, purely because the tool gave no signal either way.

**Fix**: removed the `DEVNULL`, let `pull_funnel.py`'s own progress print through, and added an
explicit note in the step header that ASC funnel reporting is genuinely slow by design.

### Bug 3 — `ledger.py` Section C called a market "covered" whenever *any* open hypothesis targeted it, regardless of actual rank

Before this fix, `section_c()`'s `covered` set was built purely from `{m for h in hyps if not
verdict for m in hyp_markets(h)}` — a market's presence in some hypothesis's `markets:` field, full
stop. A position of #6 in Israel, #11 in Norway, or #26 in Sweden all rendered as "covered by an
open hypothesis" in the money-at-stake table even though none of those are a dominant position by
any reasonable definition — an open hypothesis in flight is evidence someone is *trying*, not that
the position is *won*. This produced a materially wrong picture during a real research session: a
manual re-check using "top-3 for a small storefront, top-5 for a large one" found every single row
the ledger had marked "covered" was still genuinely open ground.

**Fix**: added `is_dominant(market, pos)` — true top-3 (or top-5 for `us/gb/de/fr/jp/cn`, where a
result page shows more competing apps before the fold) as of the *latest* observation, never based
on hypothesis presence. A dominant position is now excluded from Section C entirely (nothing left to
claim); a non-dominant position with an open hypothesis reads as `open hypothesis, not yet dominant`
instead of `covered`, and a non-dominant position with no hypothesis still reads `UNCLAIMED`.

### Why this batch of fixes, together

All three bugs share one shape: a tool silently gave a confident-looking answer to a question it
had not actually checked (a storefront it never queried, a process it gave no status on, a market it
called defended without checking the number). Each is now checked explicitly instead of assumed.
