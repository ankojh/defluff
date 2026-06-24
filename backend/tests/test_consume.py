from app.consume import _enrich_timed_analysis, _make_highlights_exclusive
from app.models import CaptionSegment, ConsumptionAnalysis, ContentKind, ContentResponse, Highlight


def _video(segments_end: float = 200.0) -> ContentResponse:
    segments = [
        CaptionSegment(start=float(t), end=float(t + 10), text=f"line at {t}")
        for t in range(0, int(segments_end), 10)
    ]
    return ContentResponse(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        kind=ContentKind.youtube,
        source="youtube",
        text="t",
        segments=segments,
    )


def _h(start: float, end: float, text: str = "h") -> Highlight:
    return Highlight(text=text, why="w", start=start, end=end)


def _assert_non_overlapping(highlights: list[Highlight]) -> None:
    timed = [(h.start, h.end) for h in highlights if h.start is not None and h.end is not None]
    for (s1, e1), (s2, e2) in zip(timed, timed[1:]):
        assert e1 <= s2, f"ranges overlap: ({s1},{e1}) then ({s2},{e2})"


def test_overlapping_highlight_is_clipped_to_abut_previous() -> None:
    content = _video()
    result = _make_highlights_exclusive(content, [_h(0, 10, "a"), _h(5, 20, "b")])

    assert len(result) == 2
    assert (result[0].start, result[0].end) == (0, 10)
    assert (result[1].start, result[1].end) == (10, 20)  # clipped up from 5
    assert result[1].timestamp == "00:10"  # display time re-derived
    _assert_non_overlapping(result)


def test_fully_contained_highlight_is_dropped() -> None:
    content = _video()
    result = _make_highlights_exclusive(content, [_h(0, 30, "a"), _h(5, 20, "b")])

    assert [h.text for h in result] == ["a"]


def test_abutting_highlights_are_left_unchanged() -> None:
    content = _video()
    original = [_h(0, 5, "a"), _h(5, 10, "b")]
    result = _make_highlights_exclusive(content, original)

    assert [(h.start, h.end) for h in result] == [(0, 5), (5, 10)]


def test_untimed_highlights_pass_through() -> None:
    content = _video()
    untimed = Highlight(text="no time", why="w")
    result = _make_highlights_exclusive(content, [untimed])

    assert result == [untimed]


def test_enrich_timed_analysis_dedupes_overlaps() -> None:
    content = _video()
    analysis = ConsumptionAnalysis(
        summary="s",
        highlights=[_h(45, 90, "later"), _h(0, 60, "earlier")],
    )

    enriched = _enrich_timed_analysis(content, analysis)

    _assert_non_overlapping(enriched.highlights)
