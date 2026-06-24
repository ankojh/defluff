import logging
import re
from urllib.parse import urldefrag, urljoin, urlparse

import lxml.html
import trafilatura
from lxml import etree

from app.content.errors import ContentError
from app.schemas import ContentBlock, ContentBlockKind, ContentKind, ContentMedia, ContentResponse

logger = logging.getLogger(__name__)


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
