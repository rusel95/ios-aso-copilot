# 🚀 ios-aso-copilot

### The Free, Open-Source Alternative to Astro MCP ($108/yr) for Indie iOS Developers

<p align="left">
  <a href="https://tryastro.app"><img src="https://img.shields.io/badge/Free%20Alternative%20to-Astro%20MCP%20($108%2Fyr)-6f42c1?style=for-the-badge&logo=apple&logoColor=white" alt="Free Alternative to Astro MCP"></a>
  <a href="https://github.com/rusel95/ios-aso-copilot"><img src="https://img.shields.io/badge/Cost-%240%20Free%20Forever-2ea44f?style=for-the-badge" alt="Free Forever"></a>
  <a href="https://skills.sh"><img src="https://img.shields.io/badge/Install-npx%20skills%20add%20rusel95%2Fios--aso--copilot-0969da?style=for-the-badge" alt="Install via Skills"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge" alt="MIT License"></a>
</p>

> [!IMPORTANT]
> ## 💡 Why pay $108/year for Astro MCP when your AI agent can do it for free?
> **`ios-aso-copilot`** delivers everything in Astro's keyword tracking & research plan — running agent-natively inside Claude Code, Cursor, Antigravity, or Codex:
>
> - 🔍 **Live Search Autocomplete Hints**: Real-time query suggestions directly from Apple's official App Store hints engine (`MZSearchHints.woa`).
> - 📊 **Keyword Rank Auditing**: Tracks your app's rank depth (up to 200) across 25+ storefronts via live iTunes Search API.
> - 🕵️ **Competitor Intelligence & Velocity**: Analyzes competitor 30d/90d review velocity, ratings, and days since last update via RSS feeds.
> - 💵 **Money-at-Stake Prioritization**: Sorts keyword opportunities by actual expected proceeds, not vanity metrics.
> - 🧪 **Hypothesis Testing & Unit Economics**: 21-day observation windows, anti-regression guards, and Apple Ads LTV/break-even models that proprietary tools don't offer.
>
> **Zero subscription fees. Zero closed-source Mac app lock-in. 100% open-source & git-versioned.**

---

### ⚔️ Feature Comparison: Astro MCP vs `ios-aso-copilot`

| Capability / Tool | Astro MCP (`tryastro.app`) | `ios-aso-copilot` (This Skill) | Status & Command |
|---|:---:|:---:|:---:|
| **Pricing & License** | **$108 / year** (closed-source) | **$0 Free Forever** (MIT open-source) | 🟢 **100% Free** |
| **Architecture** | Proprietary Mac app running on `localhost:8089` | **Agent Skill (zero apps to run)** | 🟢 **CLI / Agent Native** |
| **Rank Tracking** (`search_rankings`) | Tracked in local app DB | Live iTunes Search API (depth up to 200, 25+ markets) | 🟢 `python3 scripts/rank_audit.py` |
| **Search Autocomplete Hints** (`get_keyword_suggestions`) | Proprietary Astro backend | Direct Apple Search Hints API (`MZSearchHints.woa`) | 🟢 `python3 scripts/harvest_keywords.py hints` |
| **Live App Store Search** (`search_app_store`) | Returns 50–100 results | iTunes Search API across 25 regional storefronts | 🟢 `python3 scripts/rank_audit.py` |
| **Competitor Extraction** (`extract_competitors_keywords`) | NLP keyword extraction from ranked apps | Competitor title/subtitle analysis across top apps | 🟢 `python3 scripts/global_velocity_audit.py` |
| **Competitor Review Velocity** (`get_app_ratings`) | Simple average ratings by store | 30d & 90d velocity, recency, Soft Target classification | 🟢 **Superior** (RSS velocity + scoring) |
| **Data Ownership & Portability** | Locked in proprietary SQLite DB | Plain text CSV & Markdown in `marketing/` under Git | 🟢 **Git-Versioned** |
| **Money-at-Stake Opportunity Prioritization** | ❌ Not available | Net proceeds per sub × unclaimed gain × reach | 🚀 **Exclusive** (`scripts/ledger.py`) |
| **ASO Hypothesis Lifecycle & Anti-Regression** | ❌ Not available | 21-day observation windows, paired before/after | 🚀 **Exclusive** (`scripts/ledger.py`) |
| **Apple Ads Financial Modeling** | ❌ Not available | LTV/subscriber, LTV/trial, break-even CPT bid cap | 🚀 **Exclusive** (`scripts/economics.py`) |
| **Metadata Character Pre-flight** | ❌ Not available | 30/30/100 limit validation, cross-locale rules | 🚀 **Exclusive** |
| **Storefront Localization & CLDR Plural Engine** | ❌ Not available | Full in-app .xcstrings audit, CLDR plurals, zero-waste metadata & knownRegions | 🚀 **Exclusive** (`scripts/localization_tool.py`) |

---

**This is a skill, not an application.** The product is instructions an AI agent follows.
Scripts are tools the agent calls; they do nothing without the agent context.

---

## Install

### Via skills CLI (recommended for Claude Code, Cursor, Codex, Antigravity, etc.)

```bash
# Project-level
npx skills add rusel95/ios-aso-copilot

# Global (across all projects)
npx skills add rusel95/ios-aso-copilot -g
```

### Via npm package installer or symlink

```bash
# Symlinks into ~/.claude/skills/
npx ios-aso-copilot install

# For Kiro
npx ios-aso-copilot install --kiro

# Manual
ln -s ~/path/to/ios-aso-copilot ~/.claude/skills/ios-aso-copilot
```

## Usage

In Claude Code, Cursor, or Antigravity, once installed:

```
/ios-aso-copilot              → orientation: phase, open hypotheses, next action
/ios-aso-copilot auto         → unattended full cycle (rank → hypotheses → metadata)
/ios-aso-copilot manual       → guided step-by-step with approval at each decision
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
ios-aso-copilot/
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
cp -n -r ~/.claude/skills/ios-aso-copilot/assets/store-template/. ./marketing/

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
- GitHub: [github.com/rusel95/ios-aso-copilot](https://github.com/rusel95/ios-aso-copilot)
