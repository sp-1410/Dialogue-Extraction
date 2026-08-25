"""
Typed result objects, and their JSON serialization (roadmap #9).

Kept as plain stdlib `dataclasses` rather than Pydantic: this project has
one well-known output shape, not a validation-heavy API surface, so a
validation library is weight without payoff here (see approach.md's tech
stack notes).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Candidate:
    """One place in the transcript whose words plausibly match the target
    dialogue, before any is chosen as "the" answer."""
    start: float
    end: float
    matched_text: str
    match_score: float          # 0-100, RapidFuzz similarity
    timing_consistency: float   # 0-100, see confidence.py
    frame_number: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Confidence:
    score: float          # 0-100 weighted composite
    label: str            # "High" / "Medium" / "Low"
    signals: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"score": round(self.score, 1), "label": self.label, "signals": self.signals}


@dataclass
class Result:
    found: bool
    video_source: str
    target_dialogue: str
    timestamp: float | None = None
    frame_number: int | None = None
    recognized_text: str | None = None
    frame_image: str | None = None
    confidence: Confidence | None = None
    candidates: list[Candidate] = field(default_factory=list)
    used_full_search: bool = False   # True if a whole-video pass was needed
                                       # (either --no-coarse-to-fine, or the
                                       # coarse-to-fine escalation fallback)
    error: str | None = None
    error_stage: str | None = None

    def to_dict(self) -> dict:
        d = {
            "query": {
                "video_source": self.video_source,
                "target_dialogue": self.target_dialogue,
            },
            "result": {
                "found": self.found,
                "timestamp": self.timestamp,
                "frame_number": self.frame_number,
                "recognized_text": self.recognized_text,
                "frame_image": self.frame_image,
                "confidence": self.confidence.to_dict() if self.confidence else None,
                "used_full_search": self.used_full_search,
            },
            "candidates": [c.to_dict() for c in self.candidates],
        }
        if self.error:
            d["error"] = {"message": self.error, "stage": self.error_stage}
        return d
