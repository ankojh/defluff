"""Pydantic request/response models, split by domain.

Re-exported here so call sites can use ``from app.schemas import X`` regardless
of which submodule a model lives in.
"""

from app.schemas.analysis import (
    AuditCriterion,
    AuditEvaluation,
    AuditIteration,
    AuditLoopResult,
    AuditReport,
    AuditScoreSnapshot,
    Chapter,
    ConsumptionAnalysis,
    CriterionEvaluation,
    Highlight,
    LocalModelUsage,
    LocalModelUsageByPurpose,
    ResearchHighlight,
    TermExplanation,
)
from app.schemas.captions import (
    CaptionRequest,
    CaptionResponse,
    CaptionSegment,
    CaptionSource,
)
from app.schemas.consume import (
    AgentTrace,
    ConsumeRequest,
    ConsumeResponse,
    ConsumeStreamEvent,
)
from app.schemas.content import (
    ContentBlock,
    ContentBlockKind,
    ContentKind,
    ContentMedia,
    ContentMediaKind,
    ContentRequest,
    ContentResponse,
)
from app.schemas.discuss import DiscussMessage, DiscussRequest
from app.schemas.knowledge import KnowledgeMatch, LearnRequest
from app.schemas.research import ResearchDocument, ResearchResult, ResearchTopic
from app.schemas.urls import UrlRecord, UrlStatus, UrlSubmission

__all__ = [
    "AgentTrace",
    "AuditCriterion",
    "AuditEvaluation",
    "AuditIteration",
    "AuditLoopResult",
    "AuditReport",
    "AuditScoreSnapshot",
    "CaptionRequest",
    "CaptionResponse",
    "CaptionSegment",
    "CaptionSource",
    "Chapter",
    "ConsumeRequest",
    "ConsumeResponse",
    "ConsumeStreamEvent",
    "ConsumptionAnalysis",
    "ContentBlock",
    "ContentBlockKind",
    "ContentKind",
    "ContentMedia",
    "ContentMediaKind",
    "ContentRequest",
    "ContentResponse",
    "CriterionEvaluation",
    "DiscussMessage",
    "DiscussRequest",
    "Highlight",
    "KnowledgeMatch",
    "LearnRequest",
    "LocalModelUsage",
    "LocalModelUsageByPurpose",
    "ResearchDocument",
    "ResearchHighlight",
    "ResearchResult",
    "ResearchTopic",
    "TermExplanation",
    "UrlRecord",
    "UrlStatus",
    "UrlSubmission",
]
