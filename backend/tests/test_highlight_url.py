import base64
import gzip
import json

from app.config import settings
from app.highlight_url import build_highlight_url, highlight_player_url, youtube_video_id
from app.models import ContentKind, ContentResponse, Highlight


def _decode(url: str) -> dict:
    token = url.split("#d=")[1]
    padded = token + "=" * (-len(token) % 4)
    return json.loads(gzip.decompress(base64.urlsafe_b64decode(padded)))


def test_build_highlight_url_round_trips() -> None:
    # The verification snippet from the spec: the player must be able to decode
    # exactly what we encode.
    url = build_highlight_url(
        "https://defluff.ankojh.com",
        "dQw4w9WgXcQ",
        [{"s": 0, "e": 5, "title": "Hook", "summary": "line1\nline2"}],
    )
    assert _decode(url) == {
        "v": "dQw4w9WgXcQ",
        "h": [{"s": 0, "e": 5, "title": "Hook", "summary": "line1\nline2"}],
    }


def test_build_highlight_url_strips_base64_padding_and_trailing_slash() -> None:
    url = build_highlight_url("https://defluff.ankojh.com/", "dQw4w9WgXcQ", [])
    token = url.split("#d=")[1]
    assert "=" not in token
    # exactly one slash between host and the hash fragment
    assert url.startswith("https://defluff.ankojh.com/#d=")


def test_build_highlight_url_preserves_non_ascii() -> None:
    url = build_highlight_url("https://x", "v", [{"s": 0, "e": 1, "title": "café 🎬"}])
    assert _decode(url)["h"][0]["title"] == "café 🎬"


def test_youtube_video_id_from_common_url_shapes() -> None:
    assert youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://youtu.be/dQw4w9WgXcQ?t=5") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert youtube_video_id("https://www.youtube.com/live/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_youtube_video_id_returns_none_for_non_video_urls() -> None:
    assert youtube_video_id("https://example.com/watch?v=dQw4w9WgXcQ") is None
    assert youtube_video_id("https://www.youtube.com/results?search_query=x") is None


def _youtube_content(url: str = "https://www.youtube.com/watch?v=dQw4w9WgXcQ") -> ContentResponse:
    return ContentResponse(url=url, kind=ContentKind.youtube, source="youtube", text="t")


def test_highlight_player_url_maps_timed_highlights() -> None:
    content = _youtube_content()
    highlights = [
        Highlight(text="The hook", why="grabs attention", start=0.0, end=5.0),
        Highlight(
            text="The evidence",
            why="why it matters",
            summary="a fuller summary",
            start=45.0,
            end=60.0,
        ),
    ]

    url = highlight_player_url(content, highlights)
    assert url is not None
    decoded = _decode(url)
    assert decoded == {
        "v": "dQw4w9WgXcQ",
        "h": [
            {"s": 0.0, "e": 5.0, "title": "The hook", "summary": "grabs attention"},
            {"s": 45.0, "e": 60.0, "title": "The evidence", "summary": "a fuller summary"},
        ],
    }


def test_highlight_player_url_uses_configured_base() -> None:
    content = _youtube_content()
    highlights = [Highlight(text="Hook", why="", start=0.0, end=5.0)]
    assert highlight_player_url(content, highlights).startswith(f"{settings.defluff_yt_base}/#d=")


def test_highlight_player_url_skips_untimed_highlights() -> None:
    content = _youtube_content()
    highlights = [
        Highlight(text="No time", why="x"),
        Highlight(text="Timed", why="y", start=10.0, end=20.0),
    ]
    decoded = _decode(highlight_player_url(content, highlights))
    assert decoded["h"] == [{"s": 10.0, "e": 20.0, "title": "Timed", "summary": "y"}]


def test_highlight_player_url_none_when_no_timed_highlights() -> None:
    content = _youtube_content()
    assert highlight_player_url(content, [Highlight(text="No time", why="x")]) is None


def test_highlight_player_url_none_for_non_youtube() -> None:
    content = ContentResponse(
        url="https://example.com/post",
        kind=ContentKind.article,
        source="article",
        text="t",
    )
    highlights = [Highlight(text="Hook", why="", start=0.0, end=5.0)]
    assert highlight_player_url(content, highlights) is None
