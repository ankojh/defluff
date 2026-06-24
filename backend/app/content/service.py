import logging

from app.content.article import _extract_article
from app.content.errors import ContentError
from app.content.pdf import _extract_pdf, _is_probably_pdf_url
from app.content.youtube import extract_youtube, is_youtube_url
from app.schemas import ContentResponse

logger = logging.getLogger(__name__)


def get_content_for_url(url: str, language: str = "en") -> ContentResponse:
    if is_youtube_url(url):
        return extract_youtube(url, language)

    if _is_probably_pdf_url(url):
        logger.info("content.pdf_detected url=%s", url)
        return _extract_pdf(url)

    logger.info("content.article_detected url=%s", url)
    try:
        return _extract_article(url)
    except ContentError as article_error:
        logger.info("content.article_failed_trying_pdf url=%s error=%s", url, article_error)
        try:
            return _extract_pdf(url)
        except ContentError:
            raise article_error
