"""
Transcript caching (roadmap #7 - efficiency).

The MVP re-transcribed the full ~54 minute reference video from scratch on
every run: about 18 minutes each time on this machine (see approach.md
section 8). That cost is pure waste on every run after the first one --
the audio doesn't change between runs while you're iterating on matching,
ranking, or confidence logic.

Cache key = hash(audio content) + whisper model name + word-timestamps flag
+ mode ("full" or "coarse"/"fine"). For coarse-to-fine mode specifically,
the *fine* pass result also depends on which window it looked at, which
depends on the target dialogue -- so the fine-pass cache key additionally
includes the normalized target dialogue. The full-transcription cache key
deliberately does NOT include the dialogue, so re-running the tool with a
different --dialogue against the same video/model still hits the cache.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def hash_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()[:16]   # short prefix is plenty collision-resistant here


def make_key(*parts: str) -> str:
    joined = "|".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:20]


def load(cache_dir: Path, key: str) -> list[dict] | None:
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None   # treat a corrupt cache entry as a miss, not a crash


def save(cache_dir: Path, key: str, segments: list[dict]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(segments, f)
