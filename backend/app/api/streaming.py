"""Shared NDJSON streaming helpers for the consume and discuss endpoints."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any


def to_ndjson(payload: Any) -> str:
    """Serialize one event as a newline-delimited JSON line."""
    return json.dumps(payload) + "\n"


async def stream_from_queue(
    worker: Callable[[asyncio.Queue], Awaitable[None]],
    *,
    serialize: Callable[[Any], str],
    heartbeat: Callable[[], Any] | None = None,
    heartbeat_seconds: float = 20.0,
) -> AsyncIterator[str]:
    """Run ``worker`` (which pushes events onto a queue) and stream them out.

    The worker is responsible for pushing events; this helper appends the
    sentinel ``None`` when the worker finishes and cancels it if the client
    disconnects mid-stream.
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def runner() -> None:
        try:
            await worker(queue)
        finally:
            await queue.put(None)

    task = asyncio.create_task(runner())
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
            except asyncio.TimeoutError:
                if heartbeat is not None:
                    yield serialize(heartbeat())
                continue
            if event is None:
                break
            yield serialize(event)
    finally:
        if not task.done():
            task.cancel()
