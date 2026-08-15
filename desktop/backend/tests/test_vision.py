from tracecue_desktop.vision import Track, evaluate_tracks


def test_line_crossing_requires_a_track_to_change_sides() -> None:
    track = Track(
        1,
        "person",
        (0, 0, 1, 1),
        3,
        [
            (0, 0.35, 0.50, 0.90),
            (1, 0.44, 0.50, 0.88),
            (2, 0.56, 0.50, 0.86),
            (3, 0.65, 0.50, 0.84),
        ],
    )
    result = evaluate_tracks(
        [track],
        event_type="line_crossing",
        overlays=[{"kind": "line", "width": 1000, "height": 1000, "points": [[500, 0], [500, 1000]]}],
        fps=5,
        frame_count=4,
        detection_count=4,
        model_id="fixture",
    )

    assert result.verdict == "confirmed_trigger"
    assert result.trigger_offset_ms == 400
    assert result.target_classes == ("person",)


def test_target_that_stays_on_one_side_is_not_confirmed() -> None:
    track = Track(
        1,
        "car",
        (0, 0, 1, 1),
        2,
        [(0, 0.20, 0.50, 0.8), (1, 0.25, 0.50, 0.8), (2, 0.30, 0.50, 0.8)],
    )
    result = evaluate_tracks(
        [track],
        event_type="line_crossing",
        overlays=[{"kind": "line", "width": 1000, "height": 1000, "points": [[500, 0], [500, 1000]]}],
        fps=5,
        frame_count=3,
        detection_count=3,
        model_id="fixture",
    )

    assert result.verdict == "target_present_no_trigger"
    assert result.trigger_offset_ms is None


def test_line_crossing_outside_the_configured_segment_is_not_confirmed() -> None:
    track = Track(
        1,
        "person",
        (0, 0, 1, 1),
        2,
        [(0, 0.40, 0.80, 0.9), (1, 0.50, 0.80, 0.9), (2, 0.60, 0.80, 0.9)],
    )
    result = evaluate_tracks(
        [track],
        event_type="line_crossing",
        overlays=[{
            "kind": "line", "width": 1000, "height": 1000,
            "points": [[500, 400], [500, 600]],
        }],
        fps=5,
        frame_count=3,
        detection_count=3,
        model_id="fixture",
    )

    assert result.verdict == "target_present_no_trigger"


def test_region_intrusion_requires_outside_to_inside_transition() -> None:
    track = Track(
        1,
        "person",
        (0, 0, 1, 1),
        2,
        [(0, 0.20, 0.50, 0.9), (1, 0.35, 0.50, 0.9), (2, 0.50, 0.50, 0.9)],
    )
    result = evaluate_tracks(
        [track],
        event_type="region_intrusion",
        overlays=[{
            "kind": "polygon", "width": 1000, "height": 1000,
            "points": [[400, 400], [600, 400], [600, 600], [400, 600]],
        }],
        fps=5,
        frame_count=3,
        detection_count=3,
        model_id="fixture",
    )

    assert result.verdict == "confirmed_trigger"
    assert result.trigger_offset_ms == 400


def test_no_tracks_is_weak_negative_evidence() -> None:
    result = evaluate_tracks(
        [],
        event_type="line_crossing",
        overlays=[{"kind": "line", "width": 1000, "height": 1000, "points": [[0, 0], [1000, 1000]]}],
        fps=5,
        frame_count=20,
        detection_count=0,
        model_id="fixture",
    )

    assert result.verdict == "no_supported_target_detected"
    assert result.confidence is None
