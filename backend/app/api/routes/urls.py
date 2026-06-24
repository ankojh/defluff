from fastapi import APIRouter

from app.db.repository import create_url_submission
from app.schemas import UrlRecord, UrlSubmission

router = APIRouter()


@router.post("/api/urls", response_model=UrlRecord, status_code=201)
async def submit_url(payload: UrlSubmission) -> UrlRecord:
    return await create_url_submission(str(payload.url))
