from app.content.transcript import (
    caption_for_range,
    format_transcript_text,
    parse_timestamp_label,
    resolved_caption_range,
)
from app.schemas import CaptionSegment


def test_caption_for_range_joins_selected_segments_verbatim() -> None:
    segments = [
        CaptionSegment(start=0.0, end=4.0, text="intro words here"),
        CaptionSegment(start=4.0, end=8.0, text="the key point is this."),
        CaptionSegment(start=8.0, end=12.0, text="later unrelated bit"),
    ]

    assert caption_for_range(segments, 4.0, 8.0) == "the key point is this."


def test_caption_for_range_keeps_overlapping_text_exactly() -> None:
    # Overlapping/rolling caption lines are kept exactly as transcribed — no
    # dedup, no reflow.
    segments = [
        CaptionSegment(start=0.0, end=5.0, text="so today we are going to"),
        CaptionSegment(start=3.0, end=8.0, text="going to talk about neural nets"),
    ]

    assert caption_for_range(segments, 0.0, 8.0) == (
        "so today we are going to going to talk about neural nets"
    )


def test_caption_for_range_guards_bad_ranges() -> None:
    segments = [CaptionSegment(start=0.0, end=4.0, text="hi there friend")]

    assert caption_for_range(segments, None, 4.0) is None
    assert caption_for_range(segments, 4.0, 4.0) is None
    assert caption_for_range([], 0.0, 4.0) is None


def test_parse_timestamp_label_accepts_video_formats() -> None:
    assert parse_timestamp_label("04:12") == 252.0
    assert parse_timestamp_label("01:02:03") == 3723.0
    assert parse_timestamp_label("bad") is None


def test_caption_for_range_prefers_timestamp_labels_over_stale_seconds() -> None:
    segments = [
        CaptionSegment(start=0.0, end=10.0, text="intro"),
        CaptionSegment(start=10.0, end=20.0, text="correct first line"),
        CaptionSegment(start=20.0, end=30.0, text="correct second line"),
        CaptionSegment(start=30.0, end=40.0, text="outro"),
    ]

    assert caption_for_range(
        segments,
        0.0,
        40.0,
        timestamp="00:10",
        end_timestamp="00:30",
    ) == "correct first line correct second line"
    assert resolved_caption_range(
        segments,
        0.0,
        40.0,
        timestamp="00:10",
        end_timestamp="00:30",
    ) == (10.0, 30.0)


def test_format_transcript_text_adds_paragraph_breaks_without_timestamps() -> None:
    text = (
        "this is the first point. this expands on it. "
        "now a second idea starts and continues with enough detail. "
        "this should still be readable."
    )

    formatted = format_transcript_text(text)

    assert formatted is not None
    assert "this is the first point." in formatted
    assert "[" not in formatted
