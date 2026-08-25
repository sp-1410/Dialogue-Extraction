"""Unit tests for timestamp -> frame conversion and verified extraction
(roadmap #3 + #4)."""

from pathlib import Path

import pytest

from locator.frames import extract_frame, get_fps, timestamp_to_frame

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mp4"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="tests/fixtures/sample.mp4 missing - run tests/make_test_clip.ps1",
)


def test_timestamp_to_frame_rounds_rather_than_truncates():
    # MVP used int(), which truncates: int(5.29 * 25) = int(132.25) = 132.
    # round() is the fix: 132.25 rounds to 132 too, but 132.6 (5.304*25)
    # should round UP to 133, not truncate down to 132.
    assert timestamp_to_frame(5.304, 25) == 133
    assert timestamp_to_frame(5.28, 25) == 132


def test_get_fps_matches_known_fixture_rate():
    assert get_fps(FIXTURE) == pytest.approx(25.0, abs=0.1)


def test_extract_frame_lands_on_or_after_requested_frame(tmp_path):
    out = tmp_path / "frame.jpg"
    actual = extract_frame(FIXTURE, 130, out)
    assert actual >= 130
    assert out.exists() and out.stat().st_size > 0


def test_extract_frame_clamps_out_of_range_request(tmp_path):
    out = tmp_path / "frame.jpg"
    # Fixture is ~14s * 25fps =~350 frames; ask for something absurd.
    actual = extract_frame(FIXTURE, 100_000, out)
    assert actual >= 0
    assert out.exists()
