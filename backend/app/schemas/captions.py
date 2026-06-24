from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel


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
