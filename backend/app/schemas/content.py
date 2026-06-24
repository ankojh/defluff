from enum import StrEnum

from pydantic import AnyHttpUrl, BaseModel, Field

from app.schemas.captions import CaptionSegment


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
