from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field


class UrlStatus(StrEnum):
    pending = "pending"
    processing = "processing"
    complete = "complete"
    failed = "failed"


class UrlSubmission(BaseModel):
    url: AnyHttpUrl


class CaptionSource(StrEnum):
    youtube = "youtube"
    whisper = "whisper"


class CaptionRequest(BaseModel):
    url: AnyHttpUrl
    language: str = "en"


class CaptionSegment(BaseModel):
    start: float
    end: float
    text: str


class CaptionResponse(BaseModel):
    url: str
    title: str | None = None
    language: str
    source: CaptionSource
    text: str
    segments: list[CaptionSegment]
    thumbnail_url: str | None = None


class ContentKind(StrEnum):
    article = "article"
    pdf = "pdf"
    youtube = "youtube"


class ContentRequest(BaseModel):
    url: AnyHttpUrl
    language: str = "en"


class ContentMediaKind(StrEnum):
    image = "image"


class ContentMedia(BaseModel):
    kind: ContentMediaKind = ContentMediaKind.image
    url: str
    alt: str | None = None
    caption: str | None = None


class ContentBlockKind(StrEnum):
    text = "text"
    image = "image"


class ContentBlock(BaseModel):
    kind: ContentBlockKind
    text: str | None = None
    media: ContentMedia | None = None


class ContentResponse(BaseModel):
    url: str
    title: str | None = None
    kind: ContentKind
    source: str
    text: str
    language: str | None = None
    segments: list[CaptionSegment] = Field(default_factory=list)
    media: list[ContentMedia] = Field(default_factory=list)
    blocks: list[ContentBlock] = Field(default_factory=list)


class ConsumeRequest(ContentRequest):
    remember: bool = True
    research: bool = True
    # Run the main Ollama summary. Kept fast by disabling analysis "thinking".
    analyze: bool = True


class DiscussMessage(BaseModel):
    role: str
    content: str


class DiscussRequest(BaseModel):
    question: str
    context: str = ""
    title: str | None = None
    history: list[DiscussMessage] = Field(default_factory=list)


class Highlight(BaseModel):
    text: str
    why: str
    summary: str | None = None
    caption: str | None = None
    start: float | None = None
    end: float | None = None
    timestamp: str | None = None
    end_timestamp: str | None = None


class Chapter(BaseModel):
    title: str
    summary: str
    caption: str | None = None
    start: float | None = None
    end: float | None = None
    timestamp: str | None = None
    end_timestamp: str | None = None


class TermExplanation(BaseModel):
    term: str
    explanation: str


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


class ResearchHighlight(BaseModel):
    title: str
    url: str
    point: str
    why_it_matters: str


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


class ConsumptionAnalysis(BaseModel):
    summary: str
    summary_points: list[str] = Field(default_factory=list)
    tldr: str | None = None
    reasoning_summary: str | None = None
    reading_flow: list[str] = Field(default_factory=list)
    context_helpers: list[str] = Field(default_factory=list)
    glossary: list[TermExplanation] = Field(default_factory=list)
    research_context: list[str] = Field(default_factory=list)
    research_highlights: list[ResearchHighlight] = Field(default_factory=list)
    deep_dive_questions: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    novel_points: list[str] = Field(default_factory=list)
    already_known: list[str] = Field(default_factory=list)
    highlights: list[Highlight] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)


class AgentTrace(BaseModel):
    name: str
    status: str
    summary: str
    details: list[str] = Field(default_factory=list)


class ConsumeResponse(BaseModel):
    content: ContentResponse
    analysis: ConsumptionAnalysis
    research_results: list[ResearchResult] = Field(default_factory=list)
    research_documents: list[ResearchDocument] = Field(default_factory=list)
    knowledge_matches: list[KnowledgeMatch] = Field(default_factory=list)
    agent_traces: list[AgentTrace] = Field(default_factory=list)
    # Shareable "defluff-yt" highlight-player link for YouTube sources with timed
    # highlights; None otherwise. See app.highlight_url.
    highlight_url: str | None = None


class ConsumeStreamEvent(BaseModel):
    type: str
    trace: AgentTrace | None = None
    result: ResearchResult | None = None
    content: ContentResponse | None = None
    analysis: ConsumptionAnalysis | None = None
    highlight: Highlight | None = None
    chapter: Chapter | None = None
    response: ConsumeResponse | None = None
    message: str | None = None


class UrlRecord(BaseModel):
    id: int
    url: str
    status: UrlStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
