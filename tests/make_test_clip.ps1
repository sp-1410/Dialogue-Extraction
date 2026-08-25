# Dev-only helper: (re)build tests/fixtures/sample.mp4, a short synthetic
# video with real speech, used to smoke-test the pipeline without a
# network connection or the real reference video.
#
# Uses Windows' built-in System.Speech (SAPI) instead of a Python TTS
# library -- pyttsx3's runAndWait() reliably hangs when driven from a
# non-interactive/headless process on this machine, whereas .NET's speech
# synthesizer does not. ffmpeg must be on PATH.
#
# Run from PowerShell:  .\tests\make_test_clip.ps1

$ErrorActionPreference = "Stop"
$dir = Join-Path $PSScriptRoot "fixtures"
New-Item -ItemType Directory -Force -Path $dir | Out-Null

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.Rate = -2

$lines = @(
  "This is some filler speech before the target line.",
  "My mind rebels at stagnation.",
  "And this is some filler speech after the target line."
)
for ($i = 0; $i -lt $lines.Count; $i++) {
  $synth.SetOutputToWaveFile("$dir\_part$i.wav")
  $synth.Speak($lines[$i])
  $synth.SetOutputToNull()
}
$synth.Dispose()

# 1s of silence between lines, so Whisper produces separate segments
# rather than merging everything into one run-on segment.
ffmpeg -y -f lavfi -i "anullsrc=r=22050:cl=mono" -t 1 "$dir\_silence.wav" | Out-Null

@"
file '_part0.wav'
file '_silence.wav'
file '_part1.wav'
file '_silence.wav'
file '_part2.wav'
"@ | Set-Content -Path "$dir\_concat.txt" -Encoding ascii

ffmpeg -y -f concat -safe 0 -i "$dir\_concat.txt" "$dir\_speech.wav" | Out-Null

# A moving test pattern as the video track -- 25fps deliberately, to also
# exercise the non-30fps case -- muxed with the speech track.
ffmpeg -y -f lavfi -i "testsrc=size=320x240:rate=25" -i "$dir\_speech.wav" `
  -shortest -pix_fmt yuv420p "$dir\sample.mp4" | Out-Null

Remove-Item "$dir\_part0.wav", "$dir\_part1.wav", "$dir\_part2.wav", `
  "$dir\_silence.wav", "$dir\_concat.txt", "$dir\_speech.wav" -ErrorAction SilentlyContinue

Write-Host "Wrote $dir\sample.mp4"
