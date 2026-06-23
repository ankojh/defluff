#!/usr/bin/env bash
set -euo pipefail

# Remove the Defluff runtime: stop and unregister the backend LaunchAgent and
# delete ~/Library/Application Support/Defluff. With --purge, also stop Postgres
# and delete the pulled Ollama model. Homebrew packages are left untouched.
DEFLUFF_HOME="${DEFLUFF_HOME:-$HOME/Library/Application Support/Defluff}"
LABEL="local.defluff.backend"
GUI_DOMAIN="gui/$(id -u)"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
PURGE=0
[[ "${1:-}" == "--purge" ]] && PURGE=1

echo "Stopping backend service..."
launchctl bootout "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

if [[ -d "$DEFLUFF_HOME" ]]; then
    echo "Removing $DEFLUFF_HOME"
    rm -rf "$DEFLUFF_HOME"
fi

if [[ "$PURGE" == "1" ]]; then
    MODEL="${OLLAMA_MODEL:-gemma4:26b}"
    echo "Purging: stopping Postgres and removing model $MODEL"
    brew services stop postgresql@15 >/dev/null 2>&1 || true
    ollama rm "$MODEL" >/dev/null 2>&1 || true
fi

echo "Done. (Defluff.app in /Applications and Homebrew packages were left in place.)"
