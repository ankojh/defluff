import logging
from urllib.parse import urlparse

from app.content.errors import ContentError
from app.integrations.captions import CaptionError, get_captions_for_url
from app.schemas import ContentBlock, ContentBlockKind, ContentKind, ContentMedia, ContentResponse

logger = logging.getLogger(__name__)


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def extract_youtube(url: str, language: str = "en") -> ContentResponse:
    logger.info("content.youtube_detected url=%s", url)
    try:
        caption_response = get_captions_for_url(url, language)
    except CaptionError as error:
        raise ContentError(str(error)) from error

    thumbnail = (
        ContentMedia(url=caption_response.thumbnail_url, alt=caption_response.title)
        if caption_response.thumbnail_url is not None
        else None
    )
    blocks = [ContentBlock(kind=ContentBlockKind.text, text=caption_response.text)]
    if thumbnail is not None:
        blocks.insert(0, ContentBlock(kind=ContentBlockKind.image, media=thumbnail))

    return ContentResponse(
        url=caption_response.url,
        title=caption_response.title,
        kind=ContentKind.youtube,
        source=caption_response.source.value,
        text=caption_response.text,
        language=caption_response.language,
        segments=caption_response.segments,
        media=[thumbnail] if thumbnail is not None else [],
        blocks=blocks,
    )
