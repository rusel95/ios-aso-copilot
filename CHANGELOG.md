# Changelog

What has landed, newest first. `ROADMAP.md` holds what has not.

Each entry names the roadmap items it closes. A number that disappears from the roadmap can be
followed here. Changes are pushed to [github.com/rusel95/ios-marketing-ops](https://github.com/rusel95/ios-marketing-ops).

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

Initial extraction from Hush/WhiteNoise marketing work.

**What shipped:**
- `SKILL.md` — full ASO iteration cycle: status/manual/auto modes, phase detection,
  hypothesis lifecycle, metadata fence
- `scripts/harvest_keywords.py` — Apple autocomplete hints + competitor discovery
- `scripts/economics.py` — LTV / break-even / scaling verdict
- `references/` — aso-loop.md, commands.md, provenance.md, state-store.md,
  apple-ads.md, playbooks.md
- `assets/store-template/` — seed files for marketing/ store initialization

**Context:** born out of Hush White Noise ASO work (H001–H004 keyword hypotheses,
39-locale screenshot pipeline, ASC metadata management).
