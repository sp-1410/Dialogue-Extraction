"""
Candidate ranking and confidence scoring (roadmap #5 + #6).

MVP recap: the first segment that matched, full stop -- no ranking if the
line occurred more than once, and no signal for "found, but shaky" versus
"found, certain."

Ranking: candidates are sorted by RapidFuzz match score, tie-broken by
timing consistency. In practice (see approach.md section 8) the reference
video only had one true occurrence, so ranking had nothing to disambiguate
there -- but the mechanism exists and is exercised by
tests/test_confidence.py against a fixture with a deliberate second,
weaker occurrence.

Confidence: a single weighted score, not a black box --

    confidence = 0.65 * match_score
               + 0.20 * timing_consistency
               + 0.15 * uniqueness_margin_scaled

  - match_score: RapidFuzz similarity of the winning window to the target.
  - timing_consistency: do the words in the window look like one fluent
    utterance (match.py)?
  - uniqueness_margin_scaled: the gap between the top candidate's score and
    the runner-up's, scaled by 4x and capped at 100. A lone strong match is
    more trustworthy than "the best of several mediocre ones" -- if there's
    no runner-up at all, this term is 100 (maximally unique) rather than
    undefined.

Bucketed as High (>=85) / Medium (65-84) / Low (<65). No signal here is
opaque or learned; every one of them can be read directly off the
candidates list in the JSON output.
"""

from __future__ import annotations

from .schema import Candidate, Confidence

WEIGHTS = {"match_score": 0.65, "timing_consistency": 0.20, "uniqueness_margin": 0.15}
HIGH_THRESHOLD = 85.0
MEDIUM_THRESHOLD = 65.0


def rank(candidates: list[Candidate]) -> list[Candidate]:
    return sorted(candidates, key=lambda c: (c.match_score, c.timing_consistency), reverse=True)


def score(ranked: list[Candidate]) -> Confidence:
    """`ranked` must be non-empty and sorted best-first (see rank())."""
    top = ranked[0]
    margin = top.match_score - ranked[1].match_score if len(ranked) > 1 else 25.0
    margin_scaled = max(0.0, min(100.0, margin * 4))

    weighted = (
        WEIGHTS["match_score"] * top.match_score
        + WEIGHTS["timing_consistency"] * top.timing_consistency
        + WEIGHTS["uniqueness_margin"] * margin_scaled
    )

    if weighted >= HIGH_THRESHOLD:
        label = "High"
    elif weighted >= MEDIUM_THRESHOLD:
        label = "Medium"
    else:
        label = "Low"

    return Confidence(
        score=weighted,
        label=label,
        signals={
            "match_score": round(top.match_score, 1),
            "timing_consistency": round(top.timing_consistency, 1),
            "uniqueness_margin": round(margin, 1),
            "candidate_count": len(ranked),
        },
    )
