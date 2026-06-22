from io import BytesIO
import re
import logging
from urllib.parse import unquote, urldefrag, urljoin, urlparse

import httpx
from lxml import etree
import lxml.html
from pypdf import PdfReader
import trafilatura

from app.captions import CaptionError, get_captions_for_url
from app.models import ContentBlock, ContentBlockKind, ContentKind, ContentMedia, ContentResponse

logger = logging.getLogger(__name__)


class ContentError(Exception):
    pass


def get_content_for_url(url: str, language: str = "en") -> ContentResponse:
    if _is_youtube_url(url):
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


def _is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def _is_probably_pdf_url(url: str) -> bool:
    parsed = urlparse(url)
    return unquote(parsed.path).lower().endswith(".pdf")


def _extract_pdf(url: str) -> ContentResponse:
    logger.info("content.pdf_fetch_started url=%s", url)
    try:
        response = httpx.get(url, follow_redirects=True, timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise ContentError(f"Could not fetch PDF URL: {error}") from error

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
        raise ContentError("URL did not return a PDF document.")

    logger.info(
        "content.pdf_fetch_ready url=%s bytes=%d content_type=%s",
        url,
        len(response.content),
        content_type or "unknown",
    )

    try:
        reader = PdfReader(BytesIO(response.content))
    except Exception as error:
        raise ContentError("Could not read PDF document.") from error

    page_texts: list[str] = []
    blocks: list[ContentBlock] = []
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""

        page_text = _clean_pdf_text(page_text)
        if not page_text:
            continue

        page_texts.append(page_text)
        blocks.append(
            ContentBlock(
                kind=ContentBlockKind.text,
                text=f"Page {page_number}\n{page_text}",
            )
        )

    text = "\n\n".join(page_texts).strip()
    if not text:
        raise ContentError("Could not extract readable text from the PDF.")

    title = _pdf_title(reader, url)
    logger.info(
        "content.pdf_extract_ready url=%s pages=%d text_chars=%d",
        url,
        len(reader.pages),
        len(text),
    )

    return ContentResponse(
        url=url,
        title=title,
        kind=ContentKind.pdf,
        source="pdf",
        text=text,
        blocks=blocks,
    )


def _clean_pdf_text(text: str) -> str:
    lines = [line.strip() for line in text.replace("\x00", "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _pdf_title(reader: PdfReader, url: str) -> str | None:
    metadata_title = None
    try:
        if reader.metadata is not None:
            metadata_title = reader.metadata.title
    except Exception:
        metadata_title = None

    if metadata_title and metadata_title.strip():
        return metadata_title.strip()

    filename = unquote(urlparse(url).path.rsplit("/", maxsplit=1)[-1])
    if filename:
        return filename.removesuffix(".pdf").replace("-", " ").replace("_", " ").strip() or None

    return None


def _extract_article(url: str) -> ContentResponse:
    logger.info("content.article_fetch_started url=%s", url)
    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        raise ContentError("Could not fetch the URL.")
    logger.info("content.article_fetch_ready url=%s html_chars=%d", url, len(downloaded))

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        output_format="txt",
        url=url,
    )
    if text is None or not text.strip():
        raise ContentError("Could not extract readable article content from the URL.")
    logger.info("content.article_extract_ready url=%s text_chars=%d", url, len(text.strip()))

    metadata = trafilatura.extract_metadata(downloaded)
    title = metadata.title if metadata is not None else None
    blocks = _extract_ordered_article_blocks(downloaded, url)
    media = [block.media for block in blocks if block.media is not None]
    logger.info(
        "content.article_blocks_ready url=%s blocks=%d media=%d",
        url,
        len(blocks),
        len(media),
    )

    return ContentResponse(
        url=url,
        title=title,
        kind=ContentKind.article,
        source="article",
        text=text.strip(),
        media=media,
        blocks=blocks if blocks else [ContentBlock(kind=ContentBlockKind.text, text=text.strip())],
    )


def _extract_ordered_article_blocks(raw_html: str, page_url: str) -> list[ContentBlock]:
    try:
        document = lxml.html.fromstring(raw_html)
    except (TypeError, ValueError, etree.ParserError):
        return []

    root = _main_content_root(document)
    blocks: list[ContentBlock] = []
    seen_urls: set[str] = set()
    seen_text: set[str] = set()

    for element in root.iterdescendants():
        if _is_ignored_element(element) or _has_ignored_ancestor(element, root):
            continue

        tag = _tag_name(element)
        if tag == "img":
            image = _content_image_from_element(element, page_url, seen_urls)
            if image is not None:
                blocks.append(ContentBlock(kind=ContentBlockKind.image, media=image))
            continue

        if tag in _TEXT_BLOCK_TAGS and not _has_text_block_ancestor(element, root):
            text = _clean_text(element.text_content())
            if text is not None and text not in seen_text and not _looks_like_boilerplate(text):
                seen_text.add(text)
                blocks.append(ContentBlock(kind=ContentBlockKind.text, text=text))

        if len(blocks) >= 500:
            break

    return blocks


_TEXT_BLOCK_TAGS = {
    "blockquote",
    "dd",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "p",
    "pre",
}

_IGNORED_TAGS = {
    "aside",
    "button",
    "footer",
    "form",
    "header",
    "iframe",
    "nav",
    "noscript",
    "script",
    "style",
    "svg",
}


def _main_content_root(document: lxml.html.HtmlElement) -> lxml.html.HtmlElement:
    selectors = (
        '//article[.//p or .//img]',
        '//*[@id="mw-content-text"][.//p or .//img]',
        '//main[.//p or .//img]',
        '//*[@role="main"][.//p or .//img]',
        '//*[contains(concat(" ", normalize-space(@class), " "), " article-body ")][.//p or .//img]',
        '//*[contains(concat(" ", normalize-space(@class), " "), " post-content ")][.//p or .//img]',
        '//*[contains(concat(" ", normalize-space(@class), " "), " entry-content ")][.//p or .//img]',
    )

    for selector in selectors:
        matches = document.xpath(selector)
        if matches:
            return max(matches, key=lambda element: len(element.text_content()))

    body = document.find("body")
    return body if body is not None else document


def _tag_name(element: lxml.html.HtmlElement) -> str:
    tag = element.tag
    return tag.lower() if isinstance(tag, str) else ""


def _is_ignored_element(element: lxml.html.HtmlElement) -> bool:
    tag = _tag_name(element)
    if tag in _IGNORED_TAGS:
        return True

    marker = " ".join(
        value
        for value in (
            element.get("class"),
            element.get("id"),
            element.get("role"),
            element.get("aria-label"),
        )
        if value
    ).lower()
    return any(
        term in marker
        for term in (
            "advert",
            "breadcrumb",
            "byline",
            "cookie",
            "footer",
            "header",
            "menu",
            "newsletter",
            "promo",
            "related",
            "share",
            "sidebar",
            "social",
            "sponsor",
            "subscribe",
            "toolbar",
        )
    )


def _has_text_block_ancestor(
    element: lxml.html.HtmlElement,
    root: lxml.html.HtmlElement,
) -> bool:
    parent = element.getparent()
    while parent is not None and parent is not root:
        if _tag_name(parent) in _TEXT_BLOCK_TAGS:
            return True
        parent = parent.getparent()

    return False


def _has_ignored_ancestor(
    element: lxml.html.HtmlElement,
    root: lxml.html.HtmlElement,
) -> bool:
    parent = element.getparent()
    while parent is not None and parent is not root:
        if _is_ignored_element(parent):
            return True
        parent = parent.getparent()

    return False


def _content_image_from_element(
    image: lxml.html.HtmlElement,
    page_url: str,
    seen_urls: set[str],
) -> ContentMedia | None:
    if not _is_probably_content_image(image):
        return None

    image_url = _normalize_image_url(_image_source(image), page_url)
    if image_url is None or image_url in seen_urls:
        return None

    seen_urls.add(image_url)
    return ContentMedia(
        url=image_url,
        alt=_clean_text(image.get("alt") or image.get("title")),
        caption=_figure_caption(image),
    )


def _is_probably_content_image(image: lxml.html.HtmlElement) -> bool:
    marker = " ".join(
        value
        for value in (image.get("class"), image.get("id"), image.get("role"), image.get("alt"))
        if value
    ).lower()
    if any(
        term in marker
        for term in (
            "avatar",
            "badge",
            "button",
            "emoji",
            "icon",
            "logo",
            "pixel",
            "profile",
            "spacer",
            "sprite",
            "tracking",
        )
    ):
        return False

    width = _dimension_value(image.get("width"))
    height = _dimension_value(image.get("height"))
    if width is not None and width < 80:
        return False
    if height is not None and height < 80:
        return False

    return True


def _dimension_value(value: str | None) -> int | None:
    if value is None:
        return None

    match = re.match(r"^\s*(\d+)", value)
    return int(match.group(1)) if match else None


def _image_source(image: lxml.html.HtmlElement) -> str | None:
    for attribute in ("src", "data-src", "data-original", "data-lazy-src"):
        value = image.get(attribute)
        if value:
            return value

    for attribute in ("srcset", "data-srcset"):
        value = image.get(attribute)
        if value:
            return _srcset_best_candidate(value)

    return None


def _srcset_best_candidate(srcset: str) -> str | None:
    candidates = [candidate.strip().split(" ", maxsplit=1)[0] for candidate in srcset.split(",")]
    candidates = [candidate for candidate in candidates if candidate]
    return candidates[-1] if candidates else None


def _normalize_image_url(value: str | None, page_url: str) -> str | None:
    if value is None:
        return None

    value = value.strip()
    if not value or value.startswith("data:") or value.startswith("blob:"):
        return None

    absolute_url = urljoin(page_url, value)
    parsed = urlparse(absolute_url)
    if parsed.scheme not in ("http", "https"):
        return None
    if _is_site_chrome_image(parsed):
        return None

    return urldefrag(absolute_url).url


def _is_site_chrome_image(parsed_url) -> bool:
    path = parsed_url.path.lower()
    url = parsed_url.geturl().lower()

    if "centralautologin" in url:
        return True
    if "/static/images/" in path or "/w/resources/assets/" in path:
        return True

    match = re.search(r"/(\d+)px-[^/]+$", path)
    return match is not None and int(match.group(1)) < 80


def _looks_like_boilerplate(text: str) -> bool:
    lowered = text.lower()
    if len(text) < 2:
        return True
    return lowered in {
        "advertisement",
        "close",
        "edit",
        "jump to content",
        "learn more",
        "menu",
        "read more",
        "share",
        "sign in",
        "subscribe",
    }


def _figure_caption(image: lxml.html.HtmlElement) -> str | None:
    captions = image.xpath("ancestor::figure[1]//figcaption")
    if not captions:
        return None

    return _clean_text(captions[0].text_content())


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None

    cleaned = " ".join(value.split())
    return cleaned or None
