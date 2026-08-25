"""Stage 2: audio extraction, and pulling a short sub-clip for the
coarse-to-fine transcription strategy (roadmap #7)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import AudioExtractionError


def extract_audio(video_path: Path, out_path: Path) -> Path:
    """Extract mono, 16kHz audio to a wav file using ffmpeg."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-ac", "1", "-ar", "16000", "-vn",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioExtractionError(f"ffmpeg audio extraction failed:\n{result.stderr}")
    return out_path


def extract_audio_window(audio_path: Path, start: float, duration: float, out_path: Path) -> Path:
    """Cut a short sub-clip of an already-extracted wav, for re-transcribing
    just the candidate window at higher fidelity (coarse-to-fine)."""
    start = max(0.0, start)
    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(audio_path),
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise AudioExtractionError(f"ffmpeg window extraction failed:\n{result.stderr}")
    return out_path
