"""
End-to-end smoke tests against the local synthetic fixture (no network,
no dependency on the real reference video).

If tests/fixtures/sample.mp4 is missing, regenerate it with:
    powershell -File tests/make_test_clip.ps1
"""

from pathlib import Path

import pytest

import main
from locator import audio, transcribe

FIXTURE = Path(__file__).parent / "fixtures" / "sample.mp4"
TARGET = "My mind rebels at stagnation"

pytestmark = pytest.mark.skipif(
    not FIXTURE.exists(),
    reason="tests/fixtures/sample.mp4 missing - run tests/make_test_clip.ps1",
)


@pytest.fixture(scope="module")
def full_segments(tmp_path_factory):
    """Whole-file transcription with word timestamps, shared across tests
    in this module to avoid re-running Whisper for every assertion."""
    work = tmp_path_factory.mktemp("pipeline_full")
    audio_path = audio.extract_audio(FIXTURE, work / "audio.wav")
    return transcribe.transcribe_full(audio_path, "tiny", cache_dir=None, use_cache=False)


def test_full_transcript_has_three_segments(full_segments):
    assert len(full_segments) == 3


def test_full_segments_carry_word_timestamps(full_segments):
    assert all("words" in seg and len(seg["words"]) > 0 for seg in full_segments)


def test_end_to_end_full_mode_finds_target(tmp_path):
    args = main.parse_args([
        "--source", str(FIXTURE), "--dialogue", TARGET,
        "--model", "tiny", "--no-coarse-to-fine", "--no-cache",
        "--work-dir", str(tmp_path / "work"),
        "--out-image", str(tmp_path / "frame.jpg"),
        "--out-json", str(tmp_path / "result.json"),
    ])
    result = main.run(args)

    assert result.found
    assert 5.0 <= result.timestamp <= 5.5      # target line starts at ~5.2s in the fixture
    assert "stagnation" in result.recognized_text.lower()
    assert result.confidence.label in {"High", "Medium"}
    assert (tmp_path / "frame.jpg").exists()


def test_end_to_end_coarse_to_fine_finds_target(tmp_path):
    args = main.parse_args([
        "--source", str(FIXTURE), "--dialogue", TARGET,
        "--model", "tiny", "--coarse-model", "tiny", "--no-cache",
        "--work-dir", str(tmp_path / "work"),
        "--out-image", str(tmp_path / "frame.jpg"),
        "--out-json", str(tmp_path / "result.json"),
    ])
    result = main.run(args)

    assert result.found
    assert 5.0 <= result.timestamp <= 5.5
    assert "stagnation" in result.recognized_text.lower()


def test_dialogue_absent_reports_not_found(tmp_path):
    args = main.parse_args([
        "--source", str(FIXTURE), "--dialogue", "a line that was never spoken here",
        "--model", "tiny", "--no-coarse-to-fine", "--no-cache",
        "--work-dir", str(tmp_path / "work"),
        "--out-image", str(tmp_path / "frame.jpg"),
        "--out-json", str(tmp_path / "result.json"),
    ])
    result = main.run(args)
    assert not result.found
    assert result.error_stage == "matching"


def test_escalates_to_full_search_when_coarse_window_misses(monkeypatch, tmp_path):
    """Real bug found while running against the actual reference video: the
    coarse pass's segment-level matching is lenient enough to lock onto the
    WRONG window (score above its floor, but not the real occurrence). The
    fine pass then correctly finds nothing in that wrong window -- and the
    old behavior reported "not found" right there, even though the line was
    genuinely elsewhere in the video (confirmed with --no-coarse-to-fine).
    This is the fix: escalate to a full search before giving up."""
    calls = {"full": 0}

    def fake_coarse_to_fine(*a, **k):
        # Simulates the coarse pass confidently pointing at the wrong window.
        return ([{"start": 0.0, "end": 1.0, "text": "nothing relevant here", "words": []}], False)

    def fake_full(*a, **k):
        calls["full"] += 1
        words = [{"word": w, "start": 100.0 + i * 0.3, "end": 100.25 + i * 0.3}
                  for i, w in enumerate(TARGET.split())]
        return [{"start": 100.0, "end": 101.5, "text": TARGET, "words": words}]

    monkeypatch.setattr(main.transcribe, "transcribe_coarse_to_fine", fake_coarse_to_fine)
    monkeypatch.setattr(main.transcribe, "transcribe_full", fake_full)

    args = main.parse_args([
        "--source", str(FIXTURE), "--dialogue", TARGET,
        "--model", "tiny", "--coarse-model", "tiny", "--no-cache",
        "--work-dir", str(tmp_path / "work"),
        "--out-image", str(tmp_path / "frame.jpg"),
        "--out-json", str(tmp_path / "result.json"),
    ])
    result = main.run(args)

    assert calls["full"] == 1
    assert result.found
    assert result.used_full_search is True
    assert result.timestamp == pytest.approx(100.0)


def test_cli_writes_valid_json(tmp_path, capsys):
    out_json = tmp_path / "result.json"
    rc = main.main([
        "--source", str(FIXTURE), "--dialogue", TARGET,
        "--model", "tiny", "--no-coarse-to-fine", "--no-cache",
        "--work-dir", str(tmp_path / "work"),
        "--out-image", str(tmp_path / "frame.jpg"),
        "--out-json", str(out_json),
    ])
    assert rc == 0
    import json
    data = json.loads(out_json.read_text(encoding="utf-8"))
    assert data["result"]["found"] is True
    assert data["result"]["confidence"]["label"] in {"High", "Medium"}

    out = capsys.readouterr().out
    assert "Recognized dialogue:" in out
    assert "Confidence:" in out
