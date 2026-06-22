from contextlib import asynccontextmanager
import asyncio
import json
import logging
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.captions import CaptionError, get_captions_for_url
from app.config import settings
from app.consume import consume_url
from app.content import ContentError, get_content_for_url
from app.db import database
from app.debug_log import DEBUG_LOG_PATH, reset_debug_log, write_debug_event
from app.knowledge import clear_knowledge, remember_learned_item
from app.models import (
    CaptionRequest,
    CaptionResponse,
    ConsumeStreamEvent,
    ConsumeRequest,
    ConsumeResponse,
    ContentRequest,
    ContentResponse,
    DiscussRequest,
    LearnRequest,
    UrlRecord,
    UrlSubmission,
)
from app.ollama_agent import AnalysisError, LocalOllamaDiscussionAgent
from app.repository import create_url_submission

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("starting backend service")
    reset_debug_log()
    write_debug_event("backend.start", debug_log=str(DEBUG_LOG_PATH))
    await database.connect()
    try:
        yield
    finally:
        logger.info("stopping backend service")
        write_debug_event("backend.stop")
        await database.disconnect()


app = FastAPI(title=settings.service_name, lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.service_name}


@app.post("/api/urls", response_model=UrlRecord, status_code=201)
async def submit_url(payload: UrlSubmission) -> UrlRecord:
    return await create_url_submission(str(payload.url))


@app.post("/api/captions", response_model=CaptionResponse)
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


@app.post("/api/content", response_model=ContentResponse)
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


@app.post("/api/consume", response_model=ConsumeResponse)
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


@app.post("/api/consume/stream")
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


async def _consume_event_stream(payload: ConsumeRequest) -> AsyncIterator[str]:
    queue: asyncio.Queue[ConsumeStreamEvent | None] = asyncio.Queue()

    async def emit_trace(trace) -> None:
        await queue.put(ConsumeStreamEvent(type="trace", trace=trace))

    async def emit_analysis_event(event: ConsumeStreamEvent) -> None:
        await queue.put(event)

    async def worker() -> None:
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
        finally:
            await queue.put(None)

    worker_task = asyncio.create_task(worker())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break

            yield json.dumps(event.model_dump(mode="json", exclude_none=True)) + "\n"
    finally:
        if not worker_task.done():
            worker_task.cancel()


@app.post("/api/knowledge/learn", status_code=201)
async def learn(payload: LearnRequest) -> dict[str, object]:
    logger.info(
        "api.knowledge_learn kind=%s url=%s title=%r",
        payload.kind,
        payload.source_url,
        payload.title,
    )
    item_id = await remember_learned_item(payload)
    return {"status": "ok", "id": item_id}


@app.delete("/api/knowledge")
async def clear_all_knowledge() -> dict[str, object]:
    removed = await clear_knowledge()
    logger.info("api.knowledge_cleared removed=%d", removed)
    return {"status": "ok", "removed": removed}


@app.post("/api/discuss/stream")
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
            yield json.dumps({"type": kind, "text": text}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
    except Exception as error:
        logger.exception("api.discuss_stream_error")
        write_debug_event("discuss_stream.error", error=str(error))
        yield json.dumps({"type": "error", "message": str(error)}) + "\n"
