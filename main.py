"""
Dialogue Locator - CLI (roadmap #8 + #9)

Given a video (URL or local file) and a target line of dialogue, find the
first point in the video where that line is spoken, and report:
timestamp, frame number, recognized text, and a saved frame image.

    python main.py --url "https://ok.ru/video/248244667877" \\
                    --dialogue "My mind rebels at stagnation"

See approach.md for how each stage of this pipeline evolved from the v1
MVP, and README.md for the full flag reference.

Pipeline:
    obtain video (yt-dlp or local path)
        -> extract audio (ffmpeg)
        -> transcribe with word-level timestamps (Whisper; coarse-to-fine
           by default -- see locator/transcribe.py)
        -> fuzzy, sliding-window match against the target dialogue
           (locator/match.py)
        -> rank candidates and score confidence (locator/confidence.py)
        -> convert timestamp -> frame, with a verified seek
           (locator/frames.py)
        -> print + write structured JSON (this file)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from locator import acquire, audio, cache, confidence, frames, match, transcribe
from locator.errors import LocatorError
from locator.schema import Result


def format_hhmmss(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Find the video frame where a target line of dialogue is first spoken.")
    p.add_argument("--source", "--url", dest="source", required=True,
                    help="Video URL (downloaded via yt-dlp) or a local video file path.")
    p.add_argument("--dialogue", required=True, help="Target dialogue to locate.")
    p.add_argument("--model", default="small",
                    help="Whisper model for the fine/full transcription pass (default: small).")
    p.add_argument("--coarse-model", default="tiny",
                    help="Whisper model for the coarse pass in coarse-to-fine mode (default: tiny).")
    p.add_argument("--coarse-to-fine", dest="coarse_to_fine", action="store_true", default=True,
                    help="Locate an approximate window cheaply, then re-transcribe only that "
                         "window at full fidelity (default: on -- see roadmap #7).")
    p.add_argument("--no-coarse-to-fine", dest="coarse_to_fine", action="store_false",
                    help="Transcribe the entire file with --model directly, no coarse pass.")
    p.add_argument("--window-pad", type=float, default=5.0,
                    help="Seconds of padding around the coarse window before the fine pass (default: 5.0).")
    p.add_argument("--floor", type=float, default=match.FLOOR,
                    help=f"Minimum RapidFuzz match score to keep a candidate (default: {match.FLOOR}).")
    p.add_argument("--max-candidates", type=int, default=5,
                    help="Max candidates to report in console/JSON output (default: 5).")
    p.add_argument("--work-dir", type=Path, default=Path("workdir"))
    p.add_argument("--cache-dir", type=Path, default=Path("cache"))
    p.add_argument("--no-cache", dest="use_cache", action="store_false", default=True,
                    help="Disable transcript caching (always re-transcribe).")
    p.add_argument("--out-image", type=Path, default=Path("result_frame.jpg"))
    p.add_argument("--out-json", type=Path, default=Path("result.json"))
    return p.parse_args(argv)


def run(args: argparse.Namespace) -> Result:
    """Runs the full pipeline. Returns a Result either way -- callers check
    `.found`/`.error` rather than relying on exceptions, since a caller
    (e.g. a test) generally wants the structured outcome, not a crash."""
    result = Result(found=False, video_source=args.source, target_dialogue=args.dialogue)

    video_path = acquire.obtain_video(args.source, args.work_dir)
    audio_path = audio.extract_audio(video_path, args.work_dir / "audio.wav")

    if args.coarse_to_fine:
        segments, used_fallback = transcribe.transcribe_coarse_to_fine(
            audio_path, args.dialogue, args.coarse_model, args.model,
            args.cache_dir if args.use_cache else None, args.work_dir,
            use_cache=args.use_cache, pad_seconds=args.window_pad)
    else:
        segments = transcribe.transcribe_full(
            audio_path, args.model, args.cache_dir if args.use_cache else None,
            use_cache=args.use_cache)
        used_fallback = True   # already a full-video search; nothing to escalate to

    candidates = match.find_candidates(segments, args.dialogue, floor=args.floor)

    # The coarse pass's segment-level matching is lenient (see match.COARSE_FLOOR)
    # and can lock onto the wrong ~10s window with a middling score, rather than
    # finding nothing at all. When that happens, the fine pass searches only that
    # (wrong) window and correctly finds nothing there -- but that's not the same
    # as the dialogue being absent from the whole video. Escalate to a full,
    # whole-video search before concluding "not found," same as the escalation
    # transcribe.py already does when the coarse pass finds nothing whatsoever.
    if not candidates and not used_fallback:
        print("Fine pass found nothing in the coarse-guessed window - "
              "escalating to a full fine-grained transcription before giving up.")
        segments = transcribe.transcribe_full(
            audio_path, args.model, args.cache_dir if args.use_cache else None,
            use_cache=args.use_cache)
        result.used_full_search = True
        candidates = match.find_candidates(segments, args.dialogue, floor=args.floor)
    else:
        result.used_full_search = used_fallback

    if not candidates:
        result.error = "Target dialogue was not found in the transcript."
        result.error_stage = "matching"
        return result

    ranked = confidence.rank(candidates)
    conf = confidence.score(ranked)
    top = ranked[0]

    fps = frames.get_fps(video_path)
    requested_frame = frames.timestamp_to_frame(top.start, fps)
    actual_frame = frames.extract_frame(video_path, requested_frame, args.out_image)
    top.frame_number = actual_frame
    for c in ranked[:args.max_candidates]:
        if c.frame_number is None:
            c.frame_number = frames.timestamp_to_frame(c.start, fps)

    result.found = True
    result.timestamp = top.start
    result.frame_number = actual_frame
    result.recognized_text = top.matched_text
    result.frame_image = str(args.out_image)
    result.confidence = conf
    result.candidates = ranked[:args.max_candidates]
    return result


def print_result(result: Result) -> None:
    print()
    print(f"Target dialogue: {result.target_dialogue}")
    if not result.found:
        print("Recognized dialogue: NOT FOUND")
        print(result.error or "The target dialogue was not found in the transcript.")
        return

    print(f"Recognized dialogue: {result.recognized_text}")
    print(f"Timestamp: {result.timestamp:.2f} seconds ({format_hhmmss(result.timestamp)})")
    print(f"Frame number: {result.frame_number}")
    print(f"Frame image: {result.frame_image}")
    print(f"Confidence: {result.confidence.score:.0f}% ({result.confidence.label})")

    if len(result.candidates) > 1:
        print()
        print(f"{len(result.candidates)} candidate(s) considered:")
        for i, c in enumerate(result.candidates, 1):
            marker = " <- selected" if c is result.candidates[0] else ""
            print(f"  {i}. {format_hhmmss(c.start)}  score={c.match_score:.0f}  "
                  f"\"{c.matched_text}\"{marker}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run(args)
    except LocatorError as e:
        result = Result(found=False, video_source=args.source, target_dialogue=args.dialogue,
                         error=str(e), error_stage=e.stage)
        print(f"ERROR [{e.stage}]: {e}")
        _write_json(result, args.out_json)
        return 1
    except Exception as e:  # last-resort guard so a bug still yields structured output
        result = Result(found=False, video_source=args.source, target_dialogue=args.dialogue,
                         error=f"Unexpected error: {e}", error_stage="unexpected")
        print(f"ERROR [unexpected]: {e}")
        _write_json(result, args.out_json)
        return 1

    print_result(result)
    _write_json(result, args.out_json)
    return 0 if result.found else 1


def _write_json(result: Result, out_path: Path) -> None:
    import json
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
