# ios-marketing-ops

App Store marketing operations skill for Claude/Kiro AI agents.

Handles the full ASO iteration cycle: keyword research, rank auditing,
hypothesis tracking, metadata management, and Apple Ads setup.

## Install

```bash
# Via npx
npx ios-marketing-ops install

# Manual symlink
ln -s ~/Desktop/ios-marketing-ops ~/.claude/skills/ios-marketing-ops
```

## Usage in Claude Code / Kiro

```
/ios-marketing-ops          → status check
/ios-marketing-ops auto     → run full iteration cycle  
/ios-marketing-ops manual   → guided step-by-step
```

## Scripts

```bash
# Keyword rank audit (21+ markets, proportional budgets, Apple hints)
python3 scripts/rank_audit.py --bundle "com.your.app" --markets all --expand-from-hints --output report.md

# Keyword discovery via Apple autocomplete
python3 scripts/harvest_keywords.py hints --storefront us --term "white noise"

# Unit economics
python3 scripts/economics.py --self-check
```

## Requirements

- Python 3.10+
- `asc` CLI configured with App Store Connect API key
- App repo with `marketing/` store directory
