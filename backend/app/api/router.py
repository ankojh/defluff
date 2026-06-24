from fastapi import APIRouter

from app.api.routes import captions, consume, content, discuss, health, knowledge, urls

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(urls.router)
api_router.include_router(captions.router)
api_router.include_router(content.router)
api_router.include_router(consume.router)
api_router.include_router(knowledge.router)
api_router.include_router(discuss.router)
