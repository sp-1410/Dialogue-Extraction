# prompts.md

LLM-assisted decisions made during development, in order. Development was
done conversationally with Claude (Claude Code); the prompts below are the
actual messages sent, not reconstructed afterwards.

---

## Prompt 1 - initial MVP + roadmap specification

**Exact prompt** (full text preserved in `quest1_solution_prompt.md` in
this repo): a detailed brief that (a) recorded the manual finding that the
reference video has no on-screen subtitles, so speech-to-text rather than
OCR is the right primary approach; (b) specified the initial MVP pipeline
(yt-dlp -> ffmpeg -> Whisper segment timestamps -> simple text matching ->
`timestamp * fps` -> OpenCV frame extraction -> printed result); (c) laid
out a 9-item improvement roadmap (word-level timestamps, robust matching,
better timestamp->frame conversion, local refinement, multiple candidates,
confidence scoring, efficiency, CLI, structured error handling); and (d)
required an `approach.md` and this `prompts.md` reflecting the real
development history rather than an idealized one.

**Why used**: to fix the scope and sequencing of the whole project before
any code was written, and to pre-commit to documenting the process
honestly as it happened rather than after the fact.

**Result / insight**: this became the project's specification. It also
made explicit that OCR was considered and ruled out for the reference
video specifically, which turned out to matter later (see Prompt 2).

**Decision / effect on implementation**: adopted the exact pipeline and
roadmap ordering from this prompt as the project's build order. `main.py`'s
MVP stage-by-stage structure and its deliberately-simple matching/frame-
conversion logic follow this prompt directly.

---

## Prompt 2 - request for an architecture plan and improvements

**Exact prompt**: *"I want you to help me build this project. Give me a
fully thought out architecture plan of working. If there is any space to
improve in the current implementation do so. Also include what other tech
stack can be used and why they are being used, significance, give reasons
for choices over the other."*

**Why used**: before writing code, to pressure-test the MVP roadmap against
the *official* problem statement PDF (not just the self-written prompt) and
to get alternative-technology trade-offs written down before committing to
a stack.

**Result / insight**: cross-reading the official PDF against the MVP
prompt surfaced a real discrepancy -- the official brief describes the
dialogue as "appearing" on screen, and separately says the evaluator "may
choose a different video" -- while the MVP prompt's own manual inspection
found no on-screen text *for the one example video given*. That combination
means an audio-only design that's correct for the example video could still
fail on an evaluation video with real captions.

**Decision / effect on implementation**: the architecture plan added a
scoped, secondary OCR-corroboration check (a handful of frames near an
ASR-found candidate, not a full-video OCR sweep) so the system degrades
gracefully onto a captioned video without turning OCR back into the primary,
expensive signal the MVP prompt correctly avoided. It also fixed the
concrete tech choices carried into `main.py` and later steps: `yt-dlp` for
acquisition, Whisper for STT (with `faster-whisper`/WhisperX flagged as a
later swap-in, not the MVP choice), RapidFuzz over embeddings for matching
(the actual failure mode is mis-heard words, not paraphrase), and an
explainable, weighted confidence formula rather than an arbitrary score.
This plan was published as a standalone architecture document before any
code was written.

---

## Prompt 3 - authorization to start building

**Exact prompt**: *"I don't have any code as of yet, you can start building
the application from base up with total liberty in quest folder. If you
have any doubts, let me know."*

**Why used**: explicit go-ahead to move from planning to implementation,
with authority to make reasonable calls independently rather than asking
before every step.

**Result / insight**: while validating the very first pipeline stage
(video acquisition against the real `ok.ru` URL), `yt-dlp` and a raw
`curl` both failed identically -- DNS resolved, ping succeeded, but every
HTTPS attempt got its connection reset mid-handshake. That's consistent
with the current network blocking the site (SNI-level), not with a bug in
the extractor or a block from the site itself.

**Decision / effect on implementation**: rather than guess at a workaround
unilaterally, this was surfaced back to the user with the diagnostic
evidence and a set of concrete options. The user chose to supply the
reference video as a local file. Effect on the code: `obtain_video()` in
`main.py` accepts either a URL (downloaded via `yt-dlp`) or a local file
path used as-is, so the rest of the pipeline is identical either way and
the project isn't blocked on network reachability from this particular
machine.

---

---

## Prompt 4 - implement all remaining roadmap improvements

**Exact prompt**: *"Let us go ahead with the next improvements, implement
all(1-6)"*, referring to a 6-item consolidated order proposed the turn
before (word-level timestamps; fuzzy matching; frame refinement;
ranking + confidence; efficiency/caching; CLI + structured output),
covering the original roadmap's items #1-#9.

**Why used**: explicit authorization to implement the full remaining
roadmap in one pass rather than pausing for approval after each item,
having already validated the MVP baseline against the real video.

**Result / insight**: implementing matching's word-level sliding window
(item 2) surfaced a real bug via its own test suite, not by inspection --
`tests/test_match.py::test_two_distinct_occurrences_are_both_reported`
produced 3 candidates instead of the expected 2. Diagnosis: the window
search didn't check whether consecutive words in the flattened word stream
were actually close together in time, so it stitched one trailing word
from an unrelated line to the start of a real occurrence 19 seconds later,
scoring 92% on character similarity alone. This is exactly the kind of
"problem discovered during testing" the brief asks to be documented
honestly rather than glossed over.

**Decision / effect on implementation**: fixed at the source rather than
patched around -- `locator/match.py::_split_into_runs` splits the word
stream into contiguous runs (gap threshold 2.0s) before windowing, so a
candidate can never span a gap no continuous utterance could physically
cross. Separately, the growing number of real, tested concerns (six
roadmap items, each with its own logic and trade-offs) was judged to have
outgrown a single `main.py` file that stays readable top-to-bottom -- the
codebase was split into a `locator/` package (see approach.md section 10's
opening) as a direct, documented consequence of this prompt's scope, not
a change made for its own sake.

---

## Prompt 5 - live bug report from local testing

**Exact prompt**: *"I was running few tests in my system where I was
trying to find the dialouge in the later part of the video, towards the
end and it said it is not able to find, it why could that be"* (with the
two failing console transcripts attached), followed by, after confirming
one line was genuinely present via `--no-coarse-to-fine`: *"with this it
was able to detect it, what should we do to make sure this is the case
always"*.

**Why used**: the user ran the tool independently, on their own machine,
against dialogue the developer (assistant) hadn't specifically tested --
exactly the kind of real usage that surfaces bugs a self-authored test
suite doesn't.

**Result / insight**: both console logs showed the run reaching "Fine
pass: re-transcribing..." rather than the "coarse pass found nothing at
all" fallback message -- meaning the coarse pass had confidently, but
wrongly, picked a window. Asking the user to re-run one line with
`--no-coarse-to-fine` (rather than guessing) confirmed the line was
genuinely in the video and findable at 100% confidence once the search
wasn't restricted to the wrong window.

**Decision / effect on implementation**: extended the existing
coarse-to-fine escalation logic to also trigger when the fine pass finds
nothing in the coarse-guessed window (previously it only triggered when
the coarse pass found nothing whatsoever) -- see approach.md section 12.
Re-verified against the real video for both originally-failing lines,
now correct in ~6 seconds each thanks to the full-transcript cache
already warmed by the user's own diagnostic `--no-coarse-to-fine` run.

---

## Prompt 6 - "I want the code to be able to pull the video.mp4 from a url"

**Exact prompt**: *"Okay for this instance I uploaded the video locally,
but in the working prototype I want the code to be able to pull the
video.mp4 from a url given"*, followed by, after being told the URL path
existed in code but had never actually been exercised end to end (because
`ok.ru` was unreachable during development): *"sure, we can go ahead with
it, I'd also like for you to retry the ok.ru video"*.

**Why used**: the user correctly flagged that "the code has a URL branch"
and "the URL branch actually works" are different claims -- everything
validated so far had gone through the local-file path. This is a direct
request to close that gap with real evidence, not an assumption.

**Result / insight**: retesting surfaced two separate, real findings, not
one. First, `ok.ru` had become reachable again (network conditions
changed since section 7's diagnosis -- confirmed by `curl` returning
HTTP 200 and `yt-dlp` returning full metadata). Second, the actual video
*download* (as opposed to the metadata fetch) failed on a genuine but
different problem: a certificate chain missing its intermediate on the
CDN host. Diagnosed with `openssl s_client` rather than guessed --
traced to a real, legitimate CA (HARICA) whose intermediate the server
simply doesn't send.

**Decision / effect on implementation**: rejected disabling certificate
verification (would also silently accept a genuinely malicious cert) and
rejected `yt-dlp`'s `prefer_system_certs` escape hatch (introduced a
different, network-level failure when tested, not a fix). Implemented
`locator/certs.py`, which supplies the specific missing intermediate
certificate and monkeypatches `certifi.where()` -- required because
`yt-dlp` calls that function directly rather than honoring the
`SSL_CERT_FILE` environment variable, confirmed by reading yt-dlp's own
source rather than assumed. Verified against the real download: the
actual reference video, pulled live from its real `ok.ru` URL, is
byte-identical (1,000,228,569 bytes) to the local copy used for every
prior validation run, and produces the identical result through the full
CLI. Also re-validated the general (non-`ok.ru`) URL-download path the
same way, against a small independently-reachable YouTube video, since
that path had the same "written but never exercised" gap.

*(Appended after each further roadmap step, in the same format: exact
prompt, why it was used, what it produced, and what changed in the code as
a result.)*
