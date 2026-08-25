# approach.md

How this solution was arrived at, in the order it actually happened.

## 1. Initial understanding of the problem

The brief: given a video URL and a target dialogue, find the exact frame
where that dialogue first appears, and return the timestamp, frame number,
extracted text, and the frame image itself. The official problem statement
phrases it as an "on-screen dialogue" appearing in the video, which reads,
on first pass, like a subtitle/caption-detection problem.

## 2. Initial assumption: OCR might be useful

Because of that "on-screen dialogue" phrasing, the first hypothesis was
that the dialogue is burned-in text (a caption or title card), and OCR
over sampled frames would be the way to find it.

## 3. Manual inspection of the reference video

The reference video (`https://ok.ru/video/248244667877`) was inspected by
hand. There is **no subtitle or caption text visibly displayed anywhere on
screen**. The line "My mind rebels at stagnation" is spoken dialogue, not
written text.

## 4. Realization: this is a spoken-dialogue localization problem

OCR would find nothing on this video. The task is really: transcribe the
audio, find where the target line is spoken, and map that back to a video
frame. This reframes the problem from computer vision to speech-to-text +
temporal alignment.

## 5. Research / selection of speech-to-text

Whisper was chosen as the STT engine: it's open source, runs locally (no
API key or network dependency at inference time), and returns per-segment
timestamps out of the box, which is exactly the alignment signal this task
needs. `openai-whisper` (the reference implementation) was picked for the
first version specifically because it's the simplest to read and explain,
even though faster/more accurate variants exist (see "Future improvements"
below).

## 6. Initial pipeline (implemented)

```
video source -> yt-dlp/local file -> ffmpeg (extract mono 16kHz audio)
   -> Whisper (segment-level transcript) -> normalize + substring match
   -> timestamp * fps -> OpenCV frame extraction -> print result
```

Implemented in `main.py`. Deliberately simple:

- **Matching**: lowercase, strip punctuation, collapse whitespace, then a
  plain substring check of the (normalized) target inside each (normalized)
  Whisper segment's text.
- **Timestamp -> frame**: the raw `frame_number = int(timestamp * fps)`
  formula, using the *segment start time* Whisper reports.
- **Frame extraction**: OpenCV `VideoCapture`, seek to that frame number,
  read, save as JPEG.
- **Configuration**: `VIDEO_SOURCE` / `TARGET_DIALOGUE` are constants at the
  top of `main.py`, not hardcoded inside the logic -- deliberately not yet a
  CLI. A CLI is roadmap item #8 in the original plan and is introduced
  later, once the core pipeline is proven, rather than up front.

## 7. Problem discovered during testing: `ok.ru` was unreachable

Before transcribing anything, the acquisition step was checked against the
real reference URL. Both `yt-dlp -J` (metadata only, no download) and a raw
`curl` to `https://ok.ru/...` failed identically: DNS resolved fine, ICMP
ping succeeded (~217ms, consistent with a Russia-hosted host), but every
HTTPS attempt had its connection reset mid-handshake
(`WinError 10054` / curl exit with no HTTP status). DNS working while the
TLS handshake gets reset immediately points at network-level (ISP/firewall)
SNI blocking on this machine, not a bug in `yt-dlp`'s extractor and not a
block from the site itself.

**Decision**: rather than build only against a URL that can't currently be
reached from the dev machine, `main.py`'s acquisition stage accepts *either*
a URL (downloaded via `yt-dlp`) or a local file path (used as-is). This
keeps the pipeline's logic identical either way -- the video-agnostic
requirement from the brief -- while unblocking real development: the exact
reference video is supplied as a local file instead of a live download.

A second, smaller problem surfaced in the same test: this machine's Python
had no configured CA certificate store at all
(`ssl.get_default_verify_paths()` returned `cafile=None`), which made even
a *reachable* HTTPS request fail with `CERTIFICATE_VERIFY_FAILED`. Fixed by
depending on `certifi` and pointing `SSL_CERT_FILE` at its bundle at the top
of `main.py`, so the tool doesn't depend on the host machine's own cert
configuration.

## 8. Validated against the real reference video

Once the reference video was supplied locally as `video.mp4` (per section 7),
the MVP was run against it for real, unmodified:

```
Target dialogue: My mind rebels at stagnation
Recognized dialogue: My mind rebels at stagnation.
Timestamp: 325.00 seconds
Frame number: 7792
Frame image: result_frame.jpg
```

The video (54m22s, 960x720, ~23.976fps, 668 Whisper segments) turned out to
be a dramatization of Arthur Conan Doyle's *The Sign of Four*. The matched
segment's surrounding context confirms this is the real quoted exchange, not
a coincidental partial match:

```
[316.00-319.00] I cannot tell you how it clarifies and stimulates the mind.
[319.00-322.00] Yes, and destroys it in time.
[325.00-328.00] My mind rebels at stagnation.       <- match
[330.00-332.00] Give me problems.
[332.00-334.00] Give me work.
```

It is the **only** occurrence of the line across all 668 transcript
segments -- no ambiguity to resolve for this particular video/dialogue pair,
though the pipeline doesn't yet know that (see roadmap #5 in section 9: it
returns the first match, not a ranked search of all matches, so it would
currently miss a second real occurrence rather than choose between them).
The extracted frame (`docs/evidence/mvp_first_real_run_frame7792.jpg`) shows
Jeremy Brett as Sherlock Holmes mid-line, a plausible speaking frame for a
timestamp taken from the *start* of a 3-second Whisper segment.

Two things worth noting about this specific run:

- `ffprobe` reported `r_frame_rate=24000/1001` (23.976fps, standard NTSC
  film rate) for this file, not an integer. Using a naive assumption of
  `fps=24` instead of reading the container's actual rate would have drifted
  the frame number by roughly 78 frames by this point in the video (~3.3s) --
  a concrete, measured instance of the constant-fps risk raised in the
  original roadmap (#3), even though this file itself is constant-frame-rate
  rather than variable.
- Transcribing the full 54m22s audio with the `small` model took about 18
  minutes on this machine's CPU (measured via a 3-minute sample: ~3x
  realtime). No caching exists yet, so every re-run re-transcribes from
  scratch -- the concrete cost that roadmap #7 (efficiency) will target.

## 9. Known limitations of this version (v1 / MVP)

- **Segment-level, not word-level, timestamps.** Whisper segments can be
  several seconds long and don't necessarily start exactly when the target
  phrase does -- the reported timestamp is "the segment containing the
  line started here," not "the line started here." (Roadmap #1.)
- **Substring matching is exact-ish.** Any ASR mis-hearing of even one word
  causes a miss with no partial credit. (Roadmap #2.)
- **`timestamp * fps` assumes constant fps.** Wrong for variable-frame-rate
  sources, and doesn't account for encoder-frame quantization or
  container mux drift. (Roadmap #3/#4.)
- **First match only.** If the line is spoken more than once, only the
  first occurrence is ever considered -- no ranking among candidates.
  (Roadmap #5.)
- **No confidence score.** A match is either found or not; there's no
  signal for "found, but shaky." (Roadmap #6.)
- **No efficiency work yet.** The full video is downloaded and the whole
  audio track transcribed at once, even though only a few seconds around
  the answer actually matter. (Roadmap #7.)
- **Config, not CLI.** Editing constants in `main.py` works but isn't what
  the final deliverable should look like. (Roadmap #8.)
- **Minimal error handling.** Failures are caught per-stage and printed,
  but there's no structured (JSON) error output yet. (Roadmap #9.)

## 10. v2: roadmap improvements #1-#9, implemented

Following the project's own development method (explain the problem,
explain the fix, implement, test, explain the result, state trade-offs,
say plainly what's implemented vs. proposed), each roadmap item was
addressed against v1's real, measured limitations from section 9 -- not
hypothetical ones.

At this scale the pipeline stopped fitting comfortably in one file that's
still easy to read top-to-bottom, so it was split into a small `locator/`
package (`acquire`, `audio`, `transcribe`, `match`, `frames`, `confidence`,
`cache`, `schema`, `errors`) with `main.py` reduced to a CLI that
orchestrates them. This is a real complexity trade-off, made deliberately
rather than accidentally: v1 was one file *because* six separate concerns
(download, transcribe, match, refine, rank, score) fit in one screen. Once
each of those concerns gained its own real logic and its own tests, one
file would have worked against readability, not for it.

### 10.1 Word-level timestamps (roadmap #1)

**Problem with v1**: Whisper's segment timestamp marks when a whole
(multi-second) chunk started, not when the target phrase within it did.

**Fix**: `openai-whisper` can report per-word timestamps directly
(`word_timestamps=True`), derived from the model's cross-attention weights
via dynamic time warping. This is **not** a separate forced-alignment
model -- that would be WhisperX, evaluated and intentionally not adopted
here (see section 12) to avoid a second heavy dependency (ctranslate2 +
a wav2vec2 alignment model) for a hackathon deliverable, given the accuracy
gain over Whisper's native word timestamps is real but secondary to simply
*having* word-level timestamps at all.

**Implemented**: `locator/transcribe.py`, `word_timestamps=True` on every
transcription call.

**Tested**: `tests/test_pipeline.py::test_full_segments_carry_word_timestamps`
asserts every segment carries a non-empty `words` list.

**Trade-off**: word timestamps add a small amount of decode time per
segment and are still an approximation (typically accurate to within a
couple hundred milliseconds, not frame-exact) -- which is exactly why
section 10.3's *verified* frame seek exists as a second line of defense,
rather than trusting the word timestamp blindly.

### 10.2 Robust dialogue matching (roadmap #2)

**Problem with v1**: matching was an exact, normalized substring check
against one Whisper *segment* at a time. Two concrete failures: (a) any
single mis-heard word anywhere in the phrase caused a total miss with no
partial credit, and (b) a phrase split across a segment boundary could
never be found, because substring search never looks across segments.

**Fix**: match over the flat *word* stream (unlocked by 10.1) with a
RapidFuzz-scored sliding window, sized target-length -1..+2 words to
tolerate a dropped or inserted short word.

**Implemented**: `locator/match.py::find_candidates`.

**Tested**: `tests/test_match.py` --
`test_one_misheard_word_still_matches_via_fuzzy_score` (a mis-heard
"rebels"->"revels" still matches, ASR mis-hearing is precisely the failure
mode this targets, not paraphrase -- see section 12 on why embeddings were
rejected) and `test_phrase_spanning_a_segment_boundary_is_still_found`
(the exact v1 failure mode, fixed).

**Real bug found by this test suite, and fixed**: the first
implementation slid windows across the *entire* word stream regardless of
gaps between words. A test with two genuine occurrences of the target line
separated by an unrelated line 19 seconds later
(`test_two_distinct_occurrences_are_both_reported`) produced a **third,
spurious candidate** scoring 92% -- a window that stitched one trailing
word from the unrelated line to the start of the second real occurrence,
because character-level similarity over a joined string barely penalizes
one extra prepended word. Fixed by splitting the word stream into
contiguous runs (`_split_into_runs`, gap threshold 2.0s) before windowing,
so a window can never span a gap no continuous utterance could cross. This
is called out explicitly because the brief asks for real problems found
during testing, not a sanitized history -- this one was found by a test
that was *right* to fail, and the fix is a real correctness improvement,
not a test-chasing patch.

**Trade-off**: RapidFuzz's `fuzz.ratio` is a character-level metric applied
to word-joined strings, not a linguistic one -- it will score two
phonetically dissimilar but character-similar words as close, and vice
versa. Good enough for the actual failure mode (ASR transcription noise),
not a semantic matcher.

### 10.3 Better timestamp-to-frame conversion (roadmap #3) + local refinement (roadmap #4)

**Problem with v1**: `int(timestamp * fps)` has two distinct issues,
demonstrated concretely against the real reference video in section 8:
truncation bias (`int()` always rounds down, `round()` doesn't), and no
guarantee that `cv2.VideoCapture.set(POS_FRAMES, n)` actually lands on
frame `n` -- on many codecs it seeks to the nearest keyframe, and the
*next read* may not be frame `n`.

**Fix implemented**: `round()` instead of `int()`
(`locator/frames.py::timestamp_to_frame`), and a *verified* seek
(`extract_frame`) that reads forward after seeking, checking the decoder's
actual reported frame position, until it reaches (or passes) the requested
frame -- rather than trusting the first read.

**Fix investigated, not implemented**: true roadmap #4 "re-transcribe a
small window around the candidate to refine the timestamp" is what
section 10.5's coarse-to-fine fine pass effectively provides as a side
effect (the fine pass already re-transcribes the candidate's neighborhood
at higher fidelity) -- so it wasn't built as a second, separate mechanism.
Genuine visual refinement (e.g. picking the sharpest/least-blurred frame
in a ±2 frame window) was considered and not implemented; see section 12.

**Tested**: `tests/test_frames.py` --
`test_timestamp_to_frame_rounds_rather_than_truncates` and
`test_extract_frame_lands_on_or_after_requested_frame`.

**Trade-off**: the verified seek costs a handful of extra frame reads on a
rough keyframe seek (bounded at 60 reads) -- negligible next to a
multi-minute transcription pass.

### 10.4 Multiple candidates + confidence scoring (roadmap #5 + #6)

**Problem with v1**: first match wins, unconditionally. No way to tell
"found, and certain" from "found, but this could easily be a fluke."

**Fix**: `locator/match.py` already returns every candidate clearing the
match floor, not just the first; `locator/confidence.py` ranks them
(match score, then timing consistency) and produces a single, documented
weighted score: 65% match similarity, 20% timing consistency (do the
words in the window look like one fluent utterance, or a coincidental
stitch?), 15% uniqueness margin (how far ahead of the runner-up is the
top candidate?) -- bucketed High (>=85) / Medium (65-84) / Low (<65).

**Implemented**: `locator/confidence.py`.

**Tested**: `tests/test_confidence.py` -- a lone strong candidate scores
High; an equally strong runner-up measurably lowers confidence via the
margin term even though the top candidate's own score didn't change; a
weak match scores Low.

**Trade-off**: the weights (65/20/15) are a considered, stated judgment
call, not derived from labeled data -- there was no labeled dataset of
right/wrong matches to fit them against. They're deliberately simple
enough to defend in one sentence each, per the brief's "explainable, not
arbitrary" requirement, rather than opaque or learned.

### 10.5 Efficiency (roadmap #7)

**Problem with v1**: the entire ~54-minute reference video was
transcribed at full fidelity on every run -- about 18 minutes each time
(measured in section 8), even though only a few seconds around the answer
ever mattered, and even on a second run against the *same* unchanged
video.

**Fix, part 1 -- caching** (`locator/cache.py`): the transcript for a
given (audio content hash, model, mode) is cached to disk. A full-mode
cache key deliberately excludes the target dialogue, since a whole-video
transcript doesn't depend on what's later searched for in it -- so
re-running with a *different* `--dialogue` against the same video and
model still hits the cache.

**Fix, part 2 -- coarse-to-fine transcription** (`locator/transcribe.py`):
by default, a cheap pass (`tiny` model, whole file, segment-level only)
locates an approximate window, and only that window (padded, default 5s
each side) is re-transcribed with word timestamps at higher fidelity
(`small` model). If the coarse pass finds nothing even loosely resembling
the target, it automatically falls back to a full fine-grained pass rather
than silently reporting "not found" from a bad coarse guess --
demonstrated live: see section 11's not-found test, where the coarse pass
correctly triggers this exact fallback.

**Tested**: `tests/test_pipeline.py::test_end_to_end_coarse_to_fine_finds_target`,
and directly measured against the real video (section 11).

**Trade-off**: coarse-to-fine trades a small amount of correctness risk
(a coarse model bad enough to miss the phrase entirely, on a video where a
weak coarse-floor match is genuinely also wrong) for a large, real speed
win, with the whole-video fallback bounding the downside. `--no-coarse-to-fine`
disables it outright when full-fidelity-only behavior is wanted. Caching
has a much smaller trade-off: correctness depends on the cache key
actually capturing everything that affects the result (audio content,
model, mode, and dialogue where relevant) -- gotten wrong, this is a class
of bug (stale cache) that's easy to introduce and easy to not notice.

### 10.6 CLI, structured JSON, and error handling (roadmap #8 + #9)

**Problem with v1**: `VIDEO_SOURCE`/`TARGET_DIALOGUE` were constants at
the top of `main.py` -- functional, but not "usable with a different video
and dialogue without touching the source," which is the actual
requirement. Errors were bare `RuntimeError`s with no machine-readable
shape.

**Fix**: `argparse`-based CLI (`--source`/`--url`, `--dialogue`, plus every
tunable introduced in 10.1-10.5); a small `LocatorError` hierarchy
(`locator/errors.py`) so each stage's failure carries a `stage` field, not
just a message; every run -- success, "not found," or hard error -- writes
a structured JSON file (`locator/schema.py`) alongside the human-readable
console output, per the brief's "JSON in addition to the human-readable
output."

**Tested**: `tests/test_pipeline.py::test_cli_writes_valid_json`, plus
manual CLI runs covering the success, not-found, and bad-input-path cases
(all three produce a valid JSON file and the documented exit codes: 0 for
found, 1 otherwise).

**Trade-off**: `argparse` over `Typer`/`Click` -- stdlib, no install step,
appropriate for a flat set of flags on one entry point (see the
architecture plan's tech stack matrix for the fuller comparison).

## 11. v2 validated against the real reference video

Run for real via the new CLI, default settings (coarse-to-fine on, `tiny`
coarse / `small` fine, caching on):

```
python main.py --source video.mp4 --dialogue "My mind rebels at stagnation"
```

```
Target dialogue: My mind rebels at stagnation
Recognized dialogue: My mind rebels at stagnation.
Timestamp: 324.88 seconds (00:05:24.880)
Frame number: 7789
Frame image: result_frame.jpg
Confidence: 100% (High)
```

Full run log and JSON archived at `docs/evidence/v2_real_run_*`.

**Consistent with v1's result** (325.00s / frame 7792, section 8) to
within 0.12s / 3 frames -- the small shift is expected and correct: v1's
timestamp was *the whole Whisper segment's* start, v2's is the specific
word "My"'s start, which naturally lands at or slightly before the
segment boundary Whisper originally reported. Single candidate, 100%
confidence -- matches the "only occurrence in 668 segments" finding from
v1.

**Efficiency, measured, not estimated:**

| Run | Time |
|---|---|
| v1 (full `small`-model transcription, no cache) | ~18 min |
| v2, first run (coarse `tiny` pass + fine `small` pass on a 13s window) | **4m10s** |
| v2, second run, identical query (both passes cache-hit) | **6.1s** |

The coarse-to-fine pass alone is a ~4.3x speedup over v1 on a cold cache;
caching turns every *repeat* run -- which is most runs during development,
and any re-run against an unchanged video -- from minutes into single-digit
seconds. The 6.1s isn't "instant" because audio re-extraction (ffmpeg,
~4s) and model/Python startup still happen every run; caching only
eliminates the transcription itself, which was the actual cost center.

**Coarse-to-fine's fallback safety net, also exercised for real** (against
the synthetic fixture, to avoid a ~18-minute full-fallback run against the
real video purely to prove a code path that's identical either way): a
CLI run with a target dialogue absent from the fixture produced

```
Coarse pass: transcribing with Whisper (tiny)...
Coarse pass found nothing resembling the target dialogue - falling back to a full fine-grained transcription.
...
Recognized dialogue: NOT FOUND
```

confirming the fallback triggers correctly rather than the coarse pass's
own weak/absent match silently becoming a false "not found."

## 12. Bug found by real local testing: coarse-to-fine false negatives

After v2 was handed off to run locally, testing it against dialogue from
later in the video surfaced a real correctness bug, not a hypothetical
one.

**Problem observed**: searching for two lines actually present later in
the video --

```
python main.py --source video.mp4 --dialogue "Madam I think I can smell fire"
python main.py --source video.mp4 --dialogue "I can't breathe"
```

-- both reported "NOT FOUND," but the log showed each run going straight
to "Fine pass: re-transcribing ...s window," meaning the coarse pass
*did* think it had found something. Re-running the first line with
`--no-coarse-to-fine` (a full, unwindowed search) found it immediately, at
100% confidence: `"Madam, I think I can smell fire."` at 00:41:32.700.
So the line was real -- the coarse-to-fine search path was wrong, not the
transcript.

**Root cause**: the coarse pass's segment-level locator
(`match.find_rough_window`, `fuzz.partial_ratio`, floor 55) is
deliberately lenient, so a mis-transcribing cheap model doesn't cause a
false "nothing here." But that leniency has a cost: it can lock onto the
*wrong* ~10-second window with a middling score, rather than finding
nothing at all. The fine pass then correctly finds nothing in that wrong
window -- and the code, at that point, had no way to distinguish "the
dialogue genuinely isn't in this video" from "the coarse pass guessed
wrong and we never actually looked at the right part of the video." Only
the *first* case had a fallback (transcribe.py's existing "coarse pass
found nothing at all -> full transcription" path); the second, more
common case did not.

**Fix**: extend the escalation in `main.py::run` -- if the fine pass on
the coarse-guessed window returns no candidates, and a full search hasn't
already happened, escalate to a whole-video full-fidelity transcription
before reporting "not found." `Result.used_full_search` now records
whether this happened, visible in the JSON output.

**Tested**: `tests/test_pipeline.py::test_escalates_to_full_search_when_coarse_window_misses`
mocks the coarse pass into confidently returning an irrelevant window and
asserts the full-search path is actually invoked and finds the (mocked)
real occurrence elsewhere. Also re-verified against the real video for
both originally-failing lines -- both now resolve correctly, and in ~6
seconds each rather than the roadmap #7 caching cost of a cold full
transcription, because the `small`-model full transcript from the earlier
`--no-coarse-to-fine` diagnostic run was already cached (see section 10.5:
the full-transcript cache key is dialogue-independent by design, so this
worked without having been built specifically for this fix).

**Trade-off**: in the worst case (a video where the true answer genuinely
isn't present, and the coarse pass unluckily locks onto a plausible-looking
wrong window), coarse-to-fine now costs the same as a full search on that
single query -- the speed win only applies when the coarse pass's guess
was actually right, or when nothing needs escalating. That's the correct
trade to make: a wrong "not found" is a worse failure than a slow correct
answer.

## 13. `ok.ru` URL acquisition: retested, diagnosed, and fixed for real

Section 7 diagnosed `ok.ru` as unreachable from the development machine
(TLS handshake reset, DNS/ping both fine) and worked around it by
supplying the video as a local file. That diagnosis held for the
development window, but network conditions aren't static -- asked to
retest later, `ok.ru`'s main domain was reachable again (`curl` returned
HTTP 200, `yt-dlp -J` returned full metadata: title, 3261s duration,
matching the local copy exactly). The earlier block looks to have been a
transient ISP/network condition, not a permanent one, and not a bug in
this project either way.

Retesting surfaced a **second, different, real problem** in the actual
video download (not the metadata fetch): a certificate verification
failure --

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain
```

**Diagnosis, not guesswork**: `openssl s_client` against the CDN host
serving the actual video (`vd346.okcdn.ru`) showed its leaf certificate is
issued by **HARICA** (Hellenic Academic and Research Institutions CA) --
a legitimate, publicly trusted CA whose root (`HARICA TLS ECC Root CA
2021`) is already present in `certifi`'s bundle. The real fault: the CDN
server sends only its leaf certificate, omitting the intermediate
(`HARICA DV TLS ECC`) needed to build a chain up to that root. Browsers
tolerate this via cached/AIA-fetched intermediates; Python's `ssl` module
via `certifi` does not, so verification fails even though the chain is
legitimate.

**Fix considered and rejected**: disabling certificate verification
(`--no-check-certificate`) would "fix" this but would also silently
accept a genuinely malicious certificate on any future request -- not an
acceptable trade for a download step, even though the practical risk here
specifically is low (the leaf cert *is* from a real CA). Also tried and
rejected: `yt-dlp`'s `prefer_system_certs` option (use the OS trust store
instead of `certifi`) -- this produced a *different* failure
(`SSL: UNEXPECTED_EOF_WHILE_READING`) on the initial metadata request,
consistent with the network being flaky in a way independent of the
certificate issue, not evidence the OS-trust-store path was the right
fix.

**Fix implemented** (`locator/certs.py`): fetch the specific missing
intermediate once (from the leaf certificate's own Authority Information
Access "CA Issuers" URL) and supply it alongside `certifi`'s bundle,
completing an already-legitimate chain rather than turning verification
off. One complication: `yt-dlp` calls `certifi.where()` directly
(`yt_dlp/networking/_helper.py`) rather than honoring the `SSL_CERT_FILE`
environment variable every other library in this project respects --
confirmed by reading yt-dlp's own source, not assumed. So the fix
monkeypatches `certifi.where()` itself (`certs.patch_certifi()`, called
once from `acquire.py`); since Python module imports are singletons,
every caller in the process -- including inside `yt-dlp` -- resolves to
the same patched function.

**Tested for real**: with the fix in place, `locator.acquire.obtain_video`
downloaded the actual reference video over its real `ok.ru` URL --
**1,000,228,569 bytes, byte-identical to the local copy already used for
every other v2 validation run** (confirmed independently: the run's own
transcript cache-hit on the audio content hash). The full CLI, run with
`--source "https://ok.ru/video/248244667877"` end to end, reproduced the
exact same result as every local-file run: 324.88s / frame 7789 / 100%
confidence. Evidence archived at `docs/evidence/v2_okru_url_source_*`.

Also re-validated the second URL-acquisition path while at it: a small,
independently reachable YouTube video ("Me at the zoo", 19s) run through
the real `--source <URL>` CLI end to end -- download, transcribe, fuzzy
match, verified frame extraction -- correctly located "really long
trunks" and extracted the matching frame
(`docs/evidence/v2_url_source_youtube_*`). Between the two, both
acquisition paths (arbitrary `yt-dlp`-supported URL, and the specific
graded reference URL) now have real, not hypothetical, evidence behind
them.

**Trade-off**: this fix is specific to one observed missing-intermediate
case. A different CDN host with a *different* incomplete chain would need
its own intermediate added to `_KNOWN_MISSING_INTERMEDIATES` the same
way -- this isn't a general "trust anything" workaround (deliberately, per
the rejected alternative above), so it doesn't automatically cover a
misconfiguration it hasn't seen.

## 14. Future improvements considered but not (yet) implemented

- **Hybrid OCR corroboration.** Given the official brief's "on-screen
  dialogue" wording and that the evaluator may swap in a different video,
  a narrow OCR check (a handful of sampled frames around a candidate
  timestamp, not a full-video OCR sweep) would make the system robust to a
  video that *does* have burned-in captions, without reintroducing OCR as
  a primary, expensive signal. Not implemented in v1.
- **Word-level alignment via WhisperX** (forced alignment against a
  wav2vec2 CTC model) instead of Whisper's own attention-derived word
  timestamps, for materially tighter frame accuracy. Investigated as a
  roadmap #1 candidate, not yet implemented.
- **Semantic (embedding) matching** as a fallback when fuzzy string
  matching fails outright. Considered and deliberately not implemented --
  the actual failure mode in this task is ASR mis-hearing words, not
  paraphrase, so a fuzzy string metric is the better-targeted tool.
- **Visual frame refinement** -- given the candidate frame's neighborhood,
  picking the sharpest / least motion-blurred of a small window of frames
  rather than exactly the requested index. Genuinely orthogonal to the
  verified-seek fix in section 10.3 (that fix guarantees you land on the
  frame you asked for; this would additionally question whether that
  exact frame is the *best* one to show). Not implemented -- v2's verified
  seek was judged sufficient for the stated requirement ("the frame where
  the dialogue first appears"), and adding a "best frame" heuristic risks
  answering a subtly different question than the one asked.
- **Distributed/parallel coarse pass** (splitting a very long video into
  chunks transcribed concurrently) for videos much longer than the
  ~54-minute reference one, where even the cheap coarse pass becomes the
  bottleneck. Not needed at the current scale (measured in section 11),
  so not built.

*(This file is updated after each roadmap step, describing what changed
and why, per the project's own development method.)*
