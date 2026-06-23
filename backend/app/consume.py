import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from starlette.concurrency import run_in_threadpool

from app.content import get_content_for_url
from app.knowledge import find_related_knowledge
from app.models import (
    AgentTrace,
    Chapter,
    ConsumeStreamEvent,
    ConsumeResponse,
    ConsumptionAnalysis,
    ContentResponse,
    Highlight,
    ResearchResult,
    ResearchTopic,
)
from app.ollama_agent import (
    LocalOllamaConsumptionAgent,
    LocalOllamaResearchPlanner,
    preload_model,
    timestamp_label,
)
from app.research import (
    fetch_research_documents,
    fallback_research_topics_for_content,
    research_content,
    research_provider_description,
)
from app.transcript import caption_for_range, resolved_caption_range

T = TypeVar("T")
logger = logging.getLogger(__name__)
ProgressCallback = Callable[[AgentTrace], Awaitable[None]]
AnalysisEventCallback = Callable[[ConsumeStreamEvent], Awaitable[None]]

_THINKING_PREVIEW_CHARS = 1600

# Strong references to in-flight model-warmup tasks, so they aren't garbage
# collected before they finish (asyncio only keeps weak references).
_warmup_tasks: set[asyncio.Task] = set()


def _thinking_detail(thinking: str | None) -> str | None:
    """Format gemma's chain-of-thought for display in an agent trace."""
    if not thinking:
        return None
    text = " ".join(thinking.split())
    if len(text) > _THINKING_PREVIEW_CHARS:
        text = text[:_THINKING_PREVIEW_CHARS].rstrip() + "…"
    return f"💭 Thinking: {text}"


async def consume_url(
    url: str,
    language: str = "en",
    remember: bool = True,
    research: bool = True,
    progress: ProgressCallback | None = None,
    analysis_progress: AnalysisEventCallback | None = None,
    analyze: bool = True,
) -> ConsumeResponse:
    logger.info("consume.start url=%s language=%s", url, language)
    # Warm the model into memory while we fetch and extract content. Content
    # fetching/transcription takes seconds (or longer for video), which hides the
    # model load so the first Ollama call is instant even though the model
    # unloads when idle to save RAM.
    if analyze:
        warmup = asyncio.create_task(preload_model())
        _warmup_tasks.add(warmup)  # hold a strong ref so it isn't GC'd mid-flight
        warmup.add_done_callback(_warmup_tasks.discard)
    await _emit(
        progress,
        AgentTrace(
            name="Content",
            status="running",
            summary="Fetching and extracting content.",
            details=[url],
        ),
    )
    content = await run_in_threadpool(get_content_for_url, url, language)
    logger.info(
        "consume.content_ready url=%s kind=%s source=%s chars=%d segments=%d",
        url,
        content.kind,
        content.source,
        len(content.text),
        len(content.segments),
    )
    await _emit(
        progress,
        AgentTrace(
            name="Content",
            status="complete",
            summary=f"{content.kind.value.title()} extracted from {content.source}.",
            details=[
                f"{len(content.text):,} text characters",
                f"{len(content.segments):,} timestamped segments",
                f"{len(content.media):,} content images",
            ],
        ),
    )
    await _emit_event(analysis_progress, ConsumeStreamEvent(type="content", content=content))

    await _emit(
        progress,
        AgentTrace(
            name="Local Knowledge",
            status="running",
            summary="Checking previously consumed content.",
        ),
    )
    knowledge_task = asyncio.create_task(find_related_knowledge(content))

    # Phase 1 — chapters and highlights first, so research can be planned from the
    # concrete points they surface (and so they stream to the UI immediately).
    analysis_agent: LocalOllamaConsumptionAgent | None = None
    chapters: list[Chapter] = []
    highlights: list[Highlight] = []
    if analyze:
        analysis_agent = LocalOllamaConsumptionAgent()
        logger.info("consume.analysis_started url=%s", url)
        await _emit(
            progress,
            AgentTrace(
                name="Ollama Summary",
                status="running",
                summary=f"Reading the source: building chapters and highlights with {LocalOllamaConsumptionAgent.model_name()}.",
            ),
        )

        async def emit_chapter(chapter: Chapter) -> None:
            await _emit_event(analysis_progress, ConsumeStreamEvent(type="chapter", chapter=chapter))

        async def emit_highlight(highlight: Highlight) -> None:
            await _emit_event(
                analysis_progress,
                ConsumeStreamEvent(type="highlight", highlight=highlight),
            )

        chapters, highlights = await analysis_agent.segment_and_highlight(
            content,
            on_chapter=emit_chapter,
            on_highlight=emit_highlight,
        )
        logger.info(
            "consume.segments_ready url=%s chapters=%d highlights=%d",
            url,
            len(chapters),
            len(highlights),
        )

    # Phase 2 — plan research from the extracted chapters/highlights, then search.
    research_topics = await _plan_research_topics(
        content,
        research,
        progress,
        chapters=chapters,
        highlights=highlights,
    )
    research_task = (
        asyncio.create_task(research_content(content, research_topics, progress=progress))
        if research
        else _completed_task([])
    )
    logger.info("consume.research_%s url=%s", "started" if research else "skipped", url)

    knowledge_matches = await knowledge_task
    logger.info("consume.knowledge_matches url=%s count=%d", url, len(knowledge_matches))
    await _emit(
        progress,
        AgentTrace(
            name="Local Knowledge",
            status="complete",
            summary=f"{len(knowledge_matches)} related consumed items found.",
            details=[
                match.title or match.url
                for match in knowledge_matches[:3]
            ],
        ),
    )

    research_results = await research_task
    logger.info("consume.research_ready url=%s count=%d", url, len(research_results))
    research_documents = (
        await fetch_research_documents(research_results, progress=progress)
        if research
        else []
    )
    logger.info("consume.research_documents_ready url=%s count=%d", url, len(research_documents))
    await _emit(
        progress,
        AgentTrace(
            name="Research",
            status="complete" if research else "skipped",
            summary=(
                f"{len(research_results)} web results via {_research_sources(research_results)}."
                if research
                else "Web research disabled for this request."
            ),
            details=[
                *[f'Searched: "{topic.query}" - {topic.reason}' for topic in research_topics],
                f"Read {len(research_documents)} linked page(s)",
                *[
                    f"Found: {result.title}"
                    for result in research_results[:3]
                ],
            ],
        ),
    )

    # Phase 3 — the overall summary, now with researched context folded in.
    if analyze and analysis_agent is not None:
        await _emit(
            progress,
            AgentTrace(
                name="Ollama Summary",
                status="running",
                summary=f"Summarizing with source plus researched context using {LocalOllamaConsumptionAgent.model_name()}.",
                details=[
                    f"{len(knowledge_matches)} prior knowledge match(es) provided.",
                    f"{len(research_documents)} research document(s) provided.",
                ],
            ),
        )
        analysis = await analysis_agent.summarize(
            content,
            knowledge_matches,
            research_documents,
            chapters,
            highlights,
        )
        analysis = _enrich_timed_analysis(content, analysis)
        logger.info(
            "consume.analysis_ready url=%s summary_chars=%d key_points=%d highlights=%d chapters=%d research_highlights=%d",
            url,
            len(analysis.summary),
            len(analysis.key_points),
            len(analysis.highlights),
            len(analysis.chapters),
            len(analysis.research_highlights),
        )
        await _emit(
            progress,
            AgentTrace(
                name="Ollama Summary",
                status="complete",
                summary=f"Analyzed locally with {LocalOllamaConsumptionAgent.model_name()}.",
                details=[
                    detail
                    for detail in (
                        _thinking_detail(analysis_agent.last_thinking),
                        analysis.reasoning_summary,
                        f"{len(analysis.reading_flow)} flow steps",
                        f"{len(analysis.context_helpers)} context helpers",
                        f"{len(analysis.glossary)} terms explained",
                        f"{len(analysis.visual_aids)} visual aids",
                        f"{len(analysis.research_context)} research context notes",
                        f"{len(analysis.research_highlights)} research highlights",
                        f"{len(analysis.deep_dive_questions)} deep-dive prompts",
                        f"{len(analysis.key_points)} key points",
                        f"{len(analysis.highlights)} highlights",
                        f"{len(analysis.chapters)} chapters",
                    )
                    if detail
                ],
            ),
        )
        await _emit_event(
            analysis_progress,
            ConsumeStreamEvent(
                type="analysis",
                analysis=analysis.model_copy(update={"highlights": [], "chapters": []}),
            ),
        )
    else:
        analysis = ConsumptionAnalysis(summary="")
        logger.info("consume.analysis_skipped url=%s", url)

    # Knowledge is no longer stored automatically — the user explicitly marks
    # individual chapters/highlights as learned via /api/knowledge/learn.
    logger.info("consume.done url=%s", url)
    agent_traces = [
        AgentTrace(
            name="Content",
            status="complete",
            summary=f"{content.kind.value.title()} extracted from {content.source}.",
            details=[
                f"{len(content.text):,} text characters",
                f"{len(content.segments):,} timestamped segments",
                f"{len(content.media):,} content images",
            ],
        ),
        AgentTrace(
            name="Research",
            status="complete" if research else "skipped",
            summary=(
                f"{len(research_results)} web results via {_research_sources(research_results)}."
                if research
                else "Web research disabled for this request."
            ),
            details=[
                *[f'Searched: "{topic.query}" - {topic.reason}' for topic in research_topics],
                f"Read {len(research_documents)} linked page(s)",
                *[
                    f"Found: {result.title}"
                    for result in research_results[:3]
                ],
            ],
        ),
        AgentTrace(
            name="Local Knowledge",
            status="complete",
            summary=f"{len(knowledge_matches)} related consumed items found.",
            details=[
                match.title or match.url
                for match in knowledge_matches[:3]
            ],
        ),
        AgentTrace(
            name="Research Planner",
            status="complete" if research else "skipped",
            summary=(
                f"{len(research_topics)} Ollama-planned search topics."
                if research
                else "Research planning disabled for this request."
            ),
            details=[
                f'{topic.query}: {topic.reason}'
                for topic in research_topics
            ],
        ),
    ]
    if analyze and analysis_agent is not None:
        agent_traces.append(
            AgentTrace(
                name="Ollama Summary",
                status="complete",
                summary=f"Analyzed locally with {LocalOllamaConsumptionAgent.model_name()}.",
                details=[
                    detail
                    for detail in (
                        _thinking_detail(analysis_agent.last_thinking),
                        analysis.reasoning_summary,
                        f"{len(analysis.reading_flow)} flow steps",
                        f"{len(analysis.context_helpers)} context helpers",
                        f"{len(analysis.glossary)} terms explained",
                        f"{len(analysis.visual_aids)} visual aids",
                        f"{len(analysis.research_context)} research context notes",
                        f"{len(analysis.research_highlights)} research highlights",
                        f"{len(analysis.deep_dive_questions)} deep-dive prompts",
                        f"{len(analysis.key_points)} key points",
                        f"{len(analysis.highlights)} highlights",
                        f"{len(analysis.chapters)} chapters",
                    )
                    if detail
                ],
            )
        )
    return ConsumeResponse(
        content=content,
        analysis=analysis,
        research_results=research_results,
        research_documents=research_documents,
        knowledge_matches=knowledge_matches,
        agent_traces=agent_traces,
    )


async def _plan_research_topics(
    content: ContentResponse,
    research: bool,
    progress: ProgressCallback | None,
    chapters: list[Chapter] | None = None,
    highlights: list[Highlight] | None = None,
) -> list[ResearchTopic]:
    if not research:
        await _emit(
            progress,
            AgentTrace(
                name="Research Planner",
                status="skipped",
                summary="Web research disabled for this request.",
            ),
        )
        return []

    grounded = bool(chapters or highlights)
    await _emit(
        progress,
        AgentTrace(
            name="Research Planner",
            status="running",
            summary=f"Finding search topics with {LocalOllamaConsumptionAgent.model_name()}.",
            details=[
                "Grounded in the extracted chapters and highlights."
                if grounded
                else "Using the extracted content body, not title-only queries.",
                "Looking for main concepts, jargon, missing context, and limitations.",
            ],
        ),
    )
    planner = LocalOllamaResearchPlanner()
    try:
        topics = await planner.plan(content, chapters=chapters, highlights=highlights)
    except Exception as error:
        logger.info("consume.research_plan_failed url=%s error=%s", content.url, error)
        topics = fallback_research_topics_for_content(content)
        await _emit(
            progress,
            AgentTrace(
                name="Research Planner",
                status="running",
                summary="Ollama topic planning failed; using local fallback topics.",
                details=[str(error)],
            ),
        )

    await _emit(
        progress,
        AgentTrace(
            name="Research Planner",
            status="complete",
            summary=f"{len(topics)} search topics selected.",
            details=[
                f'{topic.query}: {topic.reason}'
                for topic in topics
            ],
        ),
    )
    return topics


async def _emit(progress: ProgressCallback | None, trace: AgentTrace) -> None:
    if progress is not None:
        await progress(trace)


async def _emit_event(
    progress: AnalysisEventCallback | None,
    event: ConsumeStreamEvent,
) -> None:
    if progress is not None:
        await progress(event)


def _completed_task(result: T) -> asyncio.Task[T]:
    async def _result() -> T:
        return result

    return asyncio.create_task(_result())


def _research_sources(results: list[ResearchResult]) -> str:
    sources = sorted({result.source for result in results if result.source})
    if sources:
        return ", ".join(sources)
    return research_provider_description()


def _enrich_timed_analysis(
    content: ContentResponse,
    analysis: ConsumptionAnalysis,
) -> ConsumptionAnalysis:
    if not content.segments:
        return analysis

    highlights = sorted(analysis.highlights, key=_timed_item_sort_key)
    chapters = sorted(analysis.chapters, key=_timed_item_sort_key)
    enriched_highlights = [_enrich_highlight(content, highlight) for highlight in highlights]
    enriched_chapters = [_enrich_chapter(content, chapter) for chapter in chapters]
    return analysis.model_copy(
        update={
            "highlights": enriched_highlights,
            "chapters": enriched_chapters,
        }
    )


def _enrich_highlight(content: ContentResponse, highlight: Highlight) -> Highlight:
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
            "caption": highlight.caption or caption_for_range(
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


def _enrich_chapter(content: ContentResponse, chapter: Chapter) -> Chapter:
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
            "caption": chapter.caption or caption_for_range(
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


def _timestamp_or_none(value: float | None) -> str | None:
    if value is None:
        return None
    return timestamp_label(value)


def _timed_item_sort_key(item: Highlight | Chapter) -> tuple[int, float, str]:
    if item.start is None:
        return (1, 0.0, item.timestamp or "")
    return (0, item.start, item.timestamp or "")
