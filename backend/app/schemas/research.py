from pydantic import BaseModel, Field


class ResearchResult(BaseModel):
    title: str
    url: str
    snippet: str | None = None
    source: str | None = None
    query: str | None = None


class ResearchDocument(BaseModel):
    title: str | None = None
    url: str
    query: str | None = None
    source: str | None = None
    depth: int = 1
    parent_url: str | None = None
    text_excerpt: str
    outbound_links: list[ResearchResult] = Field(default_factory=list)


class ResearchTopic(BaseModel):
    query: str
    reason: str
    source_terms: list[str] = Field(default_factory=list)
