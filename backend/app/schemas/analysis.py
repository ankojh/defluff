from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AuditCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    weight: float = Field(ge=0.1, le=3.0)
    source: Literal["fixed", "dynamic"] = "fixed"


class CriterionEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=500)
    weight: float = Field(default=1.0, ge=0.1, le=3.0)
    score: float = Field(ge=0.0, le=100.0)
    issues: list[str] = Field(default_factory=list)
    smallest_repair: str = ""
    weighted_deficit: float = Field(default=0.0, ge=0.0)


class AuditEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[CriterionEvaluation] = Field(default_factory=list)
    weighted_score: float = Field(ge=0.0, le=100.0)


class AuditIteration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    iteration: int
    criterion_id: str
    before_score: float
    after_score: float
    improvement: float
    issues: list[str] = Field(default_factory=list)
    smallest_repair: str = ""


class AuditScoreSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    weighted_score: float = Field(ge=0.0, le=100.0)
    criteria: list[CriterionEvaluation] = Field(default_factory=list)


class LocalModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_duration_ms: float = 0.0


class LocalModelUsageByPurpose(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_duration_ms: float = 0.0


class AuditReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    initial_score: float
    final_score: float
    target_score: float
    iterations: list[AuditIteration] = Field(default_factory=list)
    criteria: list[AuditCriterion] = Field(default_factory=list)
    evaluations: list[AuditScoreSnapshot] = Field(default_factory=list)
    final_evaluation: AuditEvaluation
    local_model_usage: LocalModelUsage = Field(default_factory=LocalModelUsage)
    local_model_usage_by_purpose: list[LocalModelUsageByPurpose] = Field(default_factory=list)
    stopped_reason: str


class AuditLoopResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_output: str
    audit_report: AuditReport


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


class ResearchHighlight(BaseModel):
    title: str
    url: str
    point: str
    why_it_matters: str


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
    audit_report: AuditReport | None = None
