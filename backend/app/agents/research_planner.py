import logging

from app.agents.base import BaseLLMAgent
from app.agents.parsing import _parse_research_topics
from app.agents.prompts.research import research_planning_prompt
from app.core.config import settings
from app.schemas import Chapter, ContentResponse, Highlight, ResearchTopic

logger = logging.getLogger(__name__)


class LocalOllamaResearchPlanner(BaseLLMAgent):
    async def plan(
        self,
        content: ContentResponse,
        chapters: list[Chapter] | None = None,
        highlights: list[Highlight] | None = None,
        max_topics: int = 6,
    ) -> list[ResearchTopic]:
        prompt = research_planning_prompt(content, chapters or [], highlights or [], max_topics)
        logger.info(
            "ollama.research_plan_request model=%s host=%s prompt_chars=%d max_topics=%d",
            settings.ollama_model,
            settings.ollama_host,
            len(prompt),
            max_topics,
        )

        raw, _ = await self.chat_json(
            system=(
                "You are Defluff's local research-planning agent. "
                "You identify what web searches would best explain, verify, "
                "or contextualize consumed content. Return strict JSON only."
            ),
            prompt=prompt,
            num_predict=settings.research_num_predict,
            temperature=0.15,
            purpose="research planning",
            think=False,
        )

        topics = _parse_research_topics(raw, max_topics)
        logger.info(
            "ollama.research_plan_response raw_chars=%d topics=%d queries=%r",
            len(raw),
            len(topics),
            [topic.query for topic in topics],
        )
        return topics
