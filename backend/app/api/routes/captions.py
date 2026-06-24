import logging

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.integrations.captions import CaptionError, get_captions_for_url
from app.schemas import CaptionRequest, CaptionResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/captions", response_model=CaptionResponse)
async def get_captions(payload: CaptionRequest) -> CaptionResponse:
    logger.info("api.captions url=%s language=%s", payload.url, payload.language)
    try:
        return await run_in_threadpool(
            get_captions_for_url,
            str(payload.url),
            payload.language,
        )
    except CaptionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
