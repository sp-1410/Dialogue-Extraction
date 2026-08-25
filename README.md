# Dialogue Locator

Given a video and a target line of dialogue, find the exact frame where
that line is first spoken: timestamp, frame number, recognized text, and
the frame itself as an image.

See [`approach.md`](approach.md) for how this solution evolved -- MVP
through every roadmap improvement, including problems found during
testing and why each design choice was made -- and
[`prompts.md`](prompts.md) for the LLM-assisted decisions made along the
way. The original brief and improvement roadmap this project follows are
in [`quest1_solution_prompt.md`](quest1_solution_prompt.md).

## Setup

```bash
python -m venv .venv
.venv/Scripts/activate        # Windows
pip install -r requirements.txt
```

`ffmpeg` must also be installed and on `PATH` (not a Python package):

```bash
winget install --id Gyan.FFmpeg -e
```

## Run

```bash
python main.py --source "https://ok.ru/video/248244667877" \
                --dialogue "My mind rebels at stagnation"
```

`--source` (alias `--url`) accepts either a URL, downloaded via `yt-dlp`,
or a local video file path. Prints the human-readable result and always
writes a structured `result.json` alongside it (see `locator/schema.py`
for the shape).

By default, the search is **coarse-to-fine** (roadmap #7): a cheap `tiny`
pass locates an approximate window, then only that window is re-transcribed
at full fidelity with the `small` model -- falling back to a full
fine-grained pass automatically if the coarse pass finds nothing close to
the target. Transcripts are cached under `cache/`, so a repeat run against
the same video is seconds, not minutes (see `approach.md` section 11 for
measured numbers).

<details>
<summary>All flags</summary>

| Flag | Default | Meaning |
|---|---|---|
| `--source` / `--url` | *(required)* | Video URL or local file path |
| `--dialogue` | *(required)* | Target line to locate |
| `--model` | `small` | Whisper model for the fine/full pass |
| `--coarse-model` | `tiny` | Whisper model for the coarse pass |
| `--coarse-to-fine` / `--no-coarse-to-fine` | on | Two-pass vs. full-file transcription |
| `--window-pad` | `5.0` | Seconds padded around the coarse window |
| `--floor` | `70.0` | Minimum RapidFuzz score to keep a candidate |
| `--max-candidates` | `5` | Candidates shown in console/JSON output |
| `--work-dir` | `workdir` | Downloaded video / extracted audio |
| `--cache-dir` | `cache` | Transcript cache location |
| `--no-cache` | off | Disable transcript caching |
| `--out-image` | `result_frame.jpg` | Extracted frame output path |
| `--out-json` | `result.json` | Structured result output path |

</details>

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

25 tests: fast unit tests for matching/ranking/frame-conversion logic
(`test_match.py`, `test_confidence.py`, `test_frames.py`, no network or
Whisper-model-size dependency) plus end-to-end smoke tests against a local
synthetic fixture (`test_pipeline.py`). If `tests/fixtures/sample.mp4` is
missing, regenerate it with (Windows, needs ffmpeg on `PATH`):

```bash
powershell -File tests/make_test_clip.ps1
```

## Status

Roadmap items #1-#9 implemented and validated -- see `approach.md`
section 10 for how each was built and tested, section 11 for the
real-video validation run, section 12 for a real coarse-to-fine bug found
during local testing (and fixed), and section 13 for validating the
`--source <URL>` path for real against both the actual reference video
and a generic `yt-dlp`-supported URL:

- **Real reference video, via URL** (`--source "https://ok.ru/video/248244667877"`):
  downloads the actual reference video live (1,000,228,569 bytes,
  confirmed byte-identical to the local copy), finds *"My mind rebels at
  stagnation"* at **324.88s / frame 7789**, 100% confidence, single
  unique candidate -- confirmed to be the genuine line from *The Sign of
  Four*. First cold-cache run: **4m10s**, down from v1's ~18 minutes.
  Repeat run (warm cache): **6.1s**.
- **Real reference video, via local file** (`--source video.mp4`): same
  result, same numbers -- useful as a network-independent fallback (see
  `approach.md` section 7 for why that mattered during development).
- **Generic URL path**, independently re-validated against a small
  YouTube video end to end (download, transcribe, match, extract).
- **Real bug found via local testing, now fixed**: dialogue later in the
  video (*"Madam I think I can smell fire"*, *"I can't breathe"*) was
  initially misreported as not found -- the coarse-to-fine search locked
  onto the wrong window rather than finding nothing. Now escalates to a
  full search automatically; both lines resolve correctly (`approach.md`
  section 12).
- **Synthetic fixture + unit tests**: 25/25 passing.

See `approach.md` section 14 for improvements that were considered and
deliberately not implemented, with the reasoning for each.
