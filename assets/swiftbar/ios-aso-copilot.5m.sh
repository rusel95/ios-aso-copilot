#!/bin/bash
# <xbar.title>iOS ASO Copilot</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.desc>Menu-bar view of the ios-aso-copilot stores: hypotheses due, last rank sweep, collect, page and publish. Reads files only; the actions open Terminal.</xbar.desc>
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
#
# Stores to show: one path per line in ~/.config/ios-aso-copilot/stores (override with ASO_STORES).
# A store is <app repo>/marketing of the app's main checkout. Setup: install.sh next to this file.

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PY=$(command -v python3)
HERE=$("$PY" -c 'import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))' "$0")
SKILL_DIR="${ASO_SKILL_DIR:-$(cd "$HERE/../.." && pwd)}"
COPILOT="$SKILL_DIR/scripts/copilot.py"
RUN="$HERE/aso-run.sh"
CONF="${ASO_STORES:-$HOME/.config/ios-aso-copilot/stores}"
TODAY=$(date +%F)

# A heartbeat, so "is SwiftBar running the plugin?" has an answer without looking at the menu bar.
mkdir -p "$HOME/.cache/ios-aso-copilot" && date +%FT%T > "$HOME/.cache/ios-aso-copilot/swiftbar-last-run"

stores=()
if [ -f "$CONF" ]; then
  while IFS= read -r line; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [ -n "$line" ] && stores+=("${line/#\~/$HOME}")
  done < "$CONF"
fi
if [ ${#stores[@]} -eq 0 ]; then
  echo "ASO ?"
  echo "---"
  echo "No stores yet: add one path per line to $CONF"
  exit 0
fi

# One sweep at a time per machine: Apple's search limit is shared by every app and project.
RUNNING=$(pgrep -f 'copilot\.py (collect|cycle)|ledger\.py.* refresh|rank_audit\.py' | head -1)

total_due=0
body=""
add() { body+="$1"$'\n'; }

for S in "${stores[@]}"; do
  name=$(basename "$(dirname "$S")")
  if [ ! -d "$S" ]; then
    add "$name: store not found | color=red"
    add "--$S"
    continue
  fi

  summary=$("$PY" "$COPILOT" ledger --store "$S" report --as-of "$TODAY" 2>/dev/null | grep -m1 -E '^[0-9]+ judged')
  due=$(sed -n 's/.* \([0-9][0-9]*\) due.*/\1/p' <<<"$summary")
  notshipped=$(sed -n 's/.* \([0-9][0-9]*\) not shipped.*/\1/p' <<<"$summary")
  total_due=$((total_due + ${due:-0}))

  last=$(awk -F, 'NR>1 && $1>m{m=$1} END{print m}' "$S/metrics/ranks.csv" 2>/dev/null)
  age=""
  if [ -n "$last" ]; then
    then_s=$(date -j -f %F "$last" +%s 2>/dev/null) && age=" ($(( ($(date +%s) - then_s) / 86400 )) d ago)"
  fi

  # The published page: https://<owner>.github.io/<site>/<path>/ from the store's Pages lines.
  repo=$(sed -n 's/^\*\*Pages repository\*\*: *//p' "$S/config.md" 2>/dev/null | head -1)
  path=$(sed -n 's/^\*\*Pages path\*\*: *//p' "$S/config.md" 2>/dev/null | head -1)
  repo="${repo%.git}"
  url=""
  if [[ "$repo" =~ ^https://github\.com/([^/]+)/([^/]+)$ ]] && [ -n "$path" ]; then
    url="https://${BASH_REMATCH[1]}.github.io/${BASH_REMATCH[2]}/${path}/"
  fi

  add "$name · ${due:-?} due · ${notshipped:-?} not shipped"
  add "--Last rank sweep: ${last:-never}${age}"
  [ -n "$url" ] && add "--Open dashboard | href=$url"
  [ -f "$S/public/index.html" ] && add "--Open local page | href=file://$S/public/index.html"
  add "--Open store folder | href=file://$S"
  add "-----"
  if [ -n "$RUNNING" ]; then
    add "--Rank sweep running (pid $RUNNING) | color=orange"
  else
    add "--Collect + rank sweep (about an hour) | bash=\"$RUN\" param1=collect param2=\"$S\" terminal=true refresh=true"
  fi
  add "--Export + build page | bash=\"$RUN\" param1=page param2=\"$S\" terminal=true refresh=true"
  add "--Export, build, publish | bash=\"$RUN\" param1=publish param2=\"$S\" terminal=true refresh=true"
done

if [ -n "$RUNNING" ]; then
  echo "ASO ⟳"
elif [ "$total_due" -gt 0 ]; then
  echo "ASO $total_due"
else
  echo "ASO ✓"
fi
echo "---"
printf '%s' "$body"
