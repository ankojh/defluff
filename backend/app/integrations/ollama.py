"""Low-level Ollama transport: client creation, streaming chunk parsing, warmup.

Agent-level concerns (prompt building, JSON parsing, the AnalysisError-raising
``complete_json`` wrapper) live in ``app.agents``; this module stays a thin
transport layer with no dependency on the agent package.
"""

import logging

import ollama

from app.core.config import settings
from app.core.debug_log import write_debug_event

logger = logging.getLogger(__name__)


def make_client() -> ollama.AsyncClient:
    return ollama.AsyncClient(host=settings.ollama_host)


async def preload_model() -> None:
    """Warm the model into memory without generating any tokens.

    Called at the start of a consume so the model loads in parallel with content
    fetching/transcription; by the time the first real Ollama call runs, the
    model is resident and the request is instant even though it unloads when
    idle to save RAM. Best-effort: failures are logged, never raised.
    """
    client = make_client()
    try:
        await client.generate(
            model=settings.ollama_model,
            prompt="",
            keep_alive=settings.ollama_keep_alive_value,
        )
        write_debug_event("ollama.preloaded", model=settings.ollama_model)
    except Exception as error:  # noqa: BLE001 - preload is best-effort
        logger.info("ollama.preload_failed error=%s", error)


def chunk_parts(part: object) -> tuple[str | None, str | None]:
    """Extract (content, thinking) from one streamed chat chunk."""
    message = getattr(part, "message", None)
    if message is None and isinstance(part, dict):
        message = part.get("message")
    if message is None:
        return None, None
    if isinstance(message, dict):
        return message.get("content"), message.get("thinking")
    return getattr(message, "content", None), getattr(message, "thinking", None)
