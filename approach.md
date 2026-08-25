# Dialogue Timeline -- Approach

## 1. Initial Understanding

The task is to take a video URL and a target dialogue and identify the
relevant video frame, returning:

-   Timestamp
-   Frame number
-   Extracted dialogue text
-   Corresponding frame image

Reference video: `https://ok.ru/video/248244667877`\
Target dialogue: **"My mind rebels at stagnation"**

The wording initially made me think this could be an
OCR/subtitle-detection problem.

## 2. Initial Assumption and Manual Inspection

My first assumption was:

``` text
Video → OCR → detected text → frame
```

I manually inspected the reference video before implementing OCR. I
found that the dialogue was **not displayed as text on screen** and
there were no usable subtitles/CC. The line was spoken by the character.

This changed the problem from visual text detection to **spoken-dialogue
localization**:

``` text
Video → Speech-to-Text → dialogue matching → timestamp → frame
```

## 3. Baseline Implementation

I deliberately started with a simple working baseline before adding
complexity.

``` text
Video URL / Local Video
        ↓
Download using yt-dlp
        ↓
Extract mono 16 kHz audio using FFmpeg
        ↓
Whisper transcription
        ↓
Segment-level timestamps
        ↓
Normalize target + transcript
        ↓
Exact/approximate dialogue matching
        ↓
Take matching segment start timestamp
        ↓
Timestamp × FPS
        ↓
OpenCV frame extraction
        ↓
Timestamp + frame number + text + image
```

I chose Whisper for the baseline because it is open source, can run
locally, does not require an API key during inference, and provides
timestamps without requiring a more complicated alignment stack.

### Baseline Matching

Text was normalized by lowercasing, removing punctuation and collapsing
whitespace. I first attempted substring matching and also used word
overlap so that small ASR differences would not immediately cause
failure.

### Baseline Frame Extraction

The initial calculation was:

``` python
frame_number = int(timestamp * fps)
```

OpenCV was then used to seek to and save the resulting frame.

## 4. First Real Validation

I ran the baseline against the actual reference video.

``` text
Target:     My mind rebels at stagnation
Recognized: My mind rebels at stagnation.
Timestamp:  325.00 seconds
Frame:      7792
```

The surrounding transcript confirmed that the match was genuine. This
proved that the basic idea worked, but testing also exposed several
weaknesses.

## 5. Problems Observed in the Baseline

-   **Coarse segment timestamps:** a Whisper segment can contain several
    seconds of speech, so its start does not necessarily equal the start
    of the target phrase.
-   **Brittle matching:** ASR differences such as
    `My mind rebells its stagnation` can break exact matching.
-   **First-match-only behavior:** repeated occurrences were not ranked.
-   **Simple timestamp-to-frame conversion:** `int(timestamp * fps)` is
    approximate, and decoder seeking is not always exact.
-   **No confidence score:** the baseline only indicated whether a match
    existed.
-   **Slow repeated runs:** a full \~54-minute transcription took about
    **18 minutes on my CPU**.
-   **Limited usability:** video and dialogue were hard-coded in
    `main.py`.

## 6. Improvement Strategy

I did not replace the whole approach blindly. I used the baseline as a
reference, identified actual failure modes, and addressed them one at a
time.

``` text
Video URL / Local File
        ↓
Acquisition + validation
        ↓
Audio extraction
        ↓
Coarse transcription
        ↓
Approximate dialogue localization
        ↓
Fine transcription with word timestamps
        ↓
Fuzzy matching
        ↓
Candidate ranking + confidence
        ↓
Timestamp → verified frame
        ↓
Structured JSON + frame image
```

As the logic grew, I split the code into focused `locator/` modules for
acquisition, audio, transcription, matching, frames, confidence,
caching, schema and errors.

## 7. Final Implementation Structure

``` text
main.py
   │
   ├── locator/acquire.py       → URL/local video acquisition
   ├── locator/audio.py         → audio extraction
   ├── locator/transcribe.py    → Whisper transcription
   ├── locator/match.py         → dialogue matching
   ├── locator/confidence.py    → candidate scoring/ranking
   ├── locator/frames.py        → timestamp/frame extraction
   ├── locator/cache.py         → transcript caching
   ├── locator/schema.py        → structured results
   ├── locator/errors.py        → pipeline-specific errors
   └── locator/certs.py         → targeted certificate handling
```

This separation made the implementation easier to test and modify
independently.

## 8. Word-Level Timestamps

The baseline used the start of the complete Whisper segment.

I enabled Whisper's native:

``` python
word_timestamps=True
```

This lets the system use the timestamp of the relevant target word
instead of automatically using the segment start.

I considered WhisperX because it provides stronger forced alignment, but
I deliberately did not add it at this stage. It introduces another
alignment model/dependency stack, while Whisper's native word timestamps
already addressed the major timestamp problem without increasing system
complexity as much.

The word timestamp is still an approximation, so I combined it with more
reliable frame seeking.

## 9. Robust Dialogue Matching

I moved from segment-only substring matching to a timestamped word
stream.

RapidFuzz scores sliding windows around the target length, allowing
small transcription errors such as dropped, inserted or misheard words.

During testing, I discovered that a sliding window over the entire word
stream could combine words from unrelated utterances separated by a
large time gap and produce a spurious high score.

I fixed this by splitting the word stream into contiguous runs before
creating matching windows. A candidate therefore cannot cross a
significant speech gap.

This was a correctness improvement discovered through testing rather
than an assumed edge case.

## 10. Timestamp-to-Frame Improvement

I changed:

``` python
int(timestamp * fps)
```

to rounded frame conversion.

I also implemented verified seeking. After requesting a frame, the code
checks the decoder's actual frame position and reads forward until the
requested frame is reached or passed.

This avoids blindly trusting the first frame returned after a
compressed-video seek.

## 11. Multiple Candidates and Confidence

Instead of returning the first match, the improved matcher keeps
candidates above the matching threshold.

Candidates are ranked using:

-   Match similarity
-   Timing consistency
-   Uniqueness relative to the next-best candidate

The confidence score is:

``` text
65% match similarity
20% timing consistency
15% uniqueness margin
```

with:

``` text
High   >= 85
Medium 65–84
Low    < 65
```

These weights are deliberately simple and explainable rather than
learned from data, since I did not have a labeled dataset for this task.

## 12. Efficiency Improvements

### Caching

Transcripts are cached based on the audio content/model/mode. A
full-video transcript does not depend on the dialogue being searched, so
the same cached transcript can be reused for different queries.

This is especially useful if an evaluator asks for a different dialogue
after the first run.

### Coarse-to-Fine Transcription

Instead of always performing an expensive fine transcription over the
complete video:

``` text
Full video
   ↓
Whisper tiny coarse pass
   ↓
Approximate candidate window
   ↓
Fine Whisper small pass around that window
   ↓
Word timestamps + matching
```

The fine window is padded on both sides.

If the coarse pass finds nothing, the system can fall back to a full
fine-grained search.

## 13. Real Bug Found in Coarse-to-Fine

Testing later dialogue exposed an important false-negative bug.

For example:

``` text
"Madam I think I can smell fire"
"I can't breathe"
```

initially returned `NOT FOUND`.

When I disabled coarse-to-fine and performed a full search, the dialogue
was found.

The issue was not the transcript. The cheap coarse pass had selected the
wrong approximate window. The fine pass then correctly found nothing
inside that wrong window.

### Fix

If the fine pass finds no candidate in the coarse-selected window, the
system now escalates to a whole-video fine search before reporting
`NOT FOUND`.

This sacrifices some speed in the worst case, but a slower correct
result is preferable to an incorrect `NOT FOUND`.

## 14. CLI and Structured Output

The baseline required editing constants in the Python file.

The improved version accepts inputs through a CLI:

``` bash
python main.py --source video.mp4 --dialogue "My mind rebels at stagnation"
```

It also supports a URL directly:

``` bash
python main.py --source "https://ok.ru/video/248244667877" --dialogue "My mind rebels at stagnation"
```

Every run produces structured JSON output covering successful matches,
not-found cases and errors, along with the extracted frame image.

## 15. URL Acquisition and OK.ru Handling

During development, the OK.ru URL initially encountered HTTPS/connection
and CDN certificate issues.

The acquisition stage supports both URL input and local-file input so
development could continue using the exact reference video.

The URL was subsequently retested successfully. The working OK.ru
acquisition command used browser impersonation, retries and a reasonable
resolution limit:

``` bash
python -m yt_dlp --impersonate chrome --retries 20 --fragment-retries 20 -f "best[height<=480][ext=mp4]/best[height<=480]/best" "https://ok.ru/video/248244667877"
```

The application also contains targeted certificate handling rather than
disabling TLS verification. I deliberately avoided
`--no-check-certificate` because disabling certificate verification
would introduce an unnecessary security risk.

The final URL-based run successfully downloaded the reference video and
processed that same downloaded video through the localization pipeline.

## 16. Final Validation

The improved system was run against the reference video and target
dialogue.

``` text
Target dialogue:
My mind rebels at stagnation

Recognized dialogue:
My mind rebels at stagnation.

Timestamp:
324.88 seconds
00:05:24.880

Frame:
7789

Confidence:
100% (High)

Frame image:
result_frame.jpg
```

The baseline result was:

``` text
325.00 seconds
Frame 7792
```

The final result differs by only 0.12 seconds / 3 frames. This is
expected because the baseline used the start of the whole Whisper
segment, whereas the improved version uses the relevant word timestamp.

## 17. Measured Performance

  Version                                          Runtime
  --------------------------------------------- ----------
  Baseline --- full small-model transcription     \~18 min
  Improved --- coarse tiny + fine small            \~4m10s
  Improved --- repeated cached run                  \~6.1s

The cold-run coarse-to-fine approach gave approximately a **4.3×
speedup** over the baseline full transcription.

Repeated searches become much faster because the expensive transcription
is cached.

## 18. Final Architecture

``` text
                  Video URL / Local File
                           ↓
                 Acquisition / Validation
                           ↓
                    FFmpeg Audio
                           ↓
                  Coarse Whisper Pass
                           ↓
                  Rough Match Window
                           ↓
                  Fine Whisper Pass
                   Word Timestamps
                           ↓
                 RapidFuzz Matching
                           ↓
               Candidate Ranking
                 + Confidence
                           ↓
               Verified Frame Seek
                           ↓
          ┌────────────────┴────────────────┐
          ↓                                 ↓
   result_frame.jpg                  structured JSON
```

## 19. Testing and Validation Approach

The system was tested at multiple levels:

-   Matching and normalization functions were tested independently.
-   Frame conversion and verified seeking were tested separately.
-   Confidence/ranking logic was tested independently.
-   Pipeline behavior was tested using controlled test clips.
-   The actual reference video was used for end-to-end validation.
-   URL acquisition was tested using the actual OK.ru source.
-   Later dialogue queries exposed the coarse-to-fine false-negative
    case.
-   Baseline and improved results were compared to confirm temporal
    consistency.

## 20. Why I Chose This Progression

I intentionally started simple and used testing to decide what needed
improvement:

``` text
Understand problem
       ↓
Check assumptions against video
       ↓
Build baseline
       ↓
Run on real input
       ↓
Observe limitations
       ↓
Improve individual failure points
       ↓
Test improvements
       ↓
Fix bugs discovered during testing
       ↓
Measure final system
```

This prevented me from adding techniques just because they sounded more
advanced.

For example:

-   **WhisperX:** investigated, but not adopted because native Whisper
    word timestamps addressed the main timestamp limitation without
    another heavy alignment dependency.
-   **Embedding/semantic matching:** considered, but the observed
    problem was ASR transcription noise rather than semantic
    paraphrasing, so fuzzy string matching was more directly targeted.
-   **Visual best-frame selection:** considered, but the requirement is
    to locate the frame corresponding to the dialogue, not simply the
    sharpest nearby frame.
-   **Parallel transcription:** not necessary for the current
    \~54-minute video after coarse-to-fine processing and caching.

## 21. Remaining Improvements

Possible future improvements include:

### Hybrid OCR

The reference video had no visible subtitles, so OCR was not useful as
the primary signal. However, for a different evaluator-provided video, a
small OCR check around the candidate timestamp could corroborate results
when burned-in captions exist.

### WhisperX / Stronger Forced Alignment

WhisperX could be benchmarked against native Whisper word timestamps if
even tighter temporal localization is required.

### Visual Frame Refinement

A small neighborhood around the predicted frame could be inspected for a
visually better frame, although this must be done carefully because the
requirement is specifically about the dialogue's first appearance.

### Parallel Processing

For substantially longer videos, coarse transcription could be split
into independent chunks and processed concurrently.

## 22. Final Takeaway

The final system evolved from a simple:

``` text
Whisper segment → timestamp → frame
```

into:

``` text
Coarse search
→ fine word-level transcription
→ fuzzy dialogue matching
→ candidate ranking
→ confidence scoring
→ verified frame extraction
→ caching + structured output
```

The main improvement was not simply changing the ASR model. It was
identifying the actual weaknesses of the baseline through real testing
and improving the stages responsible for **accuracy, robustness,
efficiency and usability**.
