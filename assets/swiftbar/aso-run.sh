#!/bin/bash
# One skill action for one store, run in the Terminal window SwiftBar opens.
# usage: aso-run.sh collect|page|publish STORE
#   collect  collect --ranks (the Top-200 sweep, about an hour); refused while another sweep runs
#   page     export + build + check
#   publish  export + build + check + publish (the owner's standing go is in the store's config.md)

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
PY=$(command -v python3)
HERE=$("$PY" -c 'import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))' "$0")
SKILL_DIR="${ASO_SKILL_DIR:-$(cd "$HERE/../.." && pwd)}"
COPILOT="$SKILL_DIR/scripts/copilot.py"
ACTION="${1:-}"
STORE="${2:-}"
DAY=$(date +%F)

finish() { echo; read -n 1 -s -r -p "Done ($1). Press any key to close."; echo; exit "$1"; }
step() { echo; echo "▶ $*"; "$@"; }

[ -d "$STORE" ] || { echo "No store at: $STORE"; finish 2; }

case "$ACTION" in
  collect)
    pid=$(pgrep -f 'copilot\.py (collect|cycle)|ledger\.py.* refresh|rank_audit\.py' | head -1)
    if [ -n "$pid" ]; then
      echo "A sweep is already running (pid $pid). Apple allows one at a time per machine."
      finish 3
    fi
    step "$PY" "$COPILOT" collect --ranks --store "$STORE" || finish $?
    ;;
  page | publish)
    step "$PY" "$COPILOT" export --store "$STORE" --as-of "$DAY" || finish $?
    step "$PY" "$COPILOT" build --store "$STORE" || finish $?
    step "$PY" "$COPILOT" check --store "$STORE" || finish $?
    if [ "$ACTION" = publish ]; then
      step "$PY" "$COPILOT" publish --store "$STORE" || finish $?
    fi
    ;;
  *)
    echo "usage: aso-run.sh collect|page|publish STORE"
    finish 2
    ;;
esac
finish 0
