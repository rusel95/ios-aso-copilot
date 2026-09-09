# Changelog

What has landed, newest first. `ROADMAP.md` holds what has not.

Each entry names the roadmap items it closes. A number that disappears from the roadmap can be
followed here. Changes are pushed to [github.com/rusel95/ios-marketing-ops](https://github.com/rusel95/ios-marketing-ops).

---

## v1.3.1 — Evidence ledger hardening — 2026-09-08

- Opens every run with a deterministic hypothesis/rank/value ledger and refuses fabricated outcomes,
  stale carried ranks, request-error zeros, non-comparable deltas and unobserved draft baskets.
- Replaced predictive opportunity and ROI claims with source-labelled observations and explicit
  uncertainty; RespectASO, ASC, Apple Ads, PPO and CPP now have documented evidence boundaries.
- Added validation for the `markets` and `queries` fields required to join a rank hypothesis to its
  observations. Legacy records stay visible as malformed until their scope is verified.
- Added the open capability roadmap for ASC imports, paired history, exposure reconciliation,
  localization QA, creative tests, paid-query learning, cohorts and proceeds reconciliation.

## v0.4.0 — Market scale weighting, ASA Strike Zone, and instant JSON re-analysis — 2026-09-05

- **Storefront Market Scale Weighting**: Differentiates relative local Search Popularity (0–100 or 1–5 dots) from estimated absolute search volume. Prevents small-market traps (e.g., Ukraine where native niche terms have high relative score but tiny absolute volume) by scaling traffic potential across Tier 1, Tier 2, and Tier 3 markets.
- **ASA Strike Zone & Sweet Spot Scoring**: Dedicated scoring algorithm to identify high-ROI Apple Search Ads opportunities to push organic rank into the Top 3. Heavily rewards ranks #4–#15, weak competitor defense (<500 reviews), and open title gaps. Classifies actions: `🚀 ASA Strike Zone`, `⚡ Title Gap + ASA`, `🧪 Discovery Match`, `🛡️ Brand Defense`, and `📝 ASO First`.
- **Instant JSON Re-Analysis (`--reanalyze`)**: Enables sub-second recalculation of all scores and tactical recommendations on existing audit JSON files without querying Apple Search APIs.
- **Multi-Niche Adaptability (`--niche`)**: Built-in support for `baby` and `whitenoise` seed trees across 25 storefronts.

---

## v0.3.0 — Multi-market hypothesis concurrency & full JSON snapshot engine — 2026-09-04

- **Market concurrency rule**: Explicitly formalized that multiple market-specific hypotheses (1 per market) can run concurrently in the same app release across up to 25 regional App Store markets (regional App Stores are disjoint ecosystems that do not cross-contaminate).
- **Market query basket & snapshots**: Hypotheses now evaluate against the full market query basket (20–100 queries) rather than a single isolated keyword.
- **rank_audit.py JSON snapshots**: Automatically saves structured JSON alongside Markdown reports (`*.json`) capturing full top-200 state, competitor data, and opportunity scores for automated diffing.
- **diff_snapshots.py**: New comparison tool to compute exact before/after diffs between any two snapshots across all markets.

---

## v0.2.0 — rank_audit.py + hint expansion + npx installer — 2026-08-26

Closes roadmap items: R-01, R-02, R-03, R-04.

**rank_audit.py** — new script for full keyword rank audit with opportunity scoring.
- Market-proportional query budgets (US=90, DE=50, UA=20, …) instead of fixed 20 per market
- `--expand-from-hints` mode: uses Apple's autocomplete endpoint to generate queries from seeds
  (what users actually type, not what we guess)
- Opportunity score formula: `market_weight × volume_proxy × rank_reachability × (1 − difficulty)`
- `--self-check` flag for API connectivity validation
- Saves full Markdown report to `$STORE/reports/aso_rank_audit_YYYY-MM-DD.md`

**SKILL.md** — added rank_audit.py documentation, market-proportional budget table, and
instruction to use hint expansion rather than manual keyword lists.

**npx installer** — `bin/cli.js` enables `npx ios-marketing-ops install` to symlink the skill
into `~/.claude/skills/` or `~/.kiro/skills/` with `--kiro`/`--path` flags.

**Repository** — extracted from `~/.claude/skills/ios-marketing-ops/` into standalone git repo
at `~/Desktop/ios-marketing-ops/`, pushed to github.com/rusel95/ios-marketing-ops.
`~/.claude/skills/ios-marketing-ops` is now a symlink to the Desktop repo.

**Files changed:**
- `scripts/rank_audit.py` — new, 400 lines
- `SKILL.md` — rank_audit section added
- `bin/cli.js` — new npx installer
- `package.json` — new
- `README.md` — new
- `CHANGELOG.md` — new (this file)
- `ROADMAP.md` — new
- `FINDINGS.md` — new

---

## v0.1.0 — initial skill extraction — 2026-08-19

Initial extraction from production iOS app marketing operations.

**What shipped:**
- `SKILL.md` — full ASO iteration cycle: status/manual/auto modes, phase detection,
  hypothesis lifecycle, metadata fence
- `scripts/harvest_keywords.py` — Apple autocomplete hints + competitor discovery
- `scripts/economics.py` — LTV / break-even / scaling verdict
- `references/` — aso-loop.md, commands.md, provenance.md, state-store.md,
  apple-ads.md, playbooks.md
- `assets/store-template/` — seed files for marketing/ store initialization

**Context:** born out of real-world App Store ASO work (early keyword hypotheses,
multi-locale metadata pipelines, ASC metadata management).
