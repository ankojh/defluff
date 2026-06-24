"""Shared builders that turn content/research into prompt-ready payloads."""

from app.core.config import settings
from app.schemas import ContentResponse, ResearchDocument
from app.utils.timestamps import format_timestamp


def content_body_for_prompt(content: ContentResponse) -> str:
    if content.segments:
        lines: list[str] = []
        total_chars = 0
        for segment in content.segments:
            timestamp = format_timestamp(segment.start)
            line = f"[{timestamp}] {segment.text}"
            total_chars += len(line)
            if total_chars > settings.analysis_max_chars:
                break
            lines.append(line)
        return "\n".join(lines)

    return content.text[: settings.analysis_max_chars]


def caption_for_prompt(
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

        line = f"[{format_timestamp(segment.start)}] {segment.text}"
        total_chars += len(line)
        if total_chars > limit:
            break
        lines.append(line)

    return "\n".join(lines)


def content_end_seconds(content: ContentResponse) -> float | None:
    if not content.segments:
        return None
    return max(segment.end for segment in content.segments)


def research_documents_for_prompt(
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
