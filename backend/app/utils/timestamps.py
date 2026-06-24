"""Timestamp formatting and parsing shared across agents, content, and services."""

from __future__ import annotations


def format_timestamp(seconds: float) -> str:
    """Format seconds as mm:ss (or hh:mm:ss past an hour)."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_timestamp_or_none(value: float | None) -> str | None:
    if value is None:
        return None
    return format_timestamp(value)


def parse_timestamp_label(value: str | None) -> float | None:
    """Parse a "ss", "mm:ss", or "hh:mm:ss" label into seconds."""
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
