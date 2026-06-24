import logging
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.core.config import settings
from app.integrations.captions.errors import CaptionError
from app.integrations.captions.youtube import _cookie_options
from app.schemas import CaptionSegment

logger = logging.getLogger(__name__)


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
