import logging

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.content import ContentError, get_content_for_url
from app.schemas import ContentRequest, ContentResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/content", response_model=ContentResponse)
async def get_content(payload: ContentRequest) -> ContentResponse:
    logger.info("api.content url=%s language=%s", payload.url, payload.language)
    try:
        return await run_in_threadpool(
            get_content_for_url,
            str(payload.url),
            payload.language,
        )
    except ContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
