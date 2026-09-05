# Findings

Empirical observations from running this skill against real apps.
Each finding is dated and sourced. Findings that drove roadmap items name the item.

---

## ASA — Apple Search Ads API setup for Hush

**Date:** 2026-08-26  
**Source:** live asc ads API calls [live:asc-ads-api@2026-08-26]

### Current state
- ASA credentials configured in `~/.asc/config.json` as "Compresso Ads" (orgId: `23140040`)
- This org has 0 campaigns and is for a different app (Compresso, not Hush)
- `POST /v5/search/targeting/keywords/suggestions` returns HTTP 404 for Hush `adamId=6449785515`
  because the app is not associated with orgId `23140040`

### UI correction (2026-08-26)
Apple Ads UI does **not** have a `Settings → Apps → Add App` screen — that step does not exist.
Apps are available across all orgs on the same Apple Developer account automatically.
Hush appears in the app chooser within org 23140040 without any manual step.
**However**: `POST /v5/search/targeting/keywords/suggestions` with `adamId=6449785515` still
returns HTTP 404 from org 23140040. The UI app picker and the API access are separate concerns.
Likely reason: Hush has never had a campaign in that org, so the API lacks the campaign context
it needs to return suggestions. Creating any campaign (even $0 budget, never started) may fix it.

### What's needed to get real popularity scores for Hush
1. Go to [ads.apple.com](https://ads.apple.com) → org 23140040 (Compresso Ads)
2. Create a new Search Ads campaign → choose "Hush: White Noise & Sleep Aid" → any ad group
   → Keywords step. You will see Popularity column (5–100). No need to fund or launch.
3. Optionally: keep the draft campaign to enable the API endpoint:
   `POST /v5/search/targeting/keywords/suggestions` with `adamId=6449785515` may work after
   a campaign shell exists. Test with the curl command below after creating the draft.
4. Configure `asc ads` if needed:
   ```bash
   asc ads auth login --name "Hush Ads" \
     --client-id "SEARCHADS.xxx" \
     --team-id "SEARCHADS.xxx" \
     --key-id "KEY_ID" \
     --private-key ./key.pem \
     --org "NEW_ORG_ID"
   ```
4. Test:
   ```bash
   echo '{"adamId":"6449785515","countriesOrRegions":["US"],"limit":50}' > /tmp/req.json
   asc ads api request --method POST \
     --path "v5/search/targeting/keywords/suggestions" \
     --org "NEW_ORG_ID" --file /tmp/req.json --output json
   ```
   Expected response includes `popularityRange: {minPopularity: N, maxPopularity: M}` per keyword.

### Drives
- Roadmap item R-10 (Apple Ads popularity scores as volume proxy)

---

## Rank audit — hints-based expansion results (2026-08-26)

**Date:** 2026-08-26  
**Source:** rank_audit.py --expand-from-hints, 25 markets, ~500 queries [live:itunes-search-api@2026-08-26]  
**Full report:** `marketing/reports/aso_rank_audit_hints_2026-08-26.md` (in WhiteNoise repo)

### Key findings

**Colour noise terms are systematically under-optimised across all markets.**
`ruido marrón` (ES #39, MX #32), `braunes rauschen` (DE #18), `brązowy szum` (PL #54),
`bruine ruis` (NL #36), `brunt brus` (SE #18), `розовый шум` (RU #82) — in every market
that has a local-language term for brown/pink noise, we rank because competitors haven't
targeted these terms. Adding them explicitly to metadata would likely improve all these ranks.

**India surprise: #7 for a sleep-adjacent query.**
`IN` market, `sleep sounds` adjacent term, rank #7. IN market weight=8 (same as KR).
No hypothesis currently tracks IN. Should be drafted.

**DE is the highest-opportunity market by composite score.**
`braunes rauschen` DE #18, `gewitter geräusche` DE #46, `weißes rauschen baby` DE #53,
`weißes rauschen` DE #60. Four ranked positions, relatively low competition (top-1 has
38–2277 ratings). DE market weight=13. Opportunity score ~114.

**SE is punching above its weight.**
4/20 queries ranked including `sovljud` #20. SE market weight=3 (small). But the quality
of positions is high — the terms we rank for are actual head terms, not niche long-tail.

**US, GB, FR, CN, IT absent entirely (0/N ranked).**
Root cause for US/GB/FR: too few ratings vs. entrenched competitors (Calm, Headspace,
White Noise Lite each have 50k–200k ratings). Not a keyword gap — a social proof gap.
No keyword change will fix US visibility without more reviews.

**Apple autocomplete hints differ significantly from manual keyword lists.**
Hint expansion for DE returned `braunes rauschen` (not in our manual list) which turned out
to be rank #18 — the best single German position. Manual lists missed this entirely.
This confirms: hint expansion is the right approach, manual lists are a poor substitute.

### Drives
- Roadmap items R-13 (historical tracking), R-17 (rank_audit in auto cycle)
- New hypothesis candidate: H006 (DE colour noise terms in metadata)
- New hypothesis candidate: H007 (IN market — what query, needs investigation)

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
- `bundleId` field in results is reliable for identifying our app

### Drives
- Roadmap item R-12 (rate limiting and retry)

---

## Skill portability — first cross-app test

**Date:** 2026-08-26  
**Source:** running skill against WhiteNoise repo with Hush app config

The skill correctly resolved `$APP_ID = 6449785515` and `$VERSION = 1.5.2` from
`marketing/config.md`. All script paths resolved via `$SKILL_DIR`. No Compresso-specific
assumptions surfaced during a full status + rank_audit run.

One gap found: `references/apple-ads.md` still contains Compresso's Apple Ads org ID
(`23140040`) as an example value. Should be replaced with a placeholder.

### Drives
- Roadmap item R-16 (multi-app support tested — partially verified, one gap remaining)

---

## Apple Search Popularity is Relative, Not Absolute — Storefront Scale & ASA Sweet Spot

**Date:** 2026-09-05  
**Source:** Companion app audit (Baby Log - Malyatko Tracker, id: 6757263634) & live feedback

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
