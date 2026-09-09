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
