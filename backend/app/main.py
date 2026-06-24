import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.core.debug_log import DEBUG_LOG_PATH, reset_debug_log, write_debug_event
from app.core.logging import setup_logging
from app.db import database

setup_logging()
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


def create_app() -> FastAPI:
    app = FastAPI(title=settings.service_name, lifespan=lifespan)
    app.include_router(api_router)
    return app


app = create_app()
