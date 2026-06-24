from io import BytesIO
import logging
from urllib.parse import unquote, urlparse

import httpx
from pypdf import PdfReader

from app.content.errors import ContentError
from app.schemas import ContentBlock, ContentBlockKind, ContentKind, ContentResponse

logger = logging.getLogger(__name__)


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
