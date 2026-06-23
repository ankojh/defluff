#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/.logs"
OLLAMA_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8000}"

mkdir -p "$LOG_DIR"

is_up() {
    local url="$1"
    curl -fsS "$url" >/dev/null 2>&1
}

wait_for() {
    local name="$1"
    local url="$2"
    local attempts="${3:-30}"

    for _ in $(seq 1 "$attempts"); do
        if is_up "$url"; then
            echo "$name is ready: $url"
            return 0
        fi
        sleep 1
    done

    echo "$name did not become ready: $url" >&2
    return 1
}

start_ollama() {
    if is_up "$OLLAMA_URL/api/tags"; then
        echo "Ollama is already running: $OLLAMA_URL"
        return 0
    fi

    if [[ -d /Applications/Ollama.app ]]; then
        open -a Ollama
    elif command -v ollama >/dev/null 2>&1; then
        nohup ollama serve >"$LOG_DIR/ollama.out.log" 2>"$LOG_DIR/ollama.err.log" &
    else
        echo "Ollama was not found. Install Ollama or start it manually." >&2
        return 1
    fi

    wait_for "Ollama" "$OLLAMA_URL/api/tags" 45
}

start_backend() {
    "$ROOT_DIR/scripts/start-backend-service.sh"
    wait_for "Defluff backend" "$BACKEND_URL/health" 45
}

open_app() {
    local app_path
    app_path="$("$ROOT_DIR/scripts/build-macos-app.sh")"
    open -n "$app_path"
    echo "Opened Defluff: $app_path"
}

start_ollama
start_backend
open_app
