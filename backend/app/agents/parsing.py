"""Turn raw Ollama JSON output into validated schema objects.

Tolerant by design: coerces loose model output, repairs truncated JSON, and
logs malformed responses to the debug log before giving up.
"""

import json
import re
from dataclasses import dataclass

from app.agents.errors import AnalysisError
from app.core.debug_log import DEBUG_LOG_PATH, write_debug_event
from app.schemas import Chapter, ConsumptionAnalysis, Highlight, ResearchTopic
from app.utils.timestamps import format_timestamp


@dataclass(frozen=True)
class ChapterAnalysis:
    title: str
    summary: str
    highlights: list[Highlight]


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


def _parse_text_segments(raw: str) -> tuple[list[Chapter], list[Highlight]]:
    """Parse the single-call chapters + highlights for timeline-free sources."""
    data = _load_ollama_json(raw, purpose="text segmentation")

    if not isinstance(data, dict):
        raise AnalysisError("Ollama text segmentation JSON response was not an object")

    raw_chapters = data.get("chapters")
    chapters: list[Chapter] = []
    if isinstance(raw_chapters, list):
        chapters = [
            Chapter.model_validate(_chapter_item(item))
            for item in raw_chapters
            if isinstance(item, dict) and _string_or_default(item.get("title"), "")
        ]

    raw_highlights = data.get("highlights")
    highlights: list[Highlight] = []
    if isinstance(raw_highlights, list):
        highlights = [
            Highlight.model_validate(_highlight_item(item))
            for item in raw_highlights
            if isinstance(item, dict) and _string_or_default(item.get("text"), "")
        ]

    return chapters, highlights


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
        timestamp = format_timestamp(float(start))
    if end_timestamp is None and end is not None:
        end_timestamp = format_timestamp(float(end))

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
        timestamp = format_timestamp(float(start))
    if end_timestamp is None and end is not None:
        end_timestamp = format_timestamp(float(end))

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
