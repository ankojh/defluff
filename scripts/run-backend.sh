#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x /opt/homebrew/bin/python3.12 ]]; then
        PYTHON_BIN="/opt/homebrew/bin/python3.12"
    else
        PYTHON_BIN="python3.12"
    fi
fi

export DATABASE_URL="${DATABASE_URL:-postgresql://defluff:defluff@127.0.0.1:5432/defluff}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-gemma4:26B}"
export SEARCH_PROVIDER="${SEARCH_PROVIDER:-duckduckgo}"
export GOOGLE_SEARCH_API_KEY="${GOOGLE_SEARCH_API_KEY:-}"
export GOOGLE_SEARCH_ENGINE_ID="${GOOGLE_SEARCH_ENGINE_ID:-}"
export HF_HOME="${HF_HOME:-$ROOT_DIR/.cache/huggingface}"
export WHISPER_MODEL="${WHISPER_MODEL:-small}"
export WHISPER_DEVICE="${WHISPER_DEVICE:-auto}"
export WHISPER_COMPUTE_TYPE="${WHISPER_COMPUTE_TYPE:-default}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "$PYTHON_BIN was not found. Install Python 3.12 or set PYTHON_BIN."
    exit 1
fi

if [[ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]]; then
    "$PYTHON_BIN" -m venv "$BACKEND_DIR/.venv"
    "$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip
    "$BACKEND_DIR/.venv/bin/python" -m pip install -e "$BACKEND_DIR[dev]"
fi

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
