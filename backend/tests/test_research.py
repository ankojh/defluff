from app.models import Chapter, ContentKind, ContentResponse, Highlight
from app.ollama_agent import (
    _parse_analysis,
    _parse_research_topics,
    _parse_text_segments,
    _research_planning_prompt,
)
from app.research import _parse_duckduckgo_html, research_queries_for_content


def test_parse_text_segments_returns_untimed_chapters_and_highlights() -> None:
    raw = """
    {
      "chapters": [
        {"title": "The problem", "summary": "Why current auth is painful."},
        {"title": "The fix", "summary": "How passkeys remove passwords."}
      ],
      "highlights": [
        {"text": "Passkeys replace shared secrets", "summary": "No password to phish.", "why": "Core claim."},
        {"text": "Sync vs device-bound", "summary": "Tradeoffs differ.", "why": "Practical choice."}
      ]
    }
    """

    chapters, highlights = _parse_text_segments(raw)

    assert [chapter.title for chapter in chapters] == ["The problem", "The fix"]
    assert [highlight.text for highlight in highlights] == [
        "Passkeys replace shared secrets",
        "Sync vs device-bound",
    ]
    # Articles have no timeline — chapters/highlights must carry no timestamps.
    assert all(chapter.start is None and chapter.timestamp is None for chapter in chapters)
    assert all(highlight.start is None and highlight.timestamp is None for highlight in highlights)


def test_research_planning_prompt_grounds_in_chapters_and_highlights() -> None:
    content = ContentResponse(
        url="https://example.com/v",
        title="Audi Q7 review",
        kind=ContentKind.youtube,
        source="youtube",
        text="full transcript body",
        segments=[],
    )
    chapters = [Chapter(title="OLED tail lights", summary="New lighting signatures.")]
    highlights = [
        Highlight(
            text="diesel mild-hybrid drivetrain",
            why="An unusual powertrain choice.",
            summary="A 48V diesel setup.",
        )
    ]

    prompt = _research_planning_prompt(content, chapters, highlights, max_topics=6)

    assert "OLED tail lights" in prompt
    assert "diesel mild-hybrid drivetrain" in prompt
    # The raw body is dropped once chapters/highlights are available.
    assert '"body": null' in prompt


def test_overall_prompt_defines_key_takeaways() -> None:
    from app.ollama_agent import _overall_analysis_prompt

    content = ContentResponse(
        url="https://example.com/v",
        title="7 auth methods you should know",
        kind=ContentKind.youtube,
        source="youtube",
        text="full transcript body",
        segments=[],
    )

    prompt = _overall_analysis_prompt(content, [], [], [], [])

    assert "key takeaways" in prompt
    assert "7 auth methods" in prompt
    assert "definition, why it matters, how it is used" in prompt


def test_research_queries_include_title_topics_and_jargon() -> None:
    content = ContentResponse(
        url="https://example.com/article",
        title="Why Retrieval Augmented Generation Changes AI Search",
        kind=ContentKind.article,
        source="article",
        text=(
            "Retrieval Augmented Generation depends on vector databases, embeddings, "
            "reranking, BM25, and semantic search. RAG pipelines often fail because "
            "chunking strategies and evaluation are weak."
        ),
    )

    queries = research_queries_for_content(content, max_queries=6)

    assert queries[0] == "Why Retrieval Augmented Generation Changes AI Search"
    assert any("BM25" in query or "RAG" in query for query in queries)
    assert any("explained" in query for query in queries)
    assert any("background context" in query for query in queries)


def test_parse_duckduckgo_html_attaches_query() -> None:
    html = """
    <a class="result__a" href="https://example.com/result">Result title</a>
    <a class="result__snippet">Useful result snippet.</a>
    """

    results = _parse_duckduckgo_html(html, limit=1, query="RAG explained")

    assert results[0].query == "RAG explained"


def test_parse_ollama_research_topics() -> None:
    raw = """
    {
      "topics": [
        {
          "query": "retrieval augmented generation evaluation",
          "reason": "The source discusses weak evaluation as a failure mode.",
          "source_terms": ["RAG", "evaluation"]
        }
      ]
    }
    """

    topics = _parse_research_topics(raw, max_topics=3)

    assert topics[0].query == "retrieval augmented generation evaluation"
    assert topics[0].source_terms == ["RAG", "evaluation"]


def test_parse_analysis_includes_consumption_helpers() -> None:
    raw = """
    {
      "summary": "A plain-English explanation.",
      "tldr": "The core takeaway.",
      "reasoning_summary": "Prioritized jargon and revisit points.",
      "reading_flow": ["Start with the problem.", "Then read the tradeoff."],
      "context_helpers": ["BM25 is an older lexical search baseline."],
      "glossary": [
        {"term": "RAG", "explanation": "Retrieval plus generation."}
      ],
      "research_context": ["External docs explain why reranking changes result quality."],
      "research_highlights": [
        {
          "title": "RAG evaluation guide",
          "url": "https://example.com/rag-eval",
          "point": "Evaluation should test retrieval and generation separately.",
          "why_it_matters": "It clarifies why generic answer scoring misses retrieval failures."
        }
      ],
      "deep_dive_questions": ["How should retrieval quality be measured?"],
      "key_points": ["Evaluation matters."],
      "novel_points": [],
      "already_known": [],
      "highlights": []
    }
    """

    analysis = _parse_analysis(raw)

    assert analysis.tldr == "The core takeaway."
    assert analysis.reading_flow == ["Start with the problem.", "Then read the tradeoff."]
    assert analysis.glossary[0].term == "RAG"
    assert analysis.research_context == [
        "External docs explain why reranking changes result quality."
    ]
    assert analysis.research_highlights[0].url == "https://example.com/rag-eval"
    assert analysis.deep_dive_questions == ["How should retrieval quality be measured?"]
