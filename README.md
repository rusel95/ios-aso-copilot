# ios-marketing-ops

App Store marketing operations skill for Claude/Kiro AI agents.

Handles the full ASO iteration cycle: keyword research, rank auditing,
hypothesis tracking, metadata management, and Apple Ads setup — for any iOS app.

**This is a skill, not an application.** The product is instructions an AI agent follows.
Scripts are tools the agent calls; they do nothing without the agent context.

---

## Install

### Via skills CLI (recommended for Claude Code, Cursor, Codex, Antigravity, etc.)

```bash
# Project-level
npx skills add rusel95/ios-marketing-ops

# Global (across all projects)
npx skills add rusel95/ios-marketing-ops -g
```

### Via npm package installer or symlink

```bash
# Symlinks into ~/.claude/skills/
npx ios-marketing-ops install

# For Kiro
npx ios-marketing-ops install --kiro

# Manual
ln -s ~/path/to/ios-marketing-ops ~/.claude/skills/ios-marketing-ops
```

## Usage

In Claude Code or Kiro, once installed:

```
/ios-marketing-ops              → orientation: phase, open hypotheses, next action
/ios-marketing-ops auto         → unattended full cycle (rank → hypotheses → metadata)
/ios-marketing-ops manual       → guided step-by-step with approval at each decision
```

## What it does

1. Detects ASO phase live: `P0-prelaunch → P1-review → P2-cold → P3-measure`
2. Runs keyword rank audit across 25 markets with opportunity scoring
3. Records weekly metrics, appends to `marketing/metrics/`
4. Judges hypotheses when their window closes, writes verdicts
5. Drafts next keyword hypothesis from opportunity leaderboard
6. Prepares App Store metadata changes up to the approval fence
7. Queues anything requiring human approval to `marketing/queue.md`

## Scripts

```bash
# Keyword rank audit — 25 markets, proportional budgets, Apple hint expansion
python3 scripts/rank_audit.py \
  --bundle "com.your.app" \
  --markets all \
  --expand-from-hints \
  --output marketing/reports/aso_rank_audit_$(date +%Y-%m-%d).md

# Keyword discovery via Apple autocomplete
python3 scripts/harvest_keywords.py hints --storefront us --term "white noise"

# Unit economics (LTV, break-even, scaling verdict)
python3 scripts/economics.py --self-check

# Self-test all scripts
python3 scripts/rank_audit.py --self-check
python3 scripts/harvest_keywords.py --self-check
python3 scripts/economics.py --self-check
```

## Repository structure

```
ios-marketing-ops/
├── SKILL.md          ← agent instructions (the operative document)
├── README.md         ← this file
├── CHANGELOG.md      ← what has landed
├── ROADMAP.md        ← what has not
├── FINDINGS.md       ← empirical observations from real runs
├── bin/
│   └── cli.js        ← npx installer
├── scripts/
│   ├── rank_audit.py       ← keyword rank + opportunity scoring (25 markets)
│   ├── harvest_keywords.py ← Apple autocomplete hints + competitor discovery
│   └── economics.py        ← LTV / break-even / scaling verdict
├── references/
│   ├── aso-loop.md         ← hypothesis lifecycle, verdict criteria
│   ├── commands.md         ← exact asc invocations, the approval fence
│   ├── provenance.md       ← source tagging rules
│   ├── state-store.md      ← marketing/ file schemas
│   ├── apple-ads.md        ← Apple Ads API setup
│   └── playbooks.md        ← experiments, CPPs, reviews
└── assets/
    └── store-template/     ← seed files for marketing/ initialization
```

## Per-app setup

Each app needs its own `marketing/` store in the app's repo:

```bash
# Seed the store (run once, never overwrites existing files)
cp -n -r ~/.claude/skills/ios-marketing-ops/assets/store-template/. ./marketing/

# Fill in your app's identity
nano marketing/config.md   # set App ID and version
```

## Requirements

- Python 3.10+
- `asc` CLI configured with App Store Connect API key ([rork.app/asc](https://rork.app/asc))
- For Apple Ads popularity scores: `asc ads` configured with Apple Search Ads credentials

## Tested on

- Multiple live production iOS apps in the App Store across utilities, audio, and niche consumer apps.

## Links

- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Roadmap: [ROADMAP.md](ROADMAP.md)
- Findings: [FINDINGS.md](FINDINGS.md)
- GitHub: [github.com/rusel95/ios-marketing-ops](https://github.com/rusel95/ios-marketing-ops)
