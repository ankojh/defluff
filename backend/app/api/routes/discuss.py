import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents import LocalOllamaDiscussionAgent
from app.api.streaming import to_ndjson
from app.core.debug_log import write_debug_event
from app.schemas import DiscussRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/discuss/stream")
async def discuss_stream(payload: DiscussRequest) -> StreamingResponse:
    logger.info(
        "api.discuss_stream question_chars=%d context_chars=%d history=%d",
        len(payload.question),
        len(payload.context),
        len(payload.history),
    )
    return StreamingResponse(
        _discuss_event_stream(payload),
        media_type="application/x-ndjson",
    )


async def _discuss_event_stream(payload: DiscussRequest) -> AsyncIterator[str]:
    agent = LocalOllamaDiscussionAgent()
    try:
        async for kind, text in agent.discuss(
            payload.question,
            payload.context,
            payload.title,
            payload.history,
        ):
            yield to_ndjson({"type": kind, "text": text})
        yield to_ndjson({"type": "done"})
    except Exception as error:
        logger.exception("api.discuss_stream_error")
        write_debug_event("discuss_stream.error", error=str(error))
        yield to_ndjson({"type": "error", "message": str(error)})
