import logging
from collections.abc import AsyncIterator

from app.agents.base import BaseLLMAgent
from app.core.config import settings
from app.integrations.ollama import chunk_parts
from app.schemas import DiscussMessage

logger = logging.getLogger(__name__)


class LocalOllamaDiscussionAgent(BaseLLMAgent):
    async def discuss(
        self,
        question: str,
        context: str,
        title: str | None,
        history: list[DiscussMessage],
    ) -> AsyncIterator[tuple[str, str]]:
        """Stream a follow-up discussion as ("thinking" | "answer", delta) pairs."""
        system = (
            "You are Defluff's discussion assistant. The user just consumed the content "
            "below and wants to discuss it. Answer clearly and concisely, using the content "
            "as the primary source and your general knowledge to fill gaps without drifting "
            "off topic. Prefer short paragraphs and bullet points."
        )
        context_block = (
            f"TITLE: {title or 'Untitled'}\n\n"
            f"CONTENT:\n{context[: settings.analysis_max_chars]}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": context_block},
            {"role": "assistant", "content": "Understood — ask me anything about it."},
        ]
        for message in history:
            role = message.role if message.role in ("user", "assistant") else "user"
            messages.append({"role": role, "content": message.content})
        messages.append({"role": "user", "content": question})

        logger.info(
            "ollama.discuss_request model=%s context_chars=%d history=%d",
            settings.ollama_model,
            len(context_block),
            len(history),
        )

        stream = await self.client.chat(
            model=settings.ollama_model,
            messages=messages,
            think=True,
            stream=True,
            keep_alive=settings.ollama_keep_alive_value,
            options={
                "temperature": 0.4,
                "num_predict": settings.discuss_num_predict,
                "repeat_penalty": 1.2,
                "repeat_last_n": 128,
            },
        )
        async for part in stream:
            content, thinking = chunk_parts(part)
            if thinking:
                yield ("thinking", thinking)
            if content:
                yield ("answer", content)
