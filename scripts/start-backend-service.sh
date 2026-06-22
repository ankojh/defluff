#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_DIR="$ROOT_DIR/.launchd"
PLIST_PATH="$PLIST_DIR/local.defluff.backend.plist"
LOG_DIR="$ROOT_DIR/.logs"
LABEL="local.defluff.backend"
GUI_DOMAIN="gui/$(id -u)"

mkdir -p "$PLIST_DIR" "$LOG_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>WorkingDirectory</key>
    <string>$ROOT_DIR</string>
    <key>ProgramArguments</key>
    <array>
        <string>$ROOT_DIR/scripts/run-backend.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$LOG_DIR/backend.out.log</string>
    <key>StandardErrorPath</key>
    <string>$LOG_DIR/backend.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1 || true
launchctl bootstrap "$GUI_DOMAIN" "$PLIST_PATH"
launchctl kickstart -k "$GUI_DOMAIN/$LABEL"

echo "Started backend service: $LABEL"
echo "Logs: $LOG_DIR/backend.out.log and $LOG_DIR/backend.err.log"
