from pydantic import BaseModel, Field

from app.schemas.analysis import Chapter, ConsumptionAnalysis, Highlight
from app.schemas.content import ContentRequest, ContentResponse
from app.schemas.knowledge import KnowledgeMatch
from app.schemas.research import ResearchDocument, ResearchResult


class ConsumeRequest(ContentRequest):
    remember: bool = True
    research: bool = True
    # Run the main Ollama summary. Kept fast by disabling analysis "thinking".
    analyze: bool = True


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
    # highlights; None otherwise. See app.services.highlight_url.
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
