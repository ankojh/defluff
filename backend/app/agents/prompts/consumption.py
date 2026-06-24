"""Prompt builders for the consumption agent (chaptering, highlights, summary)."""

import json

from app.agents.prompts.inputs import (
    caption_for_prompt,
    content_body_for_prompt,
    research_documents_for_prompt,
)
from app.schemas import Chapter, ContentResponse, Highlight, KnowledgeMatch, ResearchDocument


def chapter_segmentation_prompt(content: ContentResponse) -> str:
    payload = {
        "url": content.url,
        "title": content.title,
        "kind": content.kind,
        "language": content.language,
        "transcript": content_body_for_prompt(content),
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


def text_segmentation_prompt(content: ContentResponse) -> str:
    payload = {
        "url": content.url,
        "title": content.title,
        "kind": content.kind,
        "language": content.language,
        "body": content_body_for_prompt(content),
    }

    return (
        "Split this written document into sequential topic chapters and pick the highlights "
        "worth revisiting. The document has no timeline, so do not invent timestamps.\n"
        "Cover the document in order, starting a new chapter when the topic, argument, or focus "
        "changes. Do not create tiny chapters for navigation, ads, or boilerplate.\n"
        "Highlights are the key revisit points across the whole document: claims, decisions, "
        "definitions, examples, warnings, or technical details. Keep them distinct and in "
        "reading order; do not repeat the same point.\n"
        "Return exactly this JSON shape:\n"
        "{\n"
        '  "chapters": [\n'
        '    {"title": "short topic title", "summary": "2 to 4 dense sentences on this section"}\n'
        "  ],\n"
        '  "highlights": [\n'
        "    {\n"
        '      "text": "10 to 20 word label for this point, paraphrased",\n'
        '      "summary": "2 to 4 dense sentences explaining the full point",\n'
        '      "why": "one sentence explaining why this point is worth revisiting"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Prefer 3 to 8 chapters and 4 to 10 highlights for a typical article, fewer for short "
        "pieces. Paraphrase in your own words; do not copy long verbatim passages.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def chapter_analysis_prompt(
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
            "transcript": caption_for_prompt(content, chapter.start, chapter.end),
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


def overall_analysis_prompt(
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
            "body": content_body_for_prompt(content) if not content.segments else None,
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
        "research_documents": research_documents_for_prompt(research_documents),
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
        "Use 5 to 10 summary_points when the source is substantial. For glossary, "
        "include 2 to 6 terms only when jargon or assumed background appears. For research_context, "
        "include 2 to 6 notes. For research_highlights, include 2 to 5 items tied to URLs. "
        "For deep_dive_questions, include 3 to 6 concrete next questions.\n\n"
        f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def transcript_format_prompt(chapter: Chapter, highlights: list[Highlight]) -> str:
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
