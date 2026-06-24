"""Google Custom Search provider."""

import logging

import httpx

from app.core.config import settings
from app.schemas import ResearchResult

logger = logging.getLogger(__name__)


def google_search_configured() -> bool:
    return bool(settings.google_search_api_key and settings.google_search_engine_id)


async def search(client: httpx.AsyncClient, query: str, limit: int) -> list[ResearchResult]:
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
