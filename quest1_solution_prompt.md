# Prompt for Initial MVP + Improvement Roadmap

I am participating in a hackathon/technical hiring challenge. I need to
build a Python solution for the following problem.

## Problem

Given a video URL and a target dialogue/sentence, identify the point in
the video where that dialogue first appears and return:

1.  Timestamp of the identified dialogue
2.  Frame number, where applicable
3.  Extracted dialogue text
4.  Corresponding video frame as an image

The solution may be evaluated on different videos and dialogue
sentences, so it should **not** be hardcoded to one specific video or
timestamp.

## Important Observation

I manually inspected the provided example video:

https://ok.ru/video/248244667877

The target dialogue is:

> "My mind rebels at stagnation"

There is **no subtitle or dialogue text visibly displayed on the video
screen**. Therefore, OCR should **not** be the primary approach.

The dialogue is spoken in the audio, so I want to approach this as a
**speech-to-text + video-frame localization** problem.

## Initial Approach

The initial pipeline should be:

``` text
Video URL
    ↓
Obtain/download video
    ↓
Extract audio
    ↓
Speech-to-text using Whisper
    ↓
Locate target dialogue in transcript
    ↓
Obtain dialogue timestamp
    ↓
Convert timestamp to video frame
    ↓
Extract/save corresponding frame
    ↓
Return required information
```

## Technology

Use:

-   Python
-   Whisper for speech-to-text
-   FFmpeg for audio/video processing
-   OpenCV for video/frame extraction
-   yt-dlp where appropriate for obtaining the video

Keep the initial implementation simple and practical.

## Initial MVP Requirements

I am currently trying to get a **working MVP first**. Do not
over-engineer the solution initially.

For the first version:

-   Use Whisper segment timestamps.
-   Use simple text normalization/matching to locate the target
    dialogue.
-   Convert the timestamp to a frame using the video's FPS.
-   Extract that frame using OpenCV.
-   Save the frame as an image.
-   Print:
    -   timestamp
    -   frame number
    -   recognized dialogue
    -   output image filename
-   Make the video URL and target dialogue configurable rather than
    hardcoded.
-   Handle the basic case where the dialogue cannot be found.
-   Keep the code understandable because I need to explain it in an
    interview.

## Required Output

The program should produce something conceptually like:

``` text
Target dialogue: My mind rebels at stagnation
Recognized dialogue: My mind rebels at stagnation
Timestamp: 328.42 seconds
Frame number: 8210
Frame image: result_frame.jpg
```

## After the MVP: Improvement Roadmap

After producing the working MVP, do **not** immediately rewrite the
entire solution.

Instead, suggest and implement improvements incrementally, validating
each improvement against the previous version.

Prioritize the improvements in this order:

### 1. Word-level timestamps

Investigate whether Whisper can provide word-level timestamps.

The goal is to move from:

``` text
Segment:
"My mind rebels at stagnation"
start = 328.42
```

towards:

``` text
My          328.42
mind        328.71
rebels      329.03
at          329.60
stagnation  329.82
```

This should allow more accurate identification of the beginning of the
target phrase.

### 2. More robust dialogue matching

Improve matching so that small differences between the input dialogue
and Whisper's transcription do not cause failure.

Consider:

-   lowercase normalization
-   punctuation removal
-   whitespace normalization
-   word overlap
-   fuzzy matching

Do not add unnecessary complexity if simple normalization is sufficient.

### 3. Better timestamp-to-frame conversion

Investigate whether simply doing:

``` python
frame_number = int(timestamp * fps)
```

is sufficiently accurate.

Explain the limitations of using the raw Whisper timestamp and determine
whether refinement is necessary.

### 4. Local timestamp/frame refinement

If the Whisper timestamp is not sufficiently accurate, search a small
time window around the predicted dialogue start and refine the candidate
frame.

The goal is to improve the approximation from:

``` text
Whisper timestamp
    ↓
single frame
```

to:

``` text
Whisper timestamp
    ↓
small candidate window
    ↓
refined timestamp
    ↓
selected frame
```

Only implement this if it provides a meaningful improvement.

### 5. Multiple possible matches

If the target dialogue occurs more than once, identify multiple
candidates and rank them rather than simply returning the first match.

For example:

``` text
Candidate 1 → 02:31
Candidate 2 → 05:28
Candidate 3 → 14:52
```

Select the best candidate based on the matching evidence.

### 6. Confidence scoring

Provide an interpretable confidence score or confidence category for the
selected result.

For example:

``` text
Dialogue match: 94%
Timestamp confidence: High
```

The scoring should be explainable rather than arbitrary.

### 7. Efficiency improvements

Consider the cost of processing long videos.

The provided example video is large, so investigate ways to reduce
unnecessary processing time while maintaining accuracy.

Do not prematurely optimize before establishing a working baseline.

### 8. Configurable command-line interface

Move from hardcoded variables such as:

``` python
VIDEO_URL = ...
TARGET_DIALOGUE = ...
```

towards something like:

``` bash
python main.py --url "VIDEO_URL" --dialogue "TARGET DIALOGUE"
```

The final solution should be usable with a different video and dialogue
without modifying the source code.

### 9. Error handling and structured output

Add clear handling for cases such as:

-   video cannot be downloaded
-   audio extraction fails
-   target dialogue is not found
-   multiple weak matches exist
-   frame extraction fails

Where useful, produce structured output such as JSON in addition to the
human-readable console output.

## Development Method

For every improvement:

1.  Explain the problem with the previous approach.
2.  Explain the proposed improvement.
3.  Implement the improvement.
4.  Test or demonstrate the change.
5.  Explain the result.
6.  Explain trade-offs.
7.  Clearly state whether the improvement is actually implemented or
    only proposed.

Do **not** claim that an improvement has been implemented if it has only
been discussed.

The goal is to create a solution that is technically strong but still
understandable and defensible in an interview.

## Documentation Requirement: approach.md

I need to submit an `approach.md` file explaining how I arrived at the
solution.

The documentation should reflect the **actual evolution** of the
solution, including:

-   Initial understanding of the problem
-   Initial assumption that OCR might be useful
-   Manual inspection of the video
-   Observation that there is no visible dialogue/subtitle text
-   Realization that this is primarily a spoken-dialogue localization
    problem
-   Research/selection of speech-to-text
-   Initial Whisper-based approach
-   Conversion from speech timestamp to video frame
-   Problems discovered during testing
-   Improvements introduced and why they were introduced
-   Limitations of each version
-   Future improvements that were considered but not implemented

Do not rewrite history or claim that an advanced technique was part of
the original approach if it was introduced later.

## Documentation Requirement: prompts.md

I also need to submit a `prompts.md` file documenting the prompts used
with LLMs during development.

For meaningful LLM-assisted decisions, preserve:

-   The exact prompt used
-   Why the prompt was used
-   What insight/result it produced
-   What decision was made based on it
-   How that decision affected the implementation

The prompts should represent the **actual development process** and
should not be artificially created after the fact.

## Important Constraint

For now, focus on producing the **initial working MVP** and then
improving it step-by-step.

Do not build a huge production system immediately.

Clearly distinguish between:

-   implemented functionality
-   investigated approaches
-   proposed future improvements

The final solution should be practical, testable, explainable, and
suitable for a hackathon technical interview.
