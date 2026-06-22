import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import httpx
import webvtt
from faster_whisper import WhisperModel
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.config import settings
from app.models import CaptionResponse, CaptionSegment, CaptionSource

logger = logging.getLogger(__name__)


class CaptionError(Exception):
    pass


def _cookie_options() -> dict[str, Any]:
    """yt-dlp auth options so YouTube treats requests as a signed-in user.

    YouTube serves "Sign in to confirm you're not a bot" to unauthenticated
    clients; cookies from a logged-in browser (or a cookies.txt file) clear it.
    Browser cookies take precedence over a cookie file.
    """
    if settings.youtube_cookies_from_browser:
        return {"cookiesfrombrowser": (settings.youtube_cookies_from_browser,)}
    if settings.youtube_cookie_file:
        return {"cookiefile": settings.youtube_cookie_file}
    return {}


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


def _extract_video_info(url: str) -> dict[str, Any]:
    logger.info("captions.metadata_started url=%s", url)
    options = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        **_cookie_options(),
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as error:
        raise CaptionError(f"Could not read YouTube URL: {error}") from error

    if not isinstance(info, dict):
        raise CaptionError("yt-dlp returned an invalid video response")

    logger.info("captions.metadata_ready url=%s title=%r", url, info.get("title"))
    return info


def _select_caption_track(info: dict[str, Any], language: str) -> dict[str, str] | None:
    subtitles = info.get("subtitles") or {}
    automatic_captions = info.get("automatic_captions") or {}

    for caption_group in (subtitles, automatic_captions):
        language_key = _find_language_key(caption_group, language)
        if language_key is None:
            continue

        track = _find_best_caption_format(caption_group[language_key])
        if track is not None:
            return {
                "url": track["url"],
                "ext": track.get("ext", ""),
                "language": language_key,
            }

    return None


def _find_language_key(captions: dict[str, Any], language: str) -> str | None:
    preferred = [language, f"{language}-US", f"{language}-GB"]
    for key in preferred:
        if key in captions:
            return key

    for key in captions:
        if key.split("-", maxsplit=1)[0] == language:
            return key

    return None


def _find_best_caption_format(tracks: list[dict[str, Any]]) -> dict[str, Any] | None:
    for ext in ("json3", "vtt"):
        for track in tracks:
            if track.get("ext") == ext and track.get("url"):
                return track

    for track in tracks:
        if track.get("url"):
            return track

    return None


def _download_and_parse_caption_track(track: dict[str, str]) -> list[CaptionSegment]:
    logger.info("captions.track_download_started language=%s ext=%s", track["language"], track.get("ext"))
    try:
        response = httpx.get(track["url"], follow_redirects=True, timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise CaptionError(f"Could not download YouTube captions: {error}") from error

    if track.get("ext") == "json3":
        segments = _parse_json3_captions(response.text)
        logger.info("captions.track_parsed ext=json3 segments=%d", len(segments))
        return segments

    segments = _parse_vtt_captions(response.text)
    logger.info("captions.track_parsed ext=vtt segments=%d", len(segments))
    return segments


def _parse_json3_captions(raw: str) -> list[CaptionSegment]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CaptionError("Could not parse YouTube JSON captions") from error

    segments: list[CaptionSegment] = []
    for event in payload.get("events", []):
        pieces = event.get("segs") or []
        text = "".join(piece.get("utf8", "") for piece in pieces).strip()
        if not text:
            continue

        start = float(event.get("tStartMs", 0)) / 1000
        duration = float(event.get("dDurationMs", 0)) / 1000
        end = start + duration if duration > 0 else start
        segments.append(CaptionSegment(start=start, end=end, text=text))

    return segments


def _parse_vtt_captions(raw: str) -> list[CaptionSegment]:
    segments: list[CaptionSegment] = []
    for caption in webvtt.from_string(raw):
        # Strip YouTube's inline timing/styling tags (e.g. <00:00:01.234>, <c>)
        # so the stored caption text is plain words, not markup.
        text = re.sub(r"<[^>]+>", " ", caption.text)
        text = " ".join(text.split())
        if not text:
            continue

        segments.append(
            CaptionSegment(
                start=_timestamp_to_seconds(caption.start),
                end=_timestamp_to_seconds(caption.end),
                text=text,
            )
        )

    return segments


def _timestamp_to_seconds(value: str) -> float:
    hours = 0
    minute_part, second_part = value.rsplit(":", maxsplit=1)
    if ":" in minute_part:
        hour_part, minute_part = minute_part.split(":", maxsplit=1)
        hours = int(hour_part)

    return hours * 3600 + int(minute_part) * 60 + float(second_part)


def _transcribe_audio(url: str) -> list[CaptionSegment]:
    logger.info("captions.audio_download_started url=%s", url)
    with tempfile.TemporaryDirectory(prefix="defluff-audio-") as tmp_dir:
        output_template = str(Path(tmp_dir) / "audio.%(ext)s")
        options = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "outtmpl": output_template,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                }
            ],
            "quiet": True,
            **_cookie_options(),
        }

        try:
            with YoutubeDL(options) as ydl:
                ydl.download([url])
        except DownloadError as error:
            raise CaptionError(f"Could not download audio for transcription: {error}") from error

        audio_path = Path(tmp_dir) / "audio.wav"
        if not audio_path.exists():
            raise CaptionError("yt-dlp did not produce an audio file")
        logger.info("captions.audio_download_ready url=%s path=%s", url, audio_path)

        model_kwargs: dict[str, str] = {}
        if settings.whisper_compute_type != "default":
            model_kwargs["compute_type"] = settings.whisper_compute_type

        model = WhisperModel(
            settings.whisper_model,
            device=settings.whisper_device,
            **model_kwargs,
        )
        logger.info(
            "captions.whisper_transcribe_started url=%s model=%s device=%s",
            url,
            settings.whisper_model,
            settings.whisper_device,
        )
        whisper_segments, _ = model.transcribe(str(audio_path), vad_filter=True)

        return [
            CaptionSegment(start=segment.start, end=segment.end, text=segment.text.strip())
            for segment in whisper_segments
            if segment.text.strip()
        ]


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
