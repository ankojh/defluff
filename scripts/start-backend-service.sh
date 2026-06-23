#!/usr/bin/env bash
set -euo pipefail

# Install (or reinstall) the Defluff backend as a per-user LaunchAgent so it
# starts at login and is kept alive. Works both from the git checkout and from
# the installed runtime under ~/Library/Application Support/Defluff.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFLUFF_HOME="${DEFLUFF_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
LOG_DIR="$DEFLUFF_HOME/.logs"
LABEL="local.defluff.backend"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS_DIR/$LABEL.plist"
GUI_DOMAIN="gui/$(id -u)"
RUN_BACKEND="$SCRIPT_DIR/run-backend.sh"
HF_HOME_DIR="${HF_HOME:-$DEFLUFF_HOME/.cache/huggingface}"

mkdir -p "$LAUNCH_AGENTS_DIR" "$LOG_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>WorkingDirectory</key>
    <string>$DEFLUFF_HOME</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>DEFLUFF_HOME</key>
        <string>$DEFLUFF_HOME</string>
        <key>HF_HOME</key>
        <string>$HF_HOME_DIR</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
    <key>ProgramArguments</key>
    <array>
        <string>$RUN_BACKEND</string>
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
echo "Plist: $PLIST_PATH"
echo "Logs: $LOG_DIR/backend.out.log and $LOG_DIR/backend.err.log"
