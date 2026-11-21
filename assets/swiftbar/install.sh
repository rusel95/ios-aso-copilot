#!/bin/bash
# One-time SwiftBar setup for this skill. usage: install.sh [STORE ...]
# STORE = <app repo>/marketing of the app's main checkout; each one is added to ~/.config/ios-aso-copilot/stores.
# Needs SwiftBar (brew install --cask swiftbar). Safe to run again: it only repoints the link and adds new stores.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd -P)
PLUG="${SWIFTBAR_PLUGINS:-$HOME/Library/Application Support/SwiftBar/Plugins}"
CONF="${ASO_STORES:-$HOME/.config/ios-aso-copilot/stores}"

chmod +x "$HERE/ios-aso-copilot.5m.sh" "$HERE/aso-run.sh"
mkdir -p "$PLUG" "$(dirname "$CONF")"
ln -sfn "$HERE/ios-aso-copilot.5m.sh" "$PLUG/ios-aso-copilot.5m.sh"
touch "$CONF"
for s in "$@"; do
  grep -qxF "$s" "$CONF" || echo "$s" >> "$CONF"
done
defaults write com.ameba.SwiftBar PluginDirectory -string "$PLUG"

if pgrep -x SwiftBar > /dev/null; then
  osascript -e 'quit app "SwiftBar"' || true
  sleep 1
fi
open -a SwiftBar || echo "SwiftBar is not installed: brew install --cask swiftbar"

echo "Plugin: $PLUG/ios-aso-copilot.5m.sh -> $HERE/ios-aso-copilot.5m.sh"
echo "Stores ($CONF):"
sed 's/^/  /' "$CONF"
