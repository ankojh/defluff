import pytest

from app.integrations import captions
from app.integrations.captions import CaptionError, get_captions_for_url
from app.schemas import CaptionSegment, CaptionSource


def test_get_captions_uses_youtube_track_without_audio(monkeypatch) -> None:
    def fail_transcribe(_: str) -> list[CaptionSegment]:
        pytest.fail("audio transcription should not run when YouTube captions are available")

    monkeypatch.setattr(
        captions,
        "_extract_video_info",
        lambda _: {
            "title": "Video title",
            "thumbnail": "https://example.com/thumb.jpg",
            "subtitles": {
                "en": [{"url": "https://example.com/captions.json", "ext": "json3"}],
            },
        },
    )
    monkeypatch.setattr(
        captions,
        "_download_and_parse_caption_track",
        lambda _: [CaptionSegment(start=1, end=2, text="caption text")],
    )
    monkeypatch.setattr(captions, "_transcribe_audio", fail_transcribe)

    response = get_captions_for_url("https://www.youtube.com/watch?v=abc", "en")

    assert response.source == CaptionSource.youtube
    assert response.segments == [CaptionSegment(start=1, end=2, text="caption text")]


def test_get_captions_falls_back_to_audio_when_track_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        captions,
        "_extract_video_info",
        lambda _: {"title": "Video title", "subtitles": {}, "automatic_captions": {}},
    )
    monkeypatch.setattr(
        captions,
        "_transcribe_audio",
        lambda _: [CaptionSegment(start=3, end=4, text="whisper text")],
    )

    response = get_captions_for_url("https://www.youtube.com/watch?v=abc", "en")

    assert response.source == CaptionSource.whisper
    assert response.segments == [CaptionSegment(start=3, end=4, text="whisper text")]


def test_get_captions_falls_back_to_audio_when_track_is_unusable(monkeypatch) -> None:
    monkeypatch.setattr(
        captions,
        "_extract_video_info",
        lambda _: {
            "title": "Video title",
            "subtitles": {
                "en": [{"url": "https://example.com/captions.json", "ext": "json3"}],
            },
        },
    )
    monkeypatch.setattr(
        captions,
        "_download_and_parse_caption_track",
        lambda _: (_ for _ in ()).throw(CaptionError("caption download failed")),
    )
    monkeypatch.setattr(
        captions,
        "_transcribe_audio",
        lambda _: [CaptionSegment(start=5, end=6, text="fallback text")],
    )

    response = get_captions_for_url("https://www.youtube.com/watch?v=abc", "en")

    assert response.source == CaptionSource.whisper
    assert response.segments == [CaptionSegment(start=5, end=6, text="fallback text")]
