import asyncio
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.agents import AnalysisError
from app.api.streaming import stream_from_queue, to_ndjson
from app.content import ContentError
from app.core.debug_log import DEBUG_LOG_PATH, write_debug_event
from app.schemas import AgentTrace, ConsumeRequest, ConsumeResponse, ConsumeStreamEvent
from app.services.consume import consume_url

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/consume", response_model=ConsumeResponse)
async def consume(payload: ConsumeRequest) -> ConsumeResponse:
    logger.info(
        "api.consume url=%s language=%s remember=%s research=%s",
        payload.url,
        payload.language,
        payload.remember,
        payload.research,
    )
    try:
        return await consume_url(
            str(payload.url),
            payload.language,
            payload.remember,
            payload.research,
            analyze=payload.analyze,
        )
    except ContentError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AnalysisError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/api/consume/stream")
async def consume_stream(payload: ConsumeRequest) -> StreamingResponse:
    logger.info(
        "api.consume_stream url=%s language=%s remember=%s research=%s",
        payload.url,
        payload.language,
        payload.remember,
        payload.research,
    )
    return StreamingResponse(
        _consume_event_stream(payload),
        media_type="application/x-ndjson",
    )


def _consume_event_stream(payload: ConsumeRequest) -> AsyncIterator[str]:
    async def worker(queue: asyncio.Queue) -> None:
        async def emit_trace(trace) -> None:
            await queue.put(ConsumeStreamEvent(type="trace", trace=trace))

        async def emit_analysis_event(event: ConsumeStreamEvent) -> None:
            await queue.put(event)

        try:
            response = await consume_url(
                str(payload.url),
                payload.language,
                payload.remember,
                payload.research,
                progress=emit_trace,
                analysis_progress=emit_analysis_event,
                analyze=payload.analyze,
            )
            await queue.put(ConsumeStreamEvent(type="final", response=response))
        except (ContentError, AnalysisError) as error:
            write_debug_event("consume_stream.error", error=str(error))
            await queue.put(ConsumeStreamEvent(type="error", message=str(error)))
        except Exception as error:
            logger.exception("api.consume_stream_unhandled_error")
            write_debug_event("consume_stream.unhandled_error", error=str(error))
            await queue.put(
                ConsumeStreamEvent(
                    type="error",
                    message=(
                        f"Unexpected error: {error}. "
                        f"Debug log: {DEBUG_LOG_PATH}"
                    ),
                )
            )

    return stream_from_queue(
        worker,
        serialize=lambda event: to_ndjson(event.model_dump(mode="json", exclude_none=True)),
        heartbeat=lambda: ConsumeStreamEvent(
            type="trace",
            trace=AgentTrace(
                name="Backend",
                status="running",
                summary="Still working locally; waiting for the current model step.",
            ),
        ),
        heartbeat_seconds=15.0,
    )
