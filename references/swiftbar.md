# Menu bar: SwiftBar

A thin face over the skill's own commands. It shows, per store, how many hypotheses are due, when the last rank
sweep was and whether one is running, and starts the long jobs in Terminal. It reads files only and never the
network; every number comes from the same `ledger report` and `ranks.csv` the rest of the skill reads.

Files, all in `assets/swiftbar/`:

| File | Does |
|---|---|
| `ios-aso-copilot.5m.sh` | the plugin; SwiftBar runs it every 5 minutes (the `5m` in the name) |
| `aso-run.sh` | the menu's actions: `collect` (the Top-200 sweep), `page` (export, build, check), `publish` |
| `install.sh [STORE ...]` | one-time setup: links the plugin, sets SwiftBar's plugin folder, adds stores, starts SwiftBar |

Stores come from `~/.config/ios-aso-copilot/stores`, one path per line (`<app repo>/marketing` of the main checkout).

## Is it set up?

```bash
test -L "$HOME/Library/Application Support/SwiftBar/Plugins/ios-aso-copilot.5m.sh" && pgrep -x SwiftBar >/dev/null \
  && echo "set up" || echo "not set up"
```

## What to do

- **Set up.** The user can start a pass from the menu, so do not start a second one while the menu shows a sweep
  running. After any `collect`, `export` or `publish` you ran yourself, refresh the menu at once:
  `open -g swiftbar://refreshallplugins`.
- **Not set up** (no link, SwiftBar not running, or no store listed). Run the commands yourself, exactly as the
  menu would: `collect --ranks`, `export --as-of`, `build`, `check`, `publish`. Do not wait on the menu and do not
  stop. Say once that `assets/swiftbar/install.sh <store>` adds it.
- **Never install SwiftBar unasked** (`brew install --cask swiftbar` is the user's call); `install.sh` only needs it
  to exist.
- **One sweep at a time per machine.** Apple's search limit is shared by every app and project. The menu and
  `aso-run.sh collect` refuse while a sweep runs; check it the same way before you start one:
  `pgrep -f 'copilot\.py (collect|cycle)|ledger\.py.* refresh|rank_audit\.py'`.
- A store's `config.md` decides what `publish` may send (`**Never publish**:`); the menu adds nothing to that.
