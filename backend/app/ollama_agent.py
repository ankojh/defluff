import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import ollama

from app.config import settings
from app.debug_log import DEBUG_LOG_PATH, write_debug_event
from app.models import (
    Chapter,
    Highlight,
    ContentResponse,
    ConsumptionAnalysis,
    DiscussMessage,
    KnowledgeMatch,
    ResearchDocument,
    ResearchTopic,
)
from app.transcript import caption_for_range, format_transcript_text, resolved_caption_range

logger = logging.getLogger(__name__)


class AnalysisError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChapterAnalysis:
    title: str
    summary: str
    highlights: list[Highlight]


class LocalOllamaConsumptionAgent:
    def __init__(self) -> None:
        self.client = ollama.AsyncClient(host=settings.ollama_host)
        self.last_thinking = ""

    @staticmethod
    def model_name() -> str:
        return settings.ollama_model

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
        prompt = _overall_analysis_prompt(
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
            raw, thinking = await _chat_json(
                self.client,
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
            self.last_thinking += thinking
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

        prompt = _chapter_segmentation_prompt(content)
        logger.info(
            "ollama.chapter_segmentation_request model=%s prompt_chars=%d segments=%d",
            settings.ollama_model,
            len(prompt),
            len(content.segments),
        )
        try:
            raw, thinking = await _chat_json(
                self.client,
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
            self.last_thinking += thinking
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
        prompt = _chapter_analysis_prompt(content, chapter, index, chapter_count)
        logger.info(
            "ollama.chapter_analysis_request model=%s prompt_chars=%d chapter=%d/%d title=%r",
            settings.ollama_model,
            len(prompt),
            index + 1,
            chapter_count,
            chapter.title,
        )
        raw, thinking = await _chat_json(
            self.client,
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
        self.last_thinking += thinking
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

        prompt = _transcript_format_prompt(chapter, highlights)
        logger.info(
            "ollama.transcript_format_request model=%s prompt_chars=%d highlight_count=%d",
            settings.ollama_model,
            len(prompt),
            len(highlights),
        )
        try:
            raw, thinking = await _chat_json(
                self.client,
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
            self.last_thinking += thinking
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


class LocalOllamaResearchPlanner:
    def __init__(self) -> None:
        self.client = ollama.AsyncClient(host=settings.ollama_host)
        self.last_thinking = ""

    async def plan(
        self,
        content: ContentResponse,
        chapters: list[Chapter] | None = None,
        highlights: list[Highlight] | None = None,
        max_topics: int = 6,
    ) -> list[ResearchTopic]:
        prompt = _research_planning_prompt(content, chapters or [], highlights or [], max_topics)
        logger.info(
            "ollama.research_plan_request model=%s host=%s prompt_chars=%d max_topics=%d",
            settings.ollama_model,
            settings.ollama_host,
            len(prompt),
            max_topics,
        )

        raw, thinking = await _chat_json(
            self.client,
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
        self.last_thinking = thinking

        topics = _parse_research_topics(raw, max_topics)
        logger.info(
            "ollama.research_plan_response raw_chars=%d topics=%d queries=%r",
            len(raw),
            len(topics),
            [topic.query for topic in topics],
        )
        return topics


class LocalOllamaDiscussionAgent:
    def __init__(self) -> None:
        self.client = ollama.AsyncClient(host=settings.ollama_host)

    @staticmethod
    def model_name() -> str:
        return settings.ollama_model

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
            options={
                "temperature": 0.4,
                "num_predict": settings.discuss_num_predict,
                "repeat_penalty": 1.2,
                "repeat_last_n": 128,
            },
        )
        async for part in stream:
            content, thinking = _chunk_parts(part)
            if thinking:
                yield ("thinking", thinking)
            if content:
                yield ("answer", content)


def _chapter_segmentation_prompt(content: ContentResponse) -> str:
    payload = {
        "url": content.url,
        "title": content.title,
        "kind": content.kind,
        "language": content.language,
        "transcript": _content_body_for_prompt(content),
    }

    return (
        "Split this timestamped transcript into topic chapters.\n"
        "Use the transcript itself, not YouTube chapter metadata. Start a new chapter when the "
        "topic, goal, argument, demonstration, or discussion focus changes. Keep chapters "
        "sequential and cover the whole transcript without gaps or overlaps: the first chapter "
        "starts at the beginning, each next chapter starts where the previous ends, and the last "
        "chapter ends at the final transcript time. Do not create tiny chapters for greetings, "
        "transitions, sponsorship, or housekeeping unless the content itself is about that topic.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "chapters": [\n'
        "    {\n"
        '      "title": "short topic title",\n'
        '      "summary": "one dense sentence describing the chapter focus",\n'
        '      "start": 0.0,\n'
        '      "end": 180.0,\n'
        '      "timestamp": "00:00",\n'
        '      "end_timestamp": "03:00"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Use timestamp labels present in the transcript. Numeric start/end seconds must match "
        "those labels approximately. Prefer 4 to 10 chapters for a typical long video, fewer for "
        "short focused videos and more only when the discussion genuinely changes often.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _chapter_analysis_prompt(
    content: ContentResponse,
    chapter: Chapter,
    index: int,
    chapter_count: int,
) -> str:
    payload = {
        "content": {
            "url": content.url,
            "title": content.title,
            "kind": content.kind,
            "source": content.source,
            "language": content.language,
        },
        "chapter": {
            "index": index + 1,
            "chapter_count": chapter_count,
            "title": chapter.title,
            "start": chapter.start,
            "end": chapter.end,
            "timestamp": chapter.timestamp,
            "end_timestamp": chapter.end_timestamp,
            "transcript": _caption_for_prompt(content, chapter.start, chapter.end),
        },
    }

    return (
        "Analyze this one transcript chapter for a reader who wants enough detail to understand "
        "the topic without watching the whole span.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "title": "refined short chapter title",\n'
        '  "summary": "3 to 5 dense but readable sentences covering the chapter argument, examples, and takeaways",\n'
        '  "highlights": [\n'
        "    {\n"
        '      "text": "10 to 20 word label for this revisit point, paraphrased",\n'
        '      "summary": "2 to 4 dense sentences explaining the full point in this timestamp range",\n'
        '      "why": "one sentence explaining why this moment is worth revisiting",\n'
        '      "start": 65.0,\n'
        '      "end": 142.0,\n'
        '      "timestamp": "01:05",\n'
        '      "end_timestamp": "02:22"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Highlights must stay inside the chapter range and be sequential. Choose only useful "
        "revisit points: claims, decisions, examples, explanations, warnings, technical details, "
        "or shifts in what the viewer should believe or do. Avoid generic intros, transitions, "
        "or repeated points. Each highlight should cover a coherent section, usually 30 seconds "
        "to 3 minutes. Do not quote the transcript verbatim; paraphrase in your own words.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _overall_analysis_prompt(
    content: ContentResponse,
    knowledge_matches: list[KnowledgeMatch],
    research_documents: list[ResearchDocument],
    chapters: list[Chapter],
    highlights: list[Highlight],
) -> str:
    prior_knowledge = [
        {
            "url": item.url,
            "title": item.title,
            "summary": item.summary,
            "overlap": item.overlap,
        }
        for item in knowledge_matches
    ]
    payload = {
        "content": {
            "url": content.url,
            "title": content.title,
            "kind": content.kind,
            "source": content.source,
            "language": content.language,
            "body": _content_body_for_prompt(content) if not content.segments else None,
            "available_images": _content_images_for_prompt(content),
        },
        "chapters": [
            {
                "title": chapter.title,
                "summary": chapter.summary,
                "timestamp": chapter.timestamp,
                "end_timestamp": chapter.end_timestamp,
            }
            for chapter in chapters
        ],
        "highlights": [
            {
                "text": highlight.text,
                "summary": highlight.summary,
                "why": highlight.why,
                "timestamp": highlight.timestamp,
                "end_timestamp": highlight.end_timestamp,
            }
            for highlight in highlights
        ],
        "research_documents": _research_documents_for_prompt(research_documents),
        "prior_knowledge": prior_knowledge,
    }

    return (
        "Create the overall consumption summary from the already analyzed chapters and highlights.\n"
        "Do not redo chaptering or highlight extraction. Use chapter summaries and highlights as "
        "the primary source, and use research_documents only to clarify, verify, or add context. "
        "Anything already covered by prior_knowledge is known to the reader: compress it to a "
        "one-line mention at most and spend the detail on what is new in this source.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "summary": "3 to 5 dense plain-English sentences, max 900 characters",\n'
        '  "summary_points": ["scannable takeaway point, max 180 characters"],\n'
        '  "tldr": "one or two sentences with the core takeaway",\n'
        '  "reasoning_summary": "brief explanation of what you prioritized and why, max 240 characters",\n'
        '  "reading_flow": ["step-by-step flow item, max 160 characters"],\n'
        '  "context_helpers": ["context helper, max 180 characters"],\n'
        '  "glossary": [\n'
        '    {"term": "jargon or acronym", "explanation": "simple explanation, max 160 characters"}\n'
        "  ],\n"
        '  "visual_aids": [\n'
        "    {\n"
        '      "title": "image or diagram helper",\n'
        '      "explanation": "how this visual helps, max 180 characters",\n'
        '      "image_url": "use an available image URL when relevant, otherwise null",\n'
        '      "image_alt": "available image alt text when relevant, otherwise null",\n'
        '      "suggested_diagram": "diagram description, max 200 characters, otherwise null"\n'
        "    }\n"
        "  ],\n"
        '  "research_context": ["context from research_documents that makes the source easier to understand"],\n'
        '  "research_highlights": [\n'
        "    {\n"
        '      "title": "research document title",\n'
        '      "url": "research document URL",\n'
        '      "point": "important point from that document",\n'
        '      "why_it_matters": "how it changes or clarifies the original content"\n'
        "    }\n"
        "  ],\n"
        '  "deep_dive_questions": ["specific question the reader can pursue next"],\n'
        '  "key_points": ["key takeaway: core concept, method, definition, or actionable value, max 220 characters"],\n'
        '  "novel_points": ["new-to-me point based on prior_knowledge, max 180 characters"],\n'
        '  "already_known": ["item skipped because it is already in prior_knowledge"]\n'
        "}\n"
        "Keep the summary dense enough to understand the topic, not just a teaser. "
        "For key_points, extract the actual key takeaways someone should remember. If the source "
        "is a listicle or lesson such as '7 auth methods you should know', key_points should be "
        "those explicit methods or lessons, in order, with the practical value of each. If the "
        "source teaches a core concept such as transformers in AI, key_points should include the "
        "definition, why it matters, how it is used, and the most important mechanisms or tradeoffs. "
        "Do not fill key_points with generic summary bullets; make them the durable concepts, "
        "definitions, methods, claims, or decisions the viewer should retain. Include 4 to 12 "
        "key_points depending on the source structure; preserve exact counts when the source is "
        "organized around a named number of items. "
        "Use 5 to 10 summary_points when the source is substantial. For visual_aids, only use "
        "image_url values from content.available_images, and include at most 2. For glossary, "
        "include 2 to 6 terms only when jargon or assumed background appears. For research_context, "
        "include 2 to 6 notes. For research_highlights, include 2 to 5 items tied to URLs. "
        "For deep_dive_questions, include 3 to 6 concrete next questions.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _transcript_format_prompt(chapter: Chapter, highlights: list[Highlight]) -> str:
    payload = {
        "chapter": {
            "title": chapter.title,
            "timestamp": chapter.timestamp,
            "end_timestamp": chapter.end_timestamp,
            "raw_transcript": chapter.caption,
        },
        "highlights": [
            {
                "index": index,
                "label": highlight.text,
                "timestamp": highlight.timestamp,
                "end_timestamp": highlight.end_timestamp,
                "raw_transcript": highlight.caption,
            }
            for index, highlight in enumerate(highlights)
        ],
    }

    return (
        "Format these raw caption transcript slices for display in a collapsed transcript panel.\n"
        "Important constraints:\n"
        "- Preserve the spoken content and meaning; do not summarize or add facts.\n"
        "- Fix obvious punctuation, capitalization, spacing, and paragraph breaks.\n"
        "- Use short readable paragraphs.\n"
        "- Use quote marks only when the raw transcript clearly contains quoted speech or a named phrase.\n"
        "- Do not add timestamps, bullet points, headings, speaker names, markdown, or commentary.\n"
        "- Keep each highlight transcript scoped only to its own raw_transcript.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "chapter_transcript": "formatted chapter transcript",\n'
        '  "highlights": [\n'
        "    {\n"
        '      "index": 0,\n'
        '      "transcript": "formatted highlight transcript"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _research_planning_prompt(
    content: ContentResponse,
    chapters: list[Chapter],
    highlights: list[Highlight],
    max_topics: int,
) -> str:
    has_extracted = bool(chapters or highlights)
    payload = {
        "url": content.url,
        "title": content.title,
        "kind": content.kind,
        "source": content.source,
        "chapters": [
            {"title": chapter.title, "summary": chapter.summary}
            for chapter in chapters
        ],
        "highlights": [
            {"text": highlight.text, "summary": highlight.summary, "why": highlight.why}
            for highlight in highlights
        ],
        # Only fall back to the raw body when nothing was extracted (e.g. articles).
        "body": None if has_extracted else _content_body_for_prompt(content),
    }

    return (
        "Choose web research topics for this content.\n"
        "You are given the chapters and highlights already extracted from it. Ground your "
        "research in those: the concrete claims, named entities, jargon, techniques, tools, "
        "and open questions they surface. Only fall back to the body when chapters and "
        "highlights are empty.\n"
        "Do not search the title by itself.\n"
        "Prefer:\n"
        "- main concepts and claims raised in the highlights\n"
        "- domain jargon, acronyms, named techniques, tools, products, laws, standards, or papers mentioned\n"
        "- background context the source assumes but does not explain\n"
        "- controversial limitations, criticism, failure modes, or tradeoffs\n"
        "- related topics that materially change interpretation of the source\n"
        "Avoid vague queries, generic summaries, the URL host, creator names by themselves, "
        "and title-only searches.\n"
        f"Return up to {max_topics} items as exactly this JSON shape:\n"
        "{\n"
        '  "topics": [\n'
        "    {\n"
        '      "query": "search-ready topic query, 4 to 10 words",\n'
        '      "reason": "short rationale for why this search helps consume the source",\n'
        '      "source_terms": ["term from the content that caused this query"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _content_body_for_prompt(content: ContentResponse) -> str:
    if content.segments:
        lines: list[str] = []
        total_chars = 0
        for segment in content.segments:
            timestamp = _timestamp(segment.start)
            line = f"[{timestamp}] {segment.text}"
            total_chars += len(line)
            if total_chars > settings.analysis_max_chars:
                break
            lines.append(line)
        return "\n".join(lines)

    return content.text[: settings.analysis_max_chars]


def _caption_for_prompt(
    content: ContentResponse,
    start: float | None,
    end: float | None,
    max_chars: int | None = None,
) -> str:
    limit = max_chars or settings.analysis_max_chars
    if not content.segments:
        return content.text[:limit]

    lines: list[str] = []
    total_chars = 0
    for segment in content.segments:
        if start is not None and segment.end <= start:
            continue
        if end is not None and segment.start >= end:
            break

        line = f"[{_timestamp(segment.start)}] {segment.text}"
        total_chars += len(line)
        if total_chars > limit:
            break
        lines.append(line)

    return "\n".join(lines)


def _content_end_seconds(content: ContentResponse) -> float | None:
    if not content.segments:
        return None
    return max(segment.end for segment in content.segments)


def _content_images_for_prompt(content: ContentResponse) -> list[dict[str, str | None]]:
    images = []
    for media in content.media[:8]:
        images.append(
            {
                "url": media.url,
                "alt": media.alt,
                "caption": media.caption,
            }
        )
    return images


def _research_documents_for_prompt(
    research_documents: list[ResearchDocument],
) -> list[dict[str, object]]:
    documents = []
    for document in research_documents[: settings.research_max_documents]:
        documents.append(
            {
                "title": document.title,
                "url": document.url,
                "query": document.query,
                "depth": document.depth,
                "parent_url": document.parent_url,
                "body": document.text_excerpt,
                "outbound_links": [
                    {
                        "title": link.title,
                        "url": link.url,
                    }
                    for link in document.outbound_links[:3]
                ],
            }
        )
    return documents


def _timestamp(seconds: float) -> str:
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def timestamp_label(seconds: float) -> str:
    return _timestamp(seconds)


def _timestamp_or_none(value: float | None) -> str | None:
    if value is None:
        return None
    return _timestamp(value)


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
            "timestamp": chapter.timestamp or _timestamp_or_none(start),
            "end_timestamp": chapter.end_timestamp or _timestamp_or_none(end),
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
            "timestamp": highlight.timestamp or _timestamp_or_none(start),
            "end_timestamp": highlight.end_timestamp or _timestamp_or_none(end),
        }
    )


def _parse_analysis(raw: str) -> ConsumptionAnalysis:
    data = _load_ollama_json(raw, purpose="analysis")

    if not isinstance(data, dict):
        raise AnalysisError("Ollama JSON response was not an object")

    data["summary"] = _string_or_default(data.get("summary"), "No new summary.")
    data["tldr"] = _string_or_none(data.get("tldr"))
    data["reasoning_summary"] = _string_or_none(data.get("reasoning_summary"))
    for key in (
        "summary_points",
        "reading_flow",
        "context_helpers",
        "research_context",
        "deep_dive_questions",
        "key_points",
        "novel_points",
        "already_known",
    ):
        data[key] = _string_list(data.get(key))
    data["glossary"] = _term_explanations(data.get("glossary"))
    data["visual_aids"] = _visual_aids(data.get("visual_aids"))
    data["research_highlights"] = _research_highlights(data.get("research_highlights"))

    highlights = data.get("highlights")
    if isinstance(highlights, list):
        data["highlights"] = [
            _highlight_item(item)
            for item in highlights
            if isinstance(item, dict) and _string_or_default(item.get("text"), "")
        ]
    else:
        data["highlights"] = []

    chapters = data.get("chapters")
    if isinstance(chapters, list):
        data["chapters"] = [
            _chapter_item(item)
            for item in chapters
            if isinstance(item, dict) and _string_or_default(item.get("title"), "")
        ]
    else:
        data["chapters"] = []

    return ConsumptionAnalysis.model_validate(data)


def _parse_chapters(raw: str) -> list[Chapter]:
    data = _load_ollama_json(raw, purpose="chapter segmentation")

    if not isinstance(data, dict):
        raise AnalysisError("Ollama chapter JSON response was not an object")

    chapters = data.get("chapters")
    if not isinstance(chapters, list):
        return []

    parsed = [
        Chapter.model_validate(_chapter_item(item))
        for item in chapters
        if isinstance(item, dict) and _string_or_default(item.get("title"), "")
    ]
    return _dedupe_ordered_chapters(parsed)


def _parse_chapter_analysis(raw: str, chapter: Chapter) -> ChapterAnalysis:
    data = _load_ollama_json(raw, purpose="chapter analysis")

    if not isinstance(data, dict):
        raise AnalysisError("Ollama chapter analysis JSON response was not an object")

    highlights = data.get("highlights")
    parsed_highlights = []
    if isinstance(highlights, list):
        parsed_highlights = [
            Highlight.model_validate(_highlight_item(item))
            for item in highlights
            if isinstance(item, dict) and _string_or_default(item.get("text"), "")
        ]

    return ChapterAnalysis(
        title=_string_or_default(data.get("title"), chapter.title),
        summary=_string_or_default(data.get("summary"), chapter.summary),
        highlights=_dedupe_ordered_highlights(parsed_highlights),
    )


def _parse_transcript_format(
    raw: str,
    chapter: Chapter,
    highlights: list[Highlight],
) -> tuple[Chapter, list[Highlight]]:
    data = _load_ollama_json(raw, purpose="transcript formatting")

    if not isinstance(data, dict):
        raise AnalysisError("Ollama transcript formatting JSON response was not an object")

    formatted_chapter = _string_or_none(data.get("chapter_transcript"))
    formatted_by_index: dict[int, str] = {}
    raw_highlights = data.get("highlights")
    if isinstance(raw_highlights, list):
        for item in raw_highlights:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            transcript = _string_or_none(item.get("transcript"))
            if isinstance(index, int) and transcript:
                formatted_by_index[index] = transcript

    return (
        chapter.model_copy(update={"caption": formatted_chapter or chapter.caption}),
        [
            highlight.model_copy(
                update={"caption": formatted_by_index.get(index) or highlight.caption}
            )
            for index, highlight in enumerate(highlights)
        ],
    )


def _dedupe_ordered_chapters(chapters: list[Chapter]) -> list[Chapter]:
    seen: set[tuple[float | None, str]] = set()
    deduped: list[Chapter] = []
    for chapter in sorted(chapters, key=lambda item: (item.start is None, item.start or 0.0)):
        key = (chapter.start, chapter.title.lower())
        if key in seen:
            continue
        deduped.append(chapter)
        seen.add(key)
    return deduped


def _dedupe_ordered_highlights(highlights: list[Highlight]) -> list[Highlight]:
    seen: set[tuple[float | None, str]] = set()
    deduped: list[Highlight] = []
    for highlight in sorted(highlights, key=lambda item: (item.start is None, item.start or 0.0)):
        key = (highlight.start, highlight.text.lower())
        if key in seen:
            continue
        deduped.append(highlight)
        seen.add(key)
    return deduped


def _fallback_chapters(content: ContentResponse) -> list[Chapter]:
    end = _content_end_seconds(content)
    if end is None:
        return []

    return [
        Chapter(
            title=content.title or "Full video",
            summary="The full video is treated as one chapter because automatic segmentation failed.",
            start=0.0,
            end=end,
            timestamp=_timestamp(0.0),
            end_timestamp=_timestamp(end),
        )
    ]


def _parse_research_topics(raw: str, max_topics: int) -> list[ResearchTopic]:
    data = _load_ollama_json(raw, purpose="research topics")

    if not isinstance(data, dict):
        raise AnalysisError("Ollama research topic JSON response was not an object")

    raw_topics = data.get("topics")
    if not isinstance(raw_topics, list):
        return []

    topics: list[ResearchTopic] = []
    seen: set[str] = set()
    for item in raw_topics:
        if not isinstance(item, dict):
            continue

        query = _string_or_default(item.get("query"), "")
        if not query:
            continue

        query = re.sub(r"\s+", " ", query).strip(" \"'")
        key = query.lower()
        if key in seen:
            continue

        topics.append(
            ResearchTopic(
                query=query,
                reason=_string_or_default(item.get("reason"), "Useful context for the source."),
                source_terms=_string_list(item.get("source_terms")),
            )
        )
        seen.add(key)
        if len(topics) >= max_topics:
            break

    return topics


def _chunk_parts(part: object) -> tuple[str | None, str | None]:
    """Extract (content, thinking) from one streamed chat chunk."""
    message = getattr(part, "message", None)
    if message is None and isinstance(part, dict):
        message = part.get("message")
    if message is None:
        return None, None
    if isinstance(message, dict):
        return message.get("content"), message.get("thinking")
    return getattr(message, "content", None), getattr(message, "thinking", None)


async def _chat_json(
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
            options={
                "temperature": temperature,
                "num_predict": num_predict,
                "repeat_penalty": 1.2,
                "repeat_last_n": 128,
            },
        )
        async for part in stream:
            content, thinking = _chunk_parts(part)
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


def _repair_truncated_json(raw: str) -> str | None:
    """Recover the largest valid JSON object from truncated/degenerate output.

    Walks the text tracking string state and the bracket stack, remembers the
    last point where the structure was cleanly closeable (a closing bracket or
    an element-separating comma), then truncates there and appends the closing
    brackets. This salvages everything up to the point gemma went off the rails
    (e.g. a repetition loop in the final array element).
    """
    start = raw.find("{")
    if start == -1:
        return None

    s = raw[start:]
    stack: list[str] = []
    in_string = False
    escape = False
    safe_len = 0
    safe_stack: list[str] = []

    for i, ch in enumerate(s):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack:
                break
            stack.pop()
            safe_len = i + 1
            safe_stack = list(stack)
        elif ch == ",":
            # Everything before this comma is a complete set of elements.
            safe_len = i
            safe_stack = list(stack)

    if safe_len == 0:
        return None

    return s[:safe_len] + "".join(reversed(safe_stack))


def _load_ollama_json(raw: str, purpose: str) -> object:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as first_error:
        candidate: str | None = None
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match is not None:
            candidate = match.group(0)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        repaired = _repair_truncated_json(raw)
        if repaired is not None:
            try:
                data = json.loads(repaired)
                write_debug_event(
                    "ollama.json_repaired",
                    purpose=purpose,
                    raw_chars=len(raw),
                    repaired_chars=len(repaired),
                )
                return data
            except json.JSONDecodeError:
                pass

        _log_malformed_ollama_json(
            raw,
            purpose,
            first_error,
            extracted_candidate=candidate,
        )
        raise AnalysisError(
            f"Ollama returned malformed JSON for {purpose}. Debug log: {DEBUG_LOG_PATH}"
        ) from first_error


def _log_malformed_ollama_json(
    raw: str,
    purpose: str,
    error: json.JSONDecodeError,
    extracted_candidate: str | None = None,
) -> None:
    write_debug_event(
        "ollama.malformed_json",
        purpose=purpose,
        error=str(error),
        line=error.lineno,
        column=error.colno,
        char=error.pos,
        raw=raw,
        extracted_candidate=extracted_candidate,
    )


def _string_or_default(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []

    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _highlight_item(value: dict[str, object]) -> dict[str, object]:
    start = value.get("start") if isinstance(value.get("start"), (int, float)) else None
    end = value.get("end") if isinstance(value.get("end"), (int, float)) else None
    timestamp = value.get("timestamp") if isinstance(value.get("timestamp"), str) else None
    end_timestamp = value.get("end_timestamp") if isinstance(value.get("end_timestamp"), str) else None

    # Fall back to formatting the numeric seconds when the model omits the
    # display strings, so videos always show a start and end time.
    if timestamp is None and start is not None:
        timestamp = _timestamp(float(start))
    if end_timestamp is None and end is not None:
        end_timestamp = _timestamp(float(end))

    return {
        "text": _string_or_default(value.get("text"), ""),
        "why": _string_or_default(value.get("why"), "Worth revisiting."),
        "summary": _string_or_none(value.get("summary")),
        "caption": _string_or_none(value.get("caption")),
        "start": start,
        "end": end,
        "timestamp": timestamp,
        "end_timestamp": end_timestamp,
    }


def _chapter_item(value: dict[str, object]) -> dict[str, object]:
    start = value.get("start") if isinstance(value.get("start"), (int, float)) else None
    end = value.get("end") if isinstance(value.get("end"), (int, float)) else None
    timestamp = value.get("timestamp") if isinstance(value.get("timestamp"), str) else None
    end_timestamp = value.get("end_timestamp") if isinstance(value.get("end_timestamp"), str) else None

    if timestamp is None and start is not None:
        timestamp = _timestamp(float(start))
    if end_timestamp is None and end is not None:
        end_timestamp = _timestamp(float(end))

    return {
        "title": _string_or_default(value.get("title"), ""),
        "summary": _string_or_default(value.get("summary"), ""),
        "caption": _string_or_none(value.get("caption")),
        "start": start,
        "end": end,
        "timestamp": timestamp,
        "end_timestamp": end_timestamp,
    }


def _term_explanations(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    terms: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        term = _string_or_default(item.get("term"), "")
        explanation = _string_or_default(item.get("explanation"), "")
        if term and explanation:
            terms.append({"term": term, "explanation": explanation})

    return terms


def _visual_aids(value: object) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []

    aids: list[dict[str, str | None]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        title = _string_or_default(item.get("title"), "")
        explanation = _string_or_default(item.get("explanation"), "")
        if not title or not explanation:
            continue

        aids.append(
            {
                "title": title,
                "explanation": explanation,
                "image_url": _string_or_none(item.get("image_url")),
                "image_alt": _string_or_none(item.get("image_alt")),
                "suggested_diagram": _string_or_none(item.get("suggested_diagram")),
            }
        )

    return aids


def _research_highlights(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    highlights: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        title = _string_or_default(item.get("title"), "")
        url = _string_or_default(item.get("url"), "")
        point = _string_or_default(item.get("point"), "")
        why_it_matters = _string_or_default(item.get("why_it_matters"), "")
        if title and url and point and why_it_matters:
            highlights.append(
                {
                    "title": title,
                    "url": url,
                    "point": point,
                    "why_it_matters": why_it_matters,
                }
            )

    return highlights
