"""Prompt builder for the research-planning agent."""

import json

from app.agents.prompts.inputs import content_body_for_prompt
from app.schemas import Chapter, ContentResponse, Highlight


def research_planning_prompt(
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
        "body": None if has_extracted else content_body_for_prompt(content),
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
