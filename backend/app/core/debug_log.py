from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

# This module lives at app/core/debug_log.py, so the repo root (holding .logs/)
# is four parents up.
ROOT_DIR = Path(__file__).resolve().parents[3]
LOG_DIR = ROOT_DIR / ".logs"
DEBUG_LOG_PATH = LOG_DIR / "debug-session.log"
MAX_FIELD_CHARS = 30000


def reset_debug_log() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_LOG_PATH.write_text("", encoding="utf-8")


def write_debug_event(event: str, **fields: Any) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "time": datetime.now(UTC).isoformat(),
        "event": event,
        **{key: _debug_value(value) for key, value in fields.items()},
    }
    with DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def _debug_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_FIELD_CHARS:
        return {
            "truncated": True,
            "chars": len(value),
            "head": value[:MAX_FIELD_CHARS],
        }

    if isinstance(value, list):
        return [_debug_value(item) for item in value]

    if isinstance(value, dict):
        return {key: _debug_value(item) for key, item in value.items()}

    return value
