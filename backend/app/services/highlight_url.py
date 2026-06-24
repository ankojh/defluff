"""Build shareable links to the standalone "defluff-yt" highlight player.

The player is a separate static page. It decodes everything it needs from the
URL hash (``#d=...``), so the backend never has to store anything or expose an
API — it only has to produce the URL. The hash fragment is never sent to a
server, which sidesteps request/proxy length limits and keeps the player fully
static; the page reconstructs the payload with the browser-native
``DecompressionStream("gzip")``.

URL format::

    <base>/#d=<token>

where ``<token> = base64url(gzip(utf8(json)))`` with ``=`` padding stripped and
the JSON is ``{"v": <video id or url>, "h": [{"s","e","title","summary"}, ...]}``.
"""

import base64
import gzip
import json
import re
from urllib.parse import parse_qs, urlparse

from app.core.config import settings
from app.schemas import ContentKind, ContentResponse, Highlight


def build_highlight_url(base: str, video_id: str, highlights: list[dict]) -> str:
    """Encode a highlight reel into a shareable player URL.

    ``base``       e.g. ``"https://defluff.ankojh.com"`` (trailing slash optional)
    ``video_id``   YouTube id (preferred) or any watch/youtu.be/embed/shorts URL
    ``highlights`` ``[{"s": 0, "e": 5, "title": "...", "summary": "..."}, ...]``;
                   ``s``/``e`` are seconds (int or float); ``title``/``summary``
                   are optional strings.

    The encoding is fixed because the player relies on it exactly: compact JSON
    (``separators=(",", ":")``, ``ensure_ascii=False``, UTF-8), gzip level 9,
    URL-safe base64 with ``=`` padding stripped.
    """
    payload = {"v": video_id, "h": highlights}
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    packed = base64.urlsafe_b64encode(gzip.compress(raw, 9)).rstrip(b"=").decode()
    return f"{base.rstrip('/')}/#d={packed}"


_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_video_id(url: str) -> str | None:
    """Pull the 11-character video id out of a YouTube URL, if present.

    Returns ``None`` for anything that isn't recognisably a single-video URL, so
    callers can fall back to passing the full URL (which the player also
    accepts). Keeping the bare id shortens the shared link.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")

    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/", 1)[0]
        return candidate if _VIDEO_ID.match(candidate) else None

    if host == "youtube.com" or host.endswith(".youtube.com"):
        v = parse_qs(parsed.query).get("v", [None])[0]
        if v and _VIDEO_ID.match(v):
            return v
        # /embed/<id>, /shorts/<id>, /v/<id>, /live/<id>
        match = re.match(r"^/(?:embed|shorts|v|live)/([A-Za-z0-9_-]{11})", parsed.path)
        if match:
            return match.group(1)

    return None


def _range_payload(highlight: Highlight) -> dict | None:
    """Map a timed Highlight to a player range; ``None`` if it has no time span."""
    if highlight.start is None or highlight.end is None:
        return None
    item: dict[str, object] = {"s": highlight.start, "e": highlight.end}
    # text is the headline; summary falls back to "why it matters" — the same
    # precedence the UI uses (cleanSummary ?? why). Both fields are optional, so
    # drop empties to keep the link short.
    title = (highlight.text or "").strip()
    summary = (highlight.summary or highlight.why or "").strip()
    if title:
        item["title"] = title
    if summary:
        item["summary"] = summary
    return item


def highlight_player_url(
    content: ContentResponse,
    highlights: list[Highlight],
    base: str | None = None,
) -> str | None:
    """Build a player URL for a YouTube source's timed highlights.

    Returns ``None`` when the source isn't YouTube or no highlight carries a
    start/end time (the player needs ranges to seek to).
    """
    if content.kind != ContentKind.youtube:
        return None

    ranges = [payload for highlight in highlights if (payload := _range_payload(highlight))]
    if not ranges:
        return None

    base = base or settings.defluff_yt_base
    video = youtube_video_id(content.url) or content.url
    return build_highlight_url(base, video, ranges)
