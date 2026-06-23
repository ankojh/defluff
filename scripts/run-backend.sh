#!/usr/bin/env bash
set -euo pipefail

# Resolve the runtime root. From the git checkout this is the repo root
# (scripts/..); when installed it is ~/Library/Application Support/Defluff and
# this script lives in $DEFLUFF_HOME/scripts. App settings (DATABASE_URL,
# OLLAMA_*, etc.) come from $DEFLUFF_HOME/.env via pydantic-settings, so this
# script only manages PATH, the Hugging Face cache, and the venv.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFLUFF_HOME="${DEFLUFF_HOME:-$(cd "$SCRIPT_DIR/.." && pwd)}"
BACKEND_DIR="${DEFLUFF_BACKEND_DIR:-$DEFLUFF_HOME/backend}"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export HF_HOME="${HF_HOME:-$DEFLUFF_HOME/.cache/huggingface}"

if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x /opt/homebrew/bin/python3.12 ]]; then
        PYTHON_BIN="/opt/homebrew/bin/python3.12"
    elif [[ -x /usr/local/bin/python3.12 ]]; then
        PYTHON_BIN="/usr/local/bin/python3.12"
    else
        PYTHON_BIN="python3.12"
    fi
fi

if [[ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        echo "$PYTHON_BIN was not found. Install Python 3.12 or set PYTHON_BIN." >&2
        exit 1
    fi
    "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
    "$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip
    "$BACKEND_DIR/.venv/bin/python" -m pip install -e "$BACKEND_DIR"
fi

# Run from DEFLUFF_HOME so pydantic-settings reads $DEFLUFF_HOME/.env.
cd "$DEFLUFF_HOME"

# Auto-reload is opt-in: it watches the repo and would otherwise restart the
# server mid-request (killing long Ollama summaries) whenever a log or debug
# file is written. Set BACKEND_RELOAD=1 for development.
RELOAD_ARGS=()
if [[ "${BACKEND_RELOAD:-0}" == "1" ]]; then
    RELOAD_ARGS=(--reload --reload-dir "$BACKEND_DIR/app")
fi

exec "$BACKEND_DIR/.venv/bin/uvicorn" app.main:app \
    --app-dir "$BACKEND_DIR" \
    ${RELOAD_ARGS[@]+"${RELOAD_ARGS[@]}"} \
    --host 127.0.0.1 \
    --port 8000
