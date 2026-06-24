"""DuckDuckGo HTML search provider."""

import logging
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.schemas import ResearchResult

logger = logging.getLogger(__name__)

SEARCH_ENDPOINTS = (
    "https://html.duckduckgo.com/html/",
    "https://lite.duckduckgo.com/lite/",
)


async def search(client: httpx.AsyncClient, query: str, limit: int) -> list[ResearchResult]:
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
            return results

    return []


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
                url=clean_result_url(item.url),
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


def clean_result_url(url: str) -> str:
    """Unwrap DuckDuckGo's /l/?uddg= redirect links to the real target URL."""
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [url])[0]
        return unquote(target)
    return url


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
