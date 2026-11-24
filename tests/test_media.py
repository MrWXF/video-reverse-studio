from app.services.media import cap_shots, fallback_segments, merge_short_shots


def test_merge_short_shots_drops_tiny_segments():
    assert merge_short_shots([0, 0.2, 3.0, 6.0], 0.8) == [(0.0, 3.0), (3.0, 6.0)]


def test_merge_short_shots_keeps_single_short_clip():
    assert merge_short_shots([0.0, 0.4], 0.8) == [(0.0, 0.4)]


def test_cap_shots_respects_limit_and_bounds():
    segments = [(float(i), float(i + 1)) for i in range(10)]
    capped = cap_shots(segments, 4)
    assert len(capped) == 4
    assert capped[0][0] == 0.0
    assert capped[-1][1] == 10.0


def test_fallback_segments_covers_duration():
    segments = fallback_segments(12.0, 24, 6.0)
    assert len(segments) == 2
    assert abs(segments[-1][1] - 12.0) < 1e-9


def test_fallback_segments_handles_unknown_duration():
    assert fallback_segments(0.0, 24) == [(0.0, 6.0)]