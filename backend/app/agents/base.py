"""Shared agent plumbing.

``BaseLLMAgent`` gives every Defluff agent an Ollama client, the model name, and
a ``chat_json`` helper that handles streaming, thinking capture, and JSON
assembly. Subclasses add prompt builders (``app.agents.prompts``) and parsers
(``app.agents.parsing``); for multi-step agentic loops, override ``run`` and call
``self.chat_json`` repeatedly (perceive -> prompt -> parse -> act).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

import ollama

from app.agents.errors import AnalysisError
from app.core.config import settings
from app.integrations.ollama import chunk_parts, make_client


async def complete_json(
    client: ollama.AsyncClient,
    *,
    system: str,
    prompt: str,
    num_predict: int,
    temperature: float,
    purpose: str,
    think: bool = True,
    on_thinking: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, str]:
    """Stream an Ollama chat, returning (json_content, thinking).

    When ``think`` is set, gemma's reasoning is streamed to ``on_thinking``
    (throttled) so the UI can show it live; disabling it keeps the JSON-only
    steps fast. A repetition penalty discourages the degenerate "x, x, x, ..."
    loops that otherwise truncate and corrupt the JSON answer.
    """
    content_parts: list[str] = []
    thinking_parts: list[str] = []

    async def _run() -> None:
        last_emit = 0.0
        stream = await client.chat(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            format="json",
            think=think,
            stream=True,
            keep_alive=settings.ollama_keep_alive_value,
            options={
                "temperature": temperature,
                "num_predict": num_predict,
                "repeat_penalty": 1.2,
                "repeat_last_n": 128,
            },
        )
        async for part in stream:
            content, thinking = chunk_parts(part)
            if thinking:
                thinking_parts.append(thinking)
                if on_thinking is not None:
                    now = time.monotonic()
                    if now - last_emit > 0.15:
                        last_emit = now
                        await on_thinking("".join(thinking_parts))
            if content:
                content_parts.append(content)
        if on_thinking is not None and thinking_parts:
            await on_thinking("".join(thinking_parts))

    try:
        await asyncio.wait_for(_run(), timeout=settings.analysis_timeout_seconds)
    except asyncio.TimeoutError as error:
        raise AnalysisError(f"Ollama {purpose} timed out") from error
    except Exception as error:
        raise AnalysisError(f"Ollama {purpose} failed: {error}") from error

    raw = "".join(content_parts)
    thinking = "".join(thinking_parts)
    if not raw.strip():
        raise AnalysisError(f"Ollama returned an empty {purpose} response")

    return raw, thinking


class BaseLLMAgent:
    """Base class for local Ollama agents."""

    def __init__(self) -> None:
        self.client = make_client()
        self.last_thinking = ""

    @staticmethod
    def model_name() -> str:
        return settings.ollama_model

    async def chat_json(
        self,
        *,
        system: str,
        prompt: str,
        num_predict: int,
        temperature: float,
        purpose: str,
        think: bool = False,
        on_thinking: Callable[[str], Awaitable[None]] | None = None,
    ) -> tuple[str, str]:
        """Run one JSON chat turn, accumulating streamed thinking on the agent."""
        raw, thinking = await complete_json(
            self.client,
            system=system,
            prompt=prompt,
            num_predict=num_predict,
            temperature=temperature,
            purpose=purpose,
            think=think,
            on_thinking=on_thinking,
        )
        self.last_thinking += thinking
        return raw, thinking

    async def run(self, *args, **kwargs):
        """Entry point for multi-step (loop-based) agents. Override in subclasses."""
        raise NotImplementedError
