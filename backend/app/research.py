from html.parser import HTMLParser
import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
import lxml.html
import trafilatura

from app.config import settings
from app.models import AgentTrace, ContentResponse, ResearchDocument, ResearchResult, ResearchTopic

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[AgentTrace], Awaitable[None]]

SEARCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Defluff/0.1",
}

SEARCH_ENDPOINTS = (
    "https://html.duckduckgo.com/html/",
    "https://lite.duckduckgo.com/lite/",
)

MAX_RESEARCH_QUERIES = 6
RESULTS_PER_QUERY = 3
CHILD_LINKS_PER_DOCUMENT = 2


async def fetch_research_documents(
    results: list[ResearchResult],
    progress: ProgressCallback | None = None,
) -> list[ResearchDocument]:
    if not results:
        return []

    max_depth = max(1, min(settings.research_fetch_depth, 3))
    max_documents = max(1, settings.research_max_documents)
    logger.info(
        "research.fetch_started results=%d max_depth=%d max_documents=%d",
        len(results),
        max_depth,
        max_documents,
    )
    await _emit(
        progress,
        AgentTrace(
            name="Research Reader",
            status="running",
            summary=f"Reading top web results up to depth {max_depth}.",
            details=[result.title for result in results[:4]],
        ),
    )

    documents: list[ResearchDocument] = []
    seen: set[str] = set()
    queue: list[tuple[ResearchResult, int, str | None]] = [
        (result, 1, None)
        for result in results[:max_documents]
        if _is_fetchable_url(result.url)
    ]

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.research_timeout_seconds,
        headers=SEARCH_HEADERS,
    ) as client:
        while queue and len(documents) < max_documents:
            batch = queue[: max_documents - len(documents)]
            queue = queue[max_documents - len(documents) :]
            fetched = await asyncio.gather(
                *[
                    _fetch_research_document(client, result, depth, parent_url)
                    for result, depth, parent_url in batch
                    if _canonical_result_key(result.url) not in seen
                ]
            )

            for document, child_links in fetched:
                if document is None:
                    continue

                key = _canonical_result_key(document.url)
                if key in seen:
                    continue

                seen.add(key)
                documents.append(document)
                await _emit(
                    progress,
                    AgentTrace(
                        name="Research Reader",
                        status="running",
                        summary=f"Read: {document.title or document.url}",
                        details=[
                            f"Depth {document.depth}",
                            f"{len(document.text_excerpt):,} extracted characters",
                        ],
                    ),
                )

                if document.depth >= max_depth:
                    continue

                for child in child_links[:CHILD_LINKS_PER_DOCUMENT]:
                    child_key = _canonical_result_key(child.url)
                    if child_key not in seen and len(documents) + len(queue) < max_documents:
                        queue.append((child, document.depth + 1, document.url))

    logger.info("research.fetch_ready documents=%d", len(documents))
    await _emit(
        progress,
        AgentTrace(
            name="Research Reader",
            status="complete",
            summary=f"Read {len(documents)} research document(s).",
            details=[document.title or document.url for document in documents[:5]],
        ),
    )
    return documents


async def _fetch_research_document(
    client: httpx.AsyncClient,
    result: ResearchResult,
    depth: int,
    parent_url: str | None,
) -> tuple[ResearchDocument | None, list[ResearchResult]]:
    logger.info("research.document_fetch_started url=%s depth=%d", result.url, depth)
    try:
        response = await client.get(result.url)
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.info("research.document_fetch_error url=%s error=%s", result.url, error)
        return None, []

    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        logger.info("research.document_skipped_non_text url=%s content_type=%s", result.url, content_type)
        return None, []

    extracted = trafilatura.extract(
        response.text,
        include_comments=False,
        include_tables=True,
        output_format="txt",
        url=str(response.url),
    )
    if not extracted or len(extracted.split()) < 80:
        logger.info("research.document_extract_empty url=%s", result.url)
        return None, []

    metadata = trafilatura.extract_metadata(response.text)
    title = metadata.title if metadata and metadata.title else result.title
    text_excerpt = _trim_text(extracted, settings.research_max_chars_per_document)
    links = _relevant_links_from_html(
        response.text,
        base_url=str(response.url),
        query=result.query or result.title,
        parent_url=result.url,
    )
    document = ResearchDocument(
        title=title,
        url=str(response.url),
        query=result.query,
        source=result.source,
        depth=depth,
        parent_url=parent_url,
        text_excerpt=text_excerpt,
        outbound_links=links[:CHILD_LINKS_PER_DOCUMENT],
    )
    logger.info(
        "research.document_ready url=%s depth=%d chars=%d links=%d",
        document.url,
        depth,
        len(text_excerpt),
        len(links),
    )
    return document, links


def _relevant_links_from_html(
    html: str,
    base_url: str,
    query: str,
    parent_url: str,
) -> list[ResearchResult]:
    try:
        document = lxml.html.fromstring(html)
    except (TypeError, ValueError):
        return []

    query_terms = {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9+-]{3,}", query)
        if term.lower() not in _STOPWORDS
    }
    links: list[tuple[int, ResearchResult]] = []
    seen: set[str] = set()
    parent_host = urlparse(parent_url).netloc.lower().removeprefix("www.")

    for anchor in document.xpath("//a[@href]"):
        href = anchor.get("href")
        if not href:
            continue

        url = urljoin(base_url, href)
        if not _is_fetchable_url(url):
            continue

        key = _canonical_result_key(url)
        if key in seen or key == _canonical_result_key(parent_url):
            continue

        title = _clean_text(anchor.text_content())
        if not title or len(title) < 4:
            continue

        parsed = urlparse(url)
        host = parsed.netloc.lower().removeprefix("www.")
        text_terms = set(re.findall(r"[a-z][a-z0-9+-]{3,}", title.lower()))
        score = len(query_terms & text_terms)
        if host == parent_host:
            score += 1
        if any(marker in parsed.path.lower() for marker in ("/tag/", "/author/", "/privacy", "/login")):
            score -= 3
        if score <= 0:
            continue

        seen.add(key)
        links.append(
            (
                score,
                ResearchResult(
                    title=title[:180],
                    url=url,
                    source="Linked page",
                    query=query,
                ),
            )
        )

    links.sort(key=lambda item: item[0], reverse=True)
    return [result for _, result in links[:8]]


def _is_fetchable_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    lowered_path = parsed.path.lower()
    blocked_suffixes = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".mp4",
        ".mp3",
        ".zip",
        ".dmg",
        ".pdf",
    )
    return not lowered_path.endswith(blocked_suffixes)


def _trim_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned

    return cleaned[:max_chars].rsplit(" ", maxsplit=1)[0].strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


async def research_content(
    content: ContentResponse,
    topics: list[ResearchTopic] | None = None,
    limit: int = 8,
    progress: ProgressCallback | None = None,
) -> list[ResearchResult]:
    selected_topics = topics or fallback_research_topics_for_content(
        content,
        max_topics=MAX_RESEARCH_QUERIES,
    )
    if not selected_topics:
        logger.info("research.skipped reason=empty_query url=%s", content.url)
        return []

    queries = [topic.query for topic in selected_topics]
    logger.info(
        "research.started url=%s queries=%r provider=%s",
        content.url,
        queries,
        settings.search_provider,
    )
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=settings.research_timeout_seconds,
        headers=SEARCH_HEADERS,
    ) as client:
        search_tasks = [
            _search_topic(client, topic, limit=RESULTS_PER_QUERY, progress=progress)
            for topic in selected_topics
        ]
        result_groups = await asyncio.gather(*search_tasks)

    results = _dedupe_results(
        [result for group in result_groups for result in group],
        limit=limit,
    )
    if results:
        logger.info("research.ready url=%s queries=%d results=%d", content.url, len(queries), len(results))
        return results

    logger.info("research.empty url=%s queries=%r", content.url, queries)
    return []


def google_search_configured() -> bool:
    return bool(settings.google_search_api_key and settings.google_search_engine_id)


def research_provider_description() -> str:
    if settings.search_provider.lower() == "google":
        if google_search_configured():
            return "Google Custom Search"
        return "Google requested, missing GOOGLE_SEARCH_API_KEY or GOOGLE_SEARCH_ENGINE_ID"

    return "DuckDuckGo"


async def _google_search(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> list[ResearchResult]:
    if not google_search_configured():
        logger.info("research.google_skipped reason=missing_credentials")
        return []

    try:
        response = await client.get(
            "https://www.googleapis.com/customsearch/v1",
            params={
                "key": settings.google_search_api_key,
                "cx": settings.google_search_engine_id,
                "q": query,
                "num": min(limit, 10),
            },
        )
        logger.info(
            "research.google_http_response status=%d bytes=%d",
            response.status_code,
            len(response.text),
        )
        response.raise_for_status()
    except httpx.HTTPError as error:
        logger.info("research.google_http_error error=%s", error)
        return []

    payload = response.json()
    results: list[ResearchResult] = []
    for item in payload.get("items", []):
        title = item.get("title")
        url = item.get("link")
        if not title or not url:
            continue

        results.append(
            ResearchResult(
                title=title,
                url=url,
                snippet=item.get("snippet"),
                source="Google",
                query=query,
            )
        )
        if len(results) >= limit:
            break

    return results


async def _search_topic(
    client: httpx.AsyncClient,
    topic: ResearchTopic,
    limit: int,
    progress: ProgressCallback | None = None,
) -> list[ResearchResult]:
    query = topic.query
    logger.info("research.query_started query=%r provider=%s", query, settings.search_provider)
    await _emit(
        progress,
        AgentTrace(
            name="Research",
            status="running",
            summary=f'Searching "{query}"',
            details=[topic.reason, *[f"Source term: {term}" for term in topic.source_terms[:3]]],
        ),
    )
    if settings.search_provider.lower() == "google":
        google_results = await _google_search(client, query, limit)
        if google_results:
            logger.info("research.google_ready query=%r results=%d", query, len(google_results))
            await _emit_research_results(progress, query, google_results)
            return google_results

        logger.info("research.google_empty_or_unconfigured query=%r fallback=duckduckgo", query)

    for endpoint in SEARCH_ENDPOINTS:
        try:
            response = await client.get(endpoint, params={"q": query})
            logger.info(
                "research.http_response query=%r endpoint=%s status=%d bytes=%d",
                query,
                endpoint,
                response.status_code,
                len(response.text),
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            logger.info("research.http_error query=%r endpoint=%s error=%s", query, endpoint, error)
            continue

        if _looks_like_search_challenge(response.text):
            logger.info("research.challenge query=%r endpoint=%s", query, endpoint)
            continue

        results = _parse_duckduckgo_html(response.text, limit, query=query)
        logger.info("research.parsed query=%r endpoint=%s results=%d", query, endpoint, len(results))
        if results:
            await _emit_research_results(progress, query, results)
            return results

    await _emit(
        progress,
        AgentTrace(
            name="Research",
            status="running",
            summary=f'No search results for "{query}"',
            details=[topic.reason],
        ),
    )
    return []


def research_queries_for_content(content: ContentResponse, max_queries: int = MAX_RESEARCH_QUERIES) -> list[str]:
    return [topic.query for topic in fallback_research_topics_for_content(content, max_topics=max_queries)]


def fallback_research_topics_for_content(
    content: ContentResponse,
    max_topics: int = MAX_RESEARCH_QUERIES,
) -> list[ResearchTopic]:
    return [
        ResearchTopic(
            query=query,
            reason="Fallback topic from local phrase extraction.",
            source_terms=[],
        )
        for query in _research_queries(content, max_queries=max_topics)
    ]


def _research_queries(content: ContentResponse, max_queries: int) -> list[str]:
    candidates: list[str] = []
    title = _clean_query(content.title or "")
    if title:
        candidates.append(title)

    phrases = _extract_research_phrases(content)
    if title and phrases:
        candidates.append(_clean_query(f"{title} {' '.join(phrases[:2])}"))
        candidates.append(_clean_query(f"{phrases[0]} explained"))
        candidates.append(_clean_query(f"{title} background context"))
    elif phrases:
        candidates.append(_clean_query(" ".join(phrases[:3])))
        candidates.append(_clean_query(f"{phrases[0]} explained"))

    for phrase in phrases[:4]:
        candidates.append(_clean_query(f"{phrase} overview"))
        candidates.append(_clean_query(f"{phrase} limitations criticism context"))

    if content.title:
        host = urlparse(content.url).netloc.removeprefix("www.")
        if host:
            candidates.append(_clean_query(f"{title} {host}"))
    else:
        host = urlparse(content.url).netloc.removeprefix("www.")
        words = content.text.split()
        candidates.append(_clean_query(" ".join([host, *words[:12]])))

    return _unique_queries(candidates, max_queries=max_queries)


def _extract_research_phrases(content: ContentResponse) -> list[str]:
    text = _text_for_phrase_extraction(content)
    if not text:
        return []

    phrase_scores: dict[str, int] = {}
    for phrase in _capitalized_phrases(text):
        phrase_scores[phrase] = phrase_scores.get(phrase, 0) + 4

    for phrase in _technical_terms(text):
        phrase_scores[phrase] = phrase_scores.get(phrase, 0) + 3

    for phrase in _frequent_keyphrases(text):
        phrase_scores[phrase] = phrase_scores.get(phrase, 0) + 1

    ranked = sorted(
        phrase_scores.items(),
        key=lambda item: (item[1], len(item[0])),
        reverse=True,
    )
    return [phrase for phrase, _ in ranked[:10]]


def _text_for_phrase_extraction(content: ContentResponse) -> str:
    if content.segments:
        return " ".join(segment.text for segment in content.segments[:120])

    block_texts = [
        block.text
        for block in content.blocks[:80]
        if block.text and len(block.text.split()) >= 3
    ]
    if block_texts:
        return " ".join(block_texts)[:12000]

    return content.text[:12000]


def _capitalized_phrases(text: str) -> list[str]:
    matches = re.findall(
        r"\b(?:[A-Z][A-Za-z0-9&.+-]{2,}|[A-Z]{2,})(?:\s+(?:[A-Z][A-Za-z0-9&.+-]{2,}|[A-Z]{2,})){0,4}",
        text,
    )
    return [_normalize_phrase(match) for match in matches if _useful_phrase(match)]


def _technical_terms(text: str) -> list[str]:
    matches = re.findall(
        r"\b(?:[A-Za-z]+[-/][A-Za-z0-9-]+|[A-Z]{2,}|[A-Za-z]+(?:\d+[A-Za-z]*|\.[A-Za-z0-9]+))\b",
        text,
    )
    return [_normalize_phrase(match) for match in matches if _useful_phrase(match)]


def _frequent_keyphrases(text: str) -> list[str]:
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}", text)
        if word.lower() not in _STOPWORDS
    ]
    scores: dict[str, int] = {}
    for size in (2, 3):
        for index in range(0, max(0, len(words) - size + 1)):
            phrase_words = words[index : index + size]
            if any(word in _STOPWORDS for word in phrase_words):
                continue

            phrase = " ".join(phrase_words)
            if _useful_phrase(phrase):
                scores[phrase] = scores.get(phrase, 0) + 1

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [phrase for phrase, score in ranked[:8] if score > 1]


def _normalize_phrase(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip(" ,.;:()[]{}\"'")).strip()


def _useful_phrase(value: str) -> bool:
    phrase = _normalize_phrase(value)
    if len(phrase) < 4 or len(phrase) > 80:
        return False

    lowered = phrase.lower()
    if lowered in _STOPWORDS or lowered in _GENERIC_PHRASES:
        return False

    words = lowered.split()
    if len(words) > 1 and all(word in _STOPWORDS for word in words):
        return False

    return True


def _clean_query(query: str) -> str:
    query = re.sub(r"\s+", " ", query).strip()
    return query[:180].strip()


def _unique_queries(candidates: list[str], max_queries: int) -> list[str]:
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        query = _clean_query(candidate)
        key = query.lower()
        if not query or key in seen:
            continue

        seen.add(key)
        queries.append(query)
        if len(queries) >= max_queries:
            break

    return queries


def _dedupe_results(results: list[ResearchResult], limit: int) -> list[ResearchResult]:
    deduped: list[ResearchResult] = []
    seen: set[str] = set()
    for result in results:
        key = _canonical_result_key(result.url)
        if key in seen:
            continue

        seen.add(key)
        deduped.append(result)
        if len(deduped) >= limit:
            break

    return deduped


async def _emit(progress: ProgressCallback | None, trace: AgentTrace) -> None:
    if progress is not None:
        await progress(trace)


async def _emit_research_results(
    progress: ProgressCallback | None,
    query: str,
    results: list[ResearchResult],
) -> None:
    if progress is None:
        return

    await progress(
        AgentTrace(
            name="Research",
            status="running",
            summary=f'Found {len(results)} result(s) for "{query}"',
            details=[result.title for result in results[:3]],
        )
    )


def _parse_duckduckgo_html(html: str, limit: int, query: str | None = None) -> list[ResearchResult]:
    parser = _DuckDuckGoParser()
    parser.feed(html)

    results: list[ResearchResult] = []
    for item in parser.results:
        if not item.title or not item.url:
            continue

        results.append(
            ResearchResult(
                title=item.title.strip(),
                url=_clean_result_url(item.url),
                snippet=item.snippet.strip() if item.snippet else None,
                source="DuckDuckGo",
                query=query,
            )
        )
        if len(results) >= limit:
            break

    return results


def _looks_like_search_challenge(html: str) -> bool:
    lowered = html.lower()
    return "anomaly-modal" in lowered or "bots use duckduckgo too" in lowered


def _clean_result_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [url])[0]
        return unquote(target)
    return url


def _canonical_result_key(url: str) -> str:
    parsed = urlparse(_clean_result_url(url))
    return f"{parsed.netloc.lower().removeprefix('www.')}{parsed.path.rstrip('/')}"


_GENERIC_PHRASES = {
    "article",
    "video",
    "youtube",
    "transcript",
    "captions",
    "introduction",
    "conclusion",
    "background",
    "overview",
}

_STOPWORDS = {
    "about",
    "above",
    "after",
    "again",
    "against",
    "also",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "could",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "from",
    "further",
    "have",
    "having",
    "here",
    "into",
    "itself",
    "just",
    "more",
    "most",
    "other",
    "over",
    "same",
    "should",
    "some",
    "such",
    "than",
    "that",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "under",
    "until",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
}


class _ParsedResult:
    def __init__(self) -> None:
        self.title = ""
        self.url = ""
        self.snippet = ""


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[_ParsedResult] = []
        self._current: _ParsedResult | None = None
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        class_name = attributes.get("class", "")

        if tag == "a" and ("result__a" in class_name or "result-link" in class_name):
            self._current = _ParsedResult()
            self._current.url = attributes.get("href", "") or ""
            self._capture = "title"
        elif self._current is not None and (
            "result__snippet" in class_name or "result-snippet" in class_name
        ):
            self._capture = "snippet"

    def handle_data(self, data: str) -> None:
        if self._current is None or self._capture is None:
            return

        if self._capture == "title":
            self._current.title += data
        elif self._capture == "snippet":
            self._current.snippet += data

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return

        if tag == "a" and self._capture == "title":
            self.results.append(self._current)
            self._capture = None
        elif self._capture == "snippet":
            self._capture = None
