from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict


class UrlStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class UrlSubmission(BaseModel):
    url: AnyHttpUrl


class UrlRecord(BaseModel):
    id: int
    url: str
    status: UrlStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
