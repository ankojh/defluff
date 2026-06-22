"""Transcript slicing helpers for caption-backed timed summaries."""

from __future__ import annotations

import re

from app.models import CaptionSegment


def parse_timestamp_label(value: str | None) -> float | None:
    if not value:
        return None

    parts = value.strip().split(":")
    if not 1 <= len(parts) <= 3:
        return None

    try:
        numbers = [float(part) for part in parts]
    except ValueError:
        return None

    if len(numbers) == 1:
        return numbers[0]
    if len(numbers) == 2:
        minutes, seconds = numbers
        return minutes * 60 + seconds

    hours, minutes, seconds = numbers
    return hours * 3600 + minutes * 60 + seconds


def resolved_caption_range(
    segments: list[CaptionSegment],
    start: float | None,
    end: float | None,
    timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> tuple[float, float] | None:
    if not segments:
        return None

    resolved_start = parse_timestamp_label(timestamp)
    resolved_end = parse_timestamp_label(end_timestamp)

    if resolved_start is None:
        resolved_start = start
    if resolved_end is None:
        resolved_end = end

    if resolved_start is None or resolved_end is None or resolved_end <= resolved_start:
        return None

    first_start = min(segment.start for segment in segments)
    last_end = max(segment.end for segment in segments)
    resolved_start = max(first_start, resolved_start)
    resolved_end = min(last_end, resolved_end)

    if resolved_end <= resolved_start:
        return None

    return resolved_start, resolved_end


def caption_for_range(
    segments: list[CaptionSegment],
    start: float | None,
    end: float | None,
    timestamp: str | None = None,
    end_timestamp: str | None = None,
) -> str | None:
    resolved = resolved_caption_range(segments, start, end, timestamp, end_timestamp)
    if resolved is None:
        return None

    resolved_start, resolved_end = resolved
    parts = [
        segment.text.strip()
        for segment in segments
        if segment.end > resolved_start and segment.start < resolved_end and segment.text.strip()
    ]
    text = " ".join(parts)
    return text or None


def format_transcript_text(text: str | None) -> str | None:
    if not text:
        return None

    normalized = " ".join(text.split())
    if not normalized:
        return None

    sentences = re_split_sentences(normalized)
    paragraphs: list[str] = []
    current: list[str] = []
    current_chars = 0
    for sentence in sentences:
        if current and current_chars + len(sentence) > 620:
            paragraphs.append(" ".join(current))
            current = []
            current_chars = 0
        current.append(sentence)
        current_chars += len(sentence)

    if current:
        paragraphs.append(" ".join(current))

    return "\n\n".join(paragraphs)


def re_split_sentences(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence.strip()
    ]
