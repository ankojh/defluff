#!/usr/bin/env bash
set -euo pipefail

LABEL="local.defluff.backend"
GUI_DOMAIN="gui/$(id -u)"

launchctl bootout "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1 || true
echo "Stopped backend service: $LABEL"
