import logging

from fastapi import APIRouter

from app.schemas import LearnRequest
from app.services.knowledge import clear_knowledge, remember_learned_item

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/api/knowledge/learn", status_code=201)
async def learn(payload: LearnRequest) -> dict[str, object]:
    logger.info(
        "api.knowledge_learn kind=%s url=%s title=%r",
        payload.kind,
        payload.source_url,
        payload.title,
    )
    item_id = await remember_learned_item(payload)
    return {"status": "ok", "id": item_id}


@router.delete("/api/knowledge")
async def clear_all_knowledge() -> dict[str, object]:
    removed = await clear_knowledge()
    logger.info("api.knowledge_cleared removed=%d", removed)
    return {"status": "ok", "removed": removed}
