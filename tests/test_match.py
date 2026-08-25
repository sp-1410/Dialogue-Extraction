"""
Unit tests for matching (roadmap #1 + #2), using hand-built word lists so
these run in milliseconds with no Whisper/ffmpeg dependency at all.
"""

from locator.match import find_candidates, find_rough_window, normalize


def words(*specs):
    """specs: (text, start, end) tuples -> Whisper-shaped segments."""
    return [{"start": specs[0][1], "end": specs[-1][2], "text": " ".join(s[0] for s in specs),
             "words": [{"word": s[0], "start": s[1], "end": s[2]} for s in specs]}]


def test_normalize_strips_case_punctuation_and_whitespace():
    assert normalize("  My Mind Rebels, at STAGNATION!!  ") == "my mind rebels at stagnation"


def test_exact_phrase_is_found():
    segs = words(
        ("My", 5.0, 5.2), ("mind", 5.2, 5.4), ("rebels", 5.4, 5.7),
        ("at", 5.7, 5.8), ("stagnation", 5.8, 6.2),
    )
    cands = find_candidates(segs, "My mind rebels at stagnation")
    assert len(cands) == 1
    assert cands[0].match_score > 95
    assert cands[0].start == 5.0


def test_one_misheard_word_still_matches_via_fuzzy_score():
    # ASR mis-hears "rebels" as "revels" -- MVP's exact substring match
    # would miss this entirely; fuzzy matching should not.
    segs = words(
        ("My", 5.0, 5.2), ("mind", 5.2, 5.4), ("revels", 5.4, 5.7),
        ("at", 5.7, 5.8), ("stagnation", 5.8, 6.2),
    )
    cands = find_candidates(segs, "My mind rebels at stagnation")
    assert len(cands) == 1
    assert 70 <= cands[0].match_score < 100


def test_phrase_spanning_a_segment_boundary_is_still_found():
    # Two Whisper segments, target line split across the boundary -- the
    # MVP's per-segment substring check could never find this.
    segs = [
        {"start": 0.0, "end": 5.4, "text": "My mind rebels",
         "words": [{"word": "My", "start": 5.0, "end": 5.2},
                    {"word": "mind", "start": 5.2, "end": 5.4},
                    {"word": "rebels", "start": 5.4, "end": 5.7}]},
        {"start": 5.7, "end": 6.2, "text": "at stagnation",
         "words": [{"word": "at", "start": 5.7, "end": 5.8},
                    {"word": "stagnation", "start": 5.8, "end": 6.2}]},
    ]
    cands = find_candidates(segs, "My mind rebels at stagnation")
    assert len(cands) == 1
    assert cands[0].match_score > 95


def test_absent_phrase_yields_no_candidates():
    segs = words(("Completely", 0.0, 0.5), ("unrelated", 0.5, 1.0), ("speech", 1.0, 1.5))
    assert find_candidates(segs, "My mind rebels at stagnation") == []


def test_overlapping_windows_around_one_occurrence_collapse_to_one_candidate():
    segs = words(
        ("My", 5.0, 5.2), ("mind", 5.2, 5.4), ("rebels", 5.4, 5.7),
        ("at", 5.7, 5.8), ("stagnation", 5.8, 6.2), ("today", 6.2, 6.5),
    )
    cands = find_candidates(segs, "My mind rebels at stagnation")
    assert len(cands) == 1   # not one candidate per sliding-window size


def test_two_distinct_occurrences_are_both_reported():
    segs = words(
        ("My", 5.0, 5.2), ("mind", 5.2, 5.4), ("rebels", 5.4, 5.7),
        ("at", 5.7, 5.8), ("stagnation", 5.8, 6.2),
        ("filler", 20.0, 20.3), ("words", 20.3, 20.6), ("here", 20.6, 20.9),
        ("My", 40.0, 40.2), ("mind", 40.2, 40.4), ("rebels", 40.4, 40.7),
        ("at", 40.7, 40.8), ("stagnation", 40.8, 41.2),
    )
    cands = find_candidates(segs, "My mind rebels at stagnation")
    assert len(cands) == 2
    assert {round(c.start, 1) for c in cands} == {5.0, 40.0}


def test_find_rough_window_locates_segment_without_word_timestamps():
    segs = [
        {"start": 0.0, "end": 3.0, "text": "This is filler speech before it"},
        {"start": 5.0, "end": 8.0, "text": "My mind rebels at stagnation"},
        {"start": 9.0, "end": 12.0, "text": "This is filler speech after it"},
    ]
    window = find_rough_window(segs, "My mind rebels at stagnation")
    assert window == (5.0, 8.0)


def test_find_rough_window_none_when_nothing_close_enough():
    segs = [{"start": 0.0, "end": 3.0, "text": "completely unrelated content"}]
    assert find_rough_window(segs, "My mind rebels at stagnation") is None
