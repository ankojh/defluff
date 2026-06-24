from pydantic import BaseModel, Field


class DiscussMessage(BaseModel):
    role: str
    content: str


class DiscussRequest(BaseModel):
    question: str
    context: str = ""
    title: str | None = None
    history: list[DiscussMessage] = Field(default_factory=list)
