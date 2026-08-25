"""
Timestamp -> frame conversion and extraction (roadmap #3 + #4).

Two concrete, measured problems with the MVP's raw
`frame_number = int(timestamp * fps)`, both documented with real numbers
from the reference video in approach.md section 8:

1. `int()` truncates rather than rounds, so it's systematically biased
   about half a frame early on average. `round()` isn't -- a small, free,
   explainable fix.
2. `cv2.VideoCapture.set(CAP_PROP_POS_FRAMES, n)` is not guaranteed to land
   exactly on frame `n` -- on many codecs it seeks to the nearest preceding
   keyframe, then the *next read* may or may not be frame `n` depending on
   the decoder. Silently trusting the seek can extract the wrong frame with
   no indication anything was off.

The fix here is a *verified* seek: after seeking, read forward (normally
zero extra reads; a handful on a rough seek) until the reported frame
position actually reaches the target, rather than trusting the first read.
This is the "local refinement" from roadmap #4, scoped to what's provably
useful here -- it doesn't require re-transcribing anything, just confirms
the frame OpenCV hands back is the one that was actually asked for.
"""

from __future__ import annotations

from pathlib import Path

import cv2

from .errors import FrameExtractionError

MAX_SEEK_CORRECTION_READS = 60   # generous headroom for a rough keyframe seek


def get_fps(video_path: Path) -> float:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FrameExtractionError(f"OpenCV could not open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    if not fps or fps <= 0:
        raise FrameExtractionError(f"OpenCV reported an invalid fps ({fps}) for {video_path}")
    return fps


def timestamp_to_frame(timestamp: float, fps: float) -> int:
    return round(timestamp * fps)


def extract_frame(video_path: Path, frame_number: int, output_path: Path) -> int:
    """Seek to `frame_number`, verify the landing, save it as a JPEG.
    Returns the actual frame index the saved image came from (==
    frame_number on a clean seek; may differ by a frame or two on a rough
    one -- that's exactly the case this function exists to catch)."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise FrameExtractionError(f"OpenCV could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target = max(0, min(frame_number, max(0, total_frames - 1)))

    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    frame = None
    actual = -1
    for _ in range(MAX_SEEK_CORRECTION_READS):
        ok, frame = cap.read()
        if not ok:
            break
        actual = int(round(cap.get(cv2.CAP_PROP_POS_FRAMES))) - 1
        if actual >= target:
            break
    cap.release()

    if frame is None:
        raise FrameExtractionError(f"Could not read frame {target} from {video_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), frame)
    return actual
