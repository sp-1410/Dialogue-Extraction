"""
Speech-to-text (roadmap #1: word-level timestamps, roadmap #7: efficiency).

Two things changed from the MVP here:

1. **Word-level timestamps.** `openai-whisper` can report per-word start/end
   times (`word_timestamps=True`), derived from the model's cross-attention
   weights via dynamic time warping -- not a separate forced-alignment
   model (that would be WhisperX; investigated, not implemented here, see
   approach.md section 10). These word timestamps are still an
   approximation, not a ground-truth alignment, but they're far finer
   grained than "the 3-second segment this word happened to fall in," which
   is what unlocks accurate matching (match.py) and frame refinement
   (frames.py).

2. **Coarse-to-fine transcription**, to answer roadmap #7 directly: the
   MVP transcribed the *entire* video at full fidelity even though only a
   few seconds around the answer ever mattered. Now: a cheap pass with a
   small/fast model locates an approximate window, and only that window
   (padded) is re-transcribed with word timestamps at higher fidelity. If
   the cheap pass doesn't find anything even loosely resembling the target
   (a real risk -- a worse model can simply mishear the whole line), it
   falls back to a full, whole-video fine pass rather than silently
   reporting "not found."
"""

from __future__ import annotations

import functools
from pathlib import Path

import whisper

from . import cache
from .audio import extract_audio_window
from .errors import TranscriptionError
from .match import find_rough_window


@functools.lru_cache(maxsize=4)
def _load_model(model_name: str):
    print(f"Loading Whisper model '{model_name}'...")
    return whisper.load_model(model_name)


def _transcribe_raw(audio_path: Path, model_name: str, word_timestamps: bool) -> list[dict]:
    model = _load_model(model_name)
    try:
        result = model.transcribe(str(audio_path), word_timestamps=word_timestamps)
    except Exception as e:  # whisper/ffmpeg failures surface as varied exception types
        raise TranscriptionError(f"Whisper transcription failed: {e}") from e
    return result["segments"]


def transcribe_full(audio_path: Path, model_name: str, cache_dir: Path | None,
                     use_cache: bool = True) -> list[dict]:
    """Transcribe the whole file with word timestamps. Cache key excludes
    the target dialogue -- a full transcript doesn't depend on what you're
    later going to search for in it, so it's reusable across searches."""
    key = None
    if use_cache and cache_dir is not None:
        audio_hash = cache.hash_file(audio_path)
        key = cache.make_key(audio_hash, model_name, "full", "words")
        cached = cache.load(cache_dir, key)
        if cached is not None:
            print("Transcript cache hit - skipping transcription.")
            return cached

    print(f"Transcribing with Whisper ({model_name})... this can take a while.")
    segments = _transcribe_raw(audio_path, model_name, word_timestamps=True)

    if key is not None:
        cache.save(cache_dir, key, segments)
    return segments


def transcribe_coarse_to_fine(audio_path: Path, target_dialogue: str,
                               coarse_model: str, fine_model: str,
                               cache_dir: Path | None, work_dir: Path,
                               use_cache: bool = True,
                               pad_seconds: float = 5.0) -> tuple[list[dict], bool]:
    """Returns (segments, used_full_fallback)."""
    audio_hash = cache.hash_file(audio_path) if (use_cache and cache_dir) else None

    # --- coarse pass: cheap model, whole file, segment-level only ---
    coarse_segments = None
    coarse_key = None
    if audio_hash is not None:
        coarse_key = cache.make_key(audio_hash, coarse_model, "coarse")
        coarse_segments = cache.load(cache_dir, coarse_key)
    if coarse_segments is None:
        print(f"Coarse pass: transcribing with Whisper ({coarse_model})...")
        coarse_segments = _transcribe_raw(audio_path, coarse_model, word_timestamps=False)
        if coarse_key is not None:
            cache.save(cache_dir, coarse_key, coarse_segments)

    window = find_rough_window(coarse_segments, target_dialogue)
    if window is None:
        print("Coarse pass found nothing resembling the target dialogue - "
              "falling back to a full fine-grained transcription.")
        return transcribe_full(audio_path, fine_model, cache_dir, use_cache), True

    start, end = window
    padded_start = max(0.0, start - pad_seconds)
    duration = (end - start) + 2 * pad_seconds

    fine_key = None
    if audio_hash is not None:
        from .match import normalize
        fine_key = cache.make_key(audio_hash, coarse_model, fine_model, "fine",
                                   normalize(target_dialogue))
        cached = cache.load(cache_dir, fine_key)
        if cached is not None:
            print("Fine-pass cache hit - skipping window transcription.")
            return cached, False

    # --- fine pass: only the padded window, higher-fidelity model, word timestamps ---
    window_audio = work_dir / "window.wav"
    extract_audio_window(audio_path, padded_start, duration, window_audio)
    print(f"Fine pass: re-transcribing {duration:.1f}s window with Whisper ({fine_model})...")
    relative_segments = _transcribe_raw(window_audio, fine_model, word_timestamps=True)

    # Shift every timestamp in the window back into the full video's timeline.
    for seg in relative_segments:
        seg["start"] += padded_start
        seg["end"] += padded_start
        for w in seg.get("words", []):
            w["start"] += padded_start
            w["end"] += padded_start

    if fine_key is not None:
        cache.save(cache_dir, fine_key, relative_segments)
    return relative_segments, False
