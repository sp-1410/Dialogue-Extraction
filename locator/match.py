"""
Dialogue matching (roadmap #1 + #2 combined).

MVP recap: matching was a single normalized substring check against each
Whisper *segment* (a whole sentence-ish chunk, several seconds long). Two
concrete problems with that:

  1. If the target line straddles a segment boundary, it's never found --
     substring search only ever looks inside one segment at a time.
  2. Any single mis-heard word anywhere in the phrase causes a total miss,
     with no partial credit and no visibility into "how close" it was.

Both are fixed by matching over the flat *word* stream (which requires
word-level timestamps -- roadmap #1) with a fuzzy, sliding-window
comparison (roadmap #2) instead of per-segment exact substring search.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .schema import Candidate

FLOOR = 70.0          # candidates below this RapidFuzz score are discarded
CLUSTER_GAP = 3.0      # seconds; candidates this close are the "same" hit
COARSE_FLOOR = 55.0    # more forgiving floor for the coarse (cheap-model) pass
MAX_INTRA_PHRASE_GAP = 2.0   # seconds; words further apart than this can't be one utterance


def normalize(text: str) -> str:
    """Lowercase, drop punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def flatten_words(segments: list[dict]) -> list[dict]:
    """Flatten Whisper's segments[].words[] into one chronological list of
    {text, norm, start, end}, dropping tokens that normalize to nothing
    (pure punctuation, e.g. a stray "--")."""
    words = []
    for seg in segments:
        for w in seg.get("words", []):
            norm = normalize(w["word"])
            if not norm:
                continue
            words.append({
                "text": w["word"].strip(),
                "norm": norm,
                "start": w["start"],
                "end": w["end"],
            })
    return words


def _timing_consistency(window_words: list[dict]) -> float:
    """0-100: how much the gaps between consecutive words in this window
    look like one fluent spoken phrase rather than a coincidental stitch of
    unrelated words. Gaps <=0.5s score 100; each additional 0.5s of the
    *largest* gap costs 30 points, floored at 0. Deliberately simple and
    stated in one sentence, per the brief's "explainable, not arbitrary"
    requirement."""
    if len(window_words) < 2:
        return 100.0
    gaps = [max(0.0, window_words[i + 1]["start"] - window_words[i]["end"])
            for i in range(len(window_words) - 1)]
    max_gap = max(gaps)
    return max(0.0, min(100.0, 100.0 - (max_gap - 0.5) / 0.5 * 30.0))


def _split_into_runs(words: list[dict]) -> list[list[dict]]:
    """Split the flat word stream wherever consecutive words are more than
    MAX_INTRA_PHRASE_GAP apart. Without this, a sliding window can span a
    long silence (or an unrelated line) and stitch two unconnected words
    into one "candidate" -- caught by tests/test_match.py, where a window
    spanning a 19-second gap scored 92% on character similarity alone
    despite being physically impossible as one spoken utterance."""
    if not words:
        return []
    runs = [[words[0]]]
    for prev, cur in zip(words, words[1:]):
        if cur["start"] - prev["end"] > MAX_INTRA_PHRASE_GAP:
            runs.append([])
        runs[-1].append(cur)
    return runs


def find_candidates(segments: list[dict], target_dialogue: str, floor: float = FLOOR) -> list[Candidate]:
    """Slide a window of ~len(target) words across the transcript's word
    stream, score each window against the target with RapidFuzz, keep
    everything above `floor`, then collapse near-duplicate overlapping
    windows down to one candidate per distinct occurrence."""
    words = flatten_words(segments)
    target_norm = normalize(target_dialogue)
    target_tokens = target_norm.split()
    t = len(target_tokens)
    if t == 0 or not words:
        return []

    raw: list[Candidate] = []
    # Window sizes span target length -1 .. +2 words, to tolerate the ASR
    # dropping or inserting a short word (e.g. "the", "a") without missing
    # the match entirely.
    for run in _split_into_runs(words):
        for w in range(max(1, t - 1), t + 3):
            for i in range(0, len(run) - w + 1):
                window = run[i:i + w]
                window_norm = " ".join(x["norm"] for x in window)
                score = fuzz.ratio(target_norm, window_norm)
                if score < floor:
                    continue
                raw.append(Candidate(
                    start=window[0]["start"],
                    end=window[-1]["end"],
                    matched_text=" ".join(x["text"] for x in window),
                    match_score=score,
                    timing_consistency=_timing_consistency(window),
                ))

    # Non-max suppression: many overlapping windows will score highly
    # around the true occurrence (w-1, w, w+1 all sliding past it). Keep
    # only the single best-scoring window per cluster of nearby timestamps.
    raw.sort(key=lambda c: c.match_score, reverse=True)
    kept: list[Candidate] = []
    for cand in raw:
        if any(abs(cand.start - k.start) < CLUSTER_GAP for k in kept):
            continue
        kept.append(cand)

    kept.sort(key=lambda c: c.start)   # chronological in the final output
    return kept


def find_rough_window(segments: list[dict], target_dialogue: str,
                       floor: float = COARSE_FLOOR) -> tuple[float, float] | None:
    """Cheap, segment-level (not word-level) locator used only for the
    *coarse* pass of coarse-to-fine transcription (roadmap #7), where the
    cheap model hasn't produced word timestamps at all. Returns the
    best-scoring segment's (start, end), or None if nothing clears the
    (deliberately more forgiving) floor."""
    target_norm = normalize(target_dialogue)
    best = None
    best_score = 0.0
    for seg in segments:
        score = fuzz.partial_ratio(target_norm, normalize(seg["text"]))
        if score > best_score:
            best_score = score
            best = seg
    if best is None or best_score < floor:
        return None
    return best["start"], best["end"]
