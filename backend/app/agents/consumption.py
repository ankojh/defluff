import logging
from collections.abc import Awaitable, Callable

from app.agents.base import BaseLLMAgent
from app.agents.errors import AnalysisError
from app.agents.parsing import (
    ChapterAnalysis,
    _parse_analysis,
    _parse_chapter_analysis,
    _parse_chapters,
    _parse_text_segments,
    _parse_transcript_format,
)
from app.agents.prompts.consumption import (
    chapter_analysis_prompt,
    chapter_segmentation_prompt,
    overall_analysis_prompt,
    text_segmentation_prompt,
    transcript_format_prompt,
)
from app.agents.prompts.inputs import content_end_seconds
from app.content.transcript import (
    caption_for_range,
    format_transcript_text,
    resolved_caption_range,
)
from app.core.config import settings
from app.schemas import (
    Chapter,
    ConsumptionAnalysis,
    ContentResponse,
    Highlight,
    KnowledgeMatch,
    ResearchDocument,
)
from app.utils.timestamps import format_timestamp, format_timestamp_or_none

logger = logging.getLogger(__name__)


class LocalOllamaConsumptionAgent(BaseLLMAgent):
    async def segment_and_highlight(
        self,
        content: ContentResponse,
        on_chapter: Callable[[Chapter], Awaitable[None]] | None = None,
        on_highlight: Callable[[Highlight], Awaitable[None]] | None = None,
    ) -> tuple[list[Chapter], list[Highlight]]:
        """Phase one: split into chapters and pull per-chapter highlights.

        This runs before web research so the planner can search using the
        concrete claims and entities these surface. Each chapter and highlight
        is streamed as soon as it is ready.
        """
        # Sources without a timeline (articles, PDFs) have no transcript to
        # segment, so split the text instead and pull untimed highlights.
        if not content.segments:
            return await self._segment_and_highlight_text(content, on_chapter, on_highlight)

        chapters = await self._chapters_for_content(content)
        chapter_highlights: list[Highlight] = []
        enriched_chapters: list[Chapter] = []

        for index, chapter in enumerate(chapters):
            try:
                chapter_analysis = await self._analyze_chapter(content, chapter, index, len(chapters))
            except AnalysisError as error:
                logger.info(
                    "ollama.chapter_analysis_failed chapter=%d/%d error=%s",
                    index + 1,
                    len(chapters),
                    error,
                )
                chapter_analysis = ChapterAnalysis(
                    title=chapter.title,
                    summary=chapter.summary,
                    highlights=[],
                )
            enriched_chapter = chapter.model_copy(
                update={
                    "title": chapter_analysis.title or chapter.title,
                    "summary": chapter_analysis.summary or chapter.summary,
                }
            )
            enriched_highlights = [
                _enrich_highlight_transcript(content, highlight)
                for highlight in chapter_analysis.highlights
            ]
            enriched_chapter, enriched_highlights = await self._format_transcript_bundle(
                enriched_chapter,
                enriched_highlights,
            )

            enriched_chapters.append(enriched_chapter)
            if on_chapter is not None:
                await on_chapter(enriched_chapter)

            for highlight in enriched_highlights:
                chapter_highlights.append(highlight)
                if on_highlight is not None:
                    await on_highlight(highlight)

        return enriched_chapters, chapter_highlights

    async def _segment_and_highlight_text(
        self,
        content: ContentResponse,
        on_chapter: Callable[[Chapter], Awaitable[None]] | None,
        on_highlight: Callable[[Highlight], Awaitable[None]] | None,
    ) -> tuple[list[Chapter], list[Highlight]]:
        """Phase one for sources without a timeline (articles, PDFs).

        Splits the body into sequential chapters and pulls revisit highlights in
        a single call. The results carry no timestamps, so they render in the UI
        without time badges.
        """
        prompt = text_segmentation_prompt(content)
        logger.info(
            "ollama.text_segmentation_request model=%s prompt_chars=%d url=%s",
            settings.ollama_model,
            len(prompt),
            content.url,
        )
        try:
            raw, _ = await self.chat_json(
                system=(
                    "You split written documents into sequential sections and pick the "
                    "points worth revisiting. Return strict JSON only."
                ),
                prompt=prompt,
                num_predict=settings.analysis_num_predict,
                temperature=0.15,
                purpose="text segmentation",
                think=False,
            )
            chapters, highlights = _parse_text_segments(raw)
        except AnalysisError as error:
            logger.info("ollama.text_segmentation_failed url=%s error=%s", content.url, error)
            return [], []

        logger.info(
            "ollama.text_segments_ready url=%s chapters=%d highlights=%d",
            content.url,
            len(chapters),
            len(highlights),
        )
        for chapter in chapters:
            if on_chapter is not None:
                await on_chapter(chapter)
        for highlight in highlights:
            if on_highlight is not None:
                await on_highlight(highlight)
        return chapters, highlights

    async def summarize(
        self,
        content: ContentResponse,
        knowledge_matches: list[KnowledgeMatch],
        research_documents: list[ResearchDocument] | None,
        chapters: list[Chapter],
        highlights: list[Highlight],
    ) -> ConsumptionAnalysis:
        """Phase two: the overall summary, with researched context folded in."""
        research_documents = research_documents or []
        prompt = overall_analysis_prompt(
            content,
            knowledge_matches,
            research_documents,
            chapters,
            highlights,
        )
        logger.info(
            "ollama.analysis_request model=%s host=%s prompt_chars=%d prior_matches=%d research_documents=%d chapters=%d highlights=%d",
            settings.ollama_model,
            settings.ollama_host,
            len(prompt),
            len(knowledge_matches),
            len(research_documents),
            len(chapters),
            len(highlights),
        )

        analysis: ConsumptionAnalysis | None = None
        last_error: Exception | None = None
        raw = ""
        for attempt in range(2):
            raw, _ = await self.chat_json(
                system=(
                    "You are Defluff's local consumption agent. "
                    "You summarize only useful information, suppress things already "
                    "known from local history, and return strict JSON only."
                ),
                prompt=prompt,
                num_predict=settings.analysis_num_predict,
                temperature=0.2,
                purpose="analysis",
                think=False,
            )
            try:
                analysis = _parse_analysis(raw)
                analysis = analysis.model_copy(
                    update={
                        "chapters": chapters,
                        "highlights": highlights,
                    }
                )
                break
            except AnalysisError as error:
                last_error = error
                logger.info("ollama.analysis_retry attempt=%d error=%s", attempt, error)

        if analysis is None:
            raise last_error or AnalysisError("Ollama analysis failed")

        logger.info(
            "ollama.analysis_response raw_chars=%d key_points=%d novel_points=%d already_known=%d highlights=%d thinking_chars=%d",
            len(raw),
            len(analysis.key_points),
            len(analysis.novel_points),
            len(analysis.already_known),
            len(analysis.highlights),
            len(self.last_thinking),
        )
        return analysis

    async def _chapters_for_content(self, content: ContentResponse) -> list[Chapter]:
        if not content.segments:
            return []

        prompt = chapter_segmentation_prompt(content)
        logger.info(
            "ollama.chapter_segmentation_request model=%s prompt_chars=%d segments=%d",
            settings.ollama_model,
            len(prompt),
            len(content.segments),
        )
        try:
            raw, _ = await self.chat_json(
                system=(
                    "You split timestamped transcripts into sequential topic chapters. "
                    "Return strict JSON only."
                ),
                prompt=prompt,
                num_predict=settings.analysis_num_predict,
                temperature=0.1,
                purpose="chapter segmentation",
                think=False,
            )
            chapters = _parse_chapters(raw)
            if chapters:
                logger.info("ollama.chapter_segmentation_response chapters=%d", len(chapters))
                return chapters
        except AnalysisError as error:
            logger.info("ollama.chapter_segmentation_failed error=%s", error)

        return _fallback_chapters(content)

    async def _analyze_chapter(
        self,
        content: ContentResponse,
        chapter: Chapter,
        index: int,
        chapter_count: int,
    ) -> ChapterAnalysis:
        prompt = chapter_analysis_prompt(content, chapter, index, chapter_count)
        logger.info(
            "ollama.chapter_analysis_request model=%s prompt_chars=%d chapter=%d/%d title=%r",
            settings.ollama_model,
            len(prompt),
            index + 1,
            chapter_count,
            chapter.title,
        )
        raw, _ = await self.chat_json(
            system=(
                "You summarize one transcript chapter and pick its best revisit points. "
                "Return strict JSON only."
            ),
            prompt=prompt,
            num_predict=settings.analysis_num_predict,
            temperature=0.15,
            purpose="chapter analysis",
            think=False,
        )
        analyzed = _parse_chapter_analysis(raw, chapter)
        logger.info(
            "ollama.chapter_analysis_response chapter=%d/%d highlights=%d",
            index + 1,
            chapter_count,
            len(analyzed.highlights),
        )
        return analyzed

    async def _format_transcript_bundle(
        self,
        chapter: Chapter,
        highlights: list[Highlight],
    ) -> tuple[Chapter, list[Highlight]]:
        fallback_chapter = chapter.model_copy(
            update={"caption": format_transcript_text(chapter.caption)}
        )
        fallback_highlights = [
            highlight.model_copy(update={"caption": format_transcript_text(highlight.caption)})
            for highlight in highlights
        ]

        raw_inputs = [chapter.caption or "", *[highlight.caption or "" for highlight in highlights]]
        total_chars = sum(len(item) for item in raw_inputs)
        if total_chars == 0 or total_chars > 12000:
            return fallback_chapter, fallback_highlights

        prompt = transcript_format_prompt(chapter, highlights)
        logger.info(
            "ollama.transcript_format_request model=%s prompt_chars=%d highlight_count=%d",
            settings.ollama_model,
            len(prompt),
            len(highlights),
        )
        try:
            raw, _ = await self.chat_json(
                system=(
                    "You format raw caption transcript text for readability. "
                    "Preserve meaning, do not summarize, and return strict JSON only."
                ),
                prompt=prompt,
                num_predict=settings.analysis_num_predict,
                temperature=0.05,
                purpose="transcript formatting",
                think=False,
            )
            formatted_chapter, formatted_highlights = _parse_transcript_format(
                raw,
                fallback_chapter,
                fallback_highlights,
            )
            logger.info(
                "ollama.transcript_format_response chapter_chars=%d highlight_count=%d",
                len(formatted_chapter.caption or ""),
                len(formatted_highlights),
            )
            return formatted_chapter, formatted_highlights
        except AnalysisError as error:
            logger.info("ollama.transcript_format_failed error=%s", error)
            return fallback_chapter, fallback_highlights


def _enrich_chapter_transcript(content: ContentResponse, chapter: Chapter) -> Chapter:
    resolved = resolved_caption_range(
        content.segments,
        chapter.start,
        chapter.end,
        chapter.timestamp,
        chapter.end_timestamp,
    )
    start, end = resolved if resolved is not None else (chapter.start, chapter.end)
    return chapter.model_copy(
        update={
            "caption": caption_for_range(
                content.segments,
                start,
                end,
                chapter.timestamp,
                chapter.end_timestamp,
            ),
            "start": start,
            "end": end,
            "timestamp": chapter.timestamp or format_timestamp_or_none(start),
            "end_timestamp": chapter.end_timestamp or format_timestamp_or_none(end),
        }
    )


def _enrich_highlight_transcript(content: ContentResponse, highlight: Highlight) -> Highlight:
    resolved = resolved_caption_range(
        content.segments,
        highlight.start,
        highlight.end,
        highlight.timestamp,
        highlight.end_timestamp,
    )
    start, end = resolved if resolved is not None else (highlight.start, highlight.end)
    return highlight.model_copy(
        update={
            "caption": caption_for_range(
                content.segments,
                start,
                end,
                highlight.timestamp,
                highlight.end_timestamp,
            ),
            "start": start,
            "end": end,
            "timestamp": highlight.timestamp or format_timestamp_or_none(start),
            "end_timestamp": highlight.end_timestamp or format_timestamp_or_none(end),
        }
    )


def _fallback_chapters(content: ContentResponse) -> list[Chapter]:
    end = content_end_seconds(content)
    if end is None:
        return []

    return [
        Chapter(
            title=content.title or "Full video",
            summary="The full video is treated as one chapter because automatic segmentation failed.",
            start=0.0,
            end=end,
            timestamp=format_timestamp(0.0),
            end_timestamp=format_timestamp(end),
        )
    ]
