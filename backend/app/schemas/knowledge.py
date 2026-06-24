from datetime import datetime

from pydantic import BaseModel


class KnowledgeMatch(BaseModel):
    id: int
    url: str
    title: str | None = None
    summary: str
    consumed_at: datetime
    overlap: float = 0.0


class LearnRequest(BaseModel):
    """One chapter or highlight the user marks as already known/learned."""

    kind: str
    source_url: str
    source_title: str | None = None
    title: str
    summary: str
    detail: str = ""
