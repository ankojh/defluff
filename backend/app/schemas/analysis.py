from pydantic import BaseModel, Field


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
