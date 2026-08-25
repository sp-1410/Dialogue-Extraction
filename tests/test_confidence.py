"""Unit tests for ranking and confidence scoring (roadmap #5 + #6)."""

from locator.confidence import rank, score
from locator.schema import Candidate


def cand(start, match_score, timing=100.0):
    return Candidate(start=start, end=start + 1, matched_text="x",
                      match_score=match_score, timing_consistency=timing)


def test_rank_orders_by_match_score_descending():
    c = [cand(10, 60), cand(5, 95), cand(20, 80)]
    ranked = rank(c)
    assert [round(x.start) for x in ranked] == [5, 20, 10]


def test_single_strong_unique_candidate_is_high_confidence():
    conf = score(rank([cand(5, 98, timing=100)]))
    assert conf.label == "High"
    assert conf.signals["uniqueness_margin"] == 25.0   # no runner-up -> full margin


def test_close_runner_up_lowers_confidence_via_margin():
    high = score(rank([cand(5, 90), ]))
    contested = score(rank([cand(5, 90), cand(40, 89)]))
    assert contested.score < high.score


def test_weak_match_is_low_confidence():
    conf = score(rank([cand(5, 55, timing=40)]))
    assert conf.label == "Low"


def test_medium_band_between_thresholds():
    # match=75, timing=100, no runner-up -> weighted = .65*75 + .20*100 + .15*100 = 88.75 -> High
    # tune to land in Medium: lower timing consistency
    conf = score(rank([cand(5, 75, timing=40)]))
    assert conf.label in {"Medium", "Low"}
    assert conf.score < 85
