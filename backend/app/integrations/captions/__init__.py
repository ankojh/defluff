"""YouTube caption retrieval: prefer published/auto captions, else transcribe.

``get_captions_for_url`` references the yt-dlp and whisper helpers as module
globals (imported below) so tests can monkeypatch them on this package.
"""

import logging

from app.integrations.captions.errors import CaptionError
from app.integrations.captions.whisper import _transcribe_audio
from app.integrations.captions.youtube import (
    _download_and_parse_caption_track,
    _extract_video_info,
    _select_caption_track,
)
from app.schemas import CaptionResponse, CaptionSegment, CaptionSource

logger = logging.getLogger(__name__)

__all__ = ["CaptionError", "get_captions_for_url"]


def get_captions_for_url(url: str, language: str = "en") -> CaptionResponse:
    logger.info("captions.start url=%s language=%s", url, language)
    info = _extract_video_info(url)
    title = info.get("title")
    thumbnail_url = info.get("thumbnail")

    caption_track = _select_caption_track(info, language)
    if caption_track is not None:
        logger.info(
            "captions.youtube_track_found url=%s language=%s ext=%s",
            url,
            caption_track["language"],
            caption_track.get("ext"),
        )
        try:
            segments = _download_and_parse_caption_track(caption_track)
        except CaptionError as error:
            logger.info("captions.youtube_track_unusable url=%s error=%s", url, error)
        else:
            if segments:
                logger.info("captions.youtube_ready url=%s segments=%d", url, len(segments))
                return CaptionResponse(
                    url=url,
                    title=title,
                    language=caption_track["language"],
                    source=CaptionSource.youtube,
                    text=_segments_to_text(segments),
                    segments=segments,
                    thumbnail_url=thumbnail_url,
                )

            logger.info("captions.youtube_track_empty url=%s", url)
    else:
        logger.info("captions.youtube_track_missing url=%s language=%s", url, language)

    logger.info("captions.audio_fallback_needed url=%s", url)
    segments = _transcribe_audio(url)
    logger.info("captions.whisper_ready url=%s segments=%d", url, len(segments))
    return CaptionResponse(
        url=url,
        title=title,
        language=language,
        source=CaptionSource.whisper,
        text=_segments_to_text(segments),
        segments=segments,
        thumbnail_url=thumbnail_url,
    )


def _segments_to_text(segments: list[CaptionSegment]) -> str:
    return "\n".join(
        f"[{_format_seconds(segment.start)} -> {_format_seconds(segment.end)}] {segment.text}"
        for segment in segments
    )


def _format_seconds(value: float) -> str:
    total_seconds = int(value)
    milliseconds = int((value - total_seconds) * 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"
