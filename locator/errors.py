"""
Structured error hierarchy (roadmap #9).

The MVP caught failures with bare `RuntimeError`/`FileNotFoundError` and
printed a message. That's fine for a human watching the console, but it
gives a caller (or the JSON output) no reliable way to tell *which* stage
failed without string-matching the message. Each pipeline stage now raises
a specific `LocatorError` subclass, which the CLI catches once at the top
level and turns into both a human message and a structured `stage` field
in the JSON error output.
"""


class LocatorError(Exception):
    """Base class for all expected, handleable pipeline failures."""
    stage = "unknown"


class AcquisitionError(LocatorError):
    stage = "acquisition"


class AudioExtractionError(LocatorError):
    stage = "audio_extraction"


class TranscriptionError(LocatorError):
    stage = "transcription"


class FrameExtractionError(LocatorError):
    stage = "frame_extraction"


class DialogueNotFoundError(LocatorError):
    """Raised when no candidate clears the matching floor at all.

    Deliberately distinct from "found, but low confidence" -- that case is
    not an error, it's a low-confidence *result* (see schema.Result).
    """
    stage = "matching"
