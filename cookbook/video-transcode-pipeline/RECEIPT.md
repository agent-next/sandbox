# RECEIPT — `cookbook/video-transcode-pipeline/`

Real command output from two fresh sandboxes, pasted as produced. Both runs
are the committed code on this branch, driven by

```bash
python3 cookbook/video-transcode-pipeline/run.py --ref sbx/demo-video-transcode-pipeline-f4
```

from outside the sandbox, on the default 2 vCPU sandbox shape.

## Two fresh-sandbox runs, side by side

Both sandboxes started with no toolchain at all: `judge/setup.sh` downloaded
and verified the pinned Debian packages, built whisper.cpp from the pinned
SHA, and fetched the model, from nothing.

| | RUN-A | RUN-B |
|---|---|---|
| `sbx create --timeout-min 30` | exit 0, 1.8 s | exit 0, 2.4 s |
| `git clone --depth 1 -b <branch>` | exit 0, 3.9 s | exit 0, 5.1 s |
| `judge/setup.sh` (fresh) | exit 0, 258.2 s | exit 0, 263.1 s |
| `judge/selftest.sh` | exit 0, 265.3 s | exit 0, 266.5 s |
| `judge/grade.sh examples/good` | exit 0, 42.3 s | exit 0, 34.8 s |
| kill rate | **7/7 = 100 %** | **7/7 = 100 %** |
| verdict JSON | identical (see below) | identical |
| `run.py` exit code | **0** | **0** |
| sandbox killed and confirmed gone | yes | yes |

`python3` comparison of the two verdicts with `timing` removed →
**identical**. The only fields that differ between runs are inside `timing`
(the standard allows exactly that).

```
RUN-A timing: pipeline 21.693 s, geometry 0.688 s, duration 0.281 s,
              keyframes 0.292 s, counter 14.237 s, poster 0.578 s, captions 0.857 s
RUN-B timing: pipeline 17.164 s, geometry 0.818 s, duration 0.301 s,
              keyframes 0.314 s, counter 11.883 s, poster 0.583 s, captions 0.977 s
```

The setup and self-test times differ by seconds between the two runs
(whisper.cpp compiles from source and the self-test grades eight
pipelines); everything the verdict depends on is identical.

## RUN-A, as pasted from the terminal

```text
run: [   1.8s] sbx create --timeout-min 30 -> exit 0
run: sandbox 01a1402e-d4e7-7bd3-85b8-551567a104e2
run: [   3.9s] git clone -> exit 0
run: [ 258.2s] judge/setup.sh -> exit 0
run: [ 265.3s] judge/selftest.sh -> exit 0
selftest: grading known-good /home/user/vtp-demo-repo/cookbook/video-transcode-pipeline/examples/good
selftest: known-good PASSED all gates
mutants: wrong-resolution  edit: 720p rendition scaled to 1280x960 instead of 1280x720
mutants: truncated  edit: renditions cut to 10 s (-t 10 on the input)
mutants: dropped-segment  edit: seg-004.ts removed from the 360p playlist (the .ts files stay)
mutants: empty-captions  edit: captions.vtt replaced by WEBVTT plus one empty cue
mutants: wrong-keyframe  edit: keyframe interval 8 s (KEYINT 192) instead of 4 s
mutants: blank-poster  edit: poster.png replaced by a solid black frame
mutants: silent-renditions  edit: renditions carry no audio stream (-an)
mutants: wrote 7 mutants to /tmp/tmp.43X0k4FVi9/mutants
selftest: killed    blank-poster (gate: poster)
selftest: killed    dropped-segment (gate: keyframes)
selftest: killed    empty-captions (gate: captions)
selftest: killed    silent-renditions (gate: geometry)
selftest: killed    truncated (gate: duration)
selftest: killed    wrong-keyframe (gate: keyframes)
selftest: killed    wrong-resolution (gate: geometry)
selftest: kill rate 7/7 = 100%
selftest: determinism OK (two --seed 1 runs identical, timing excluded)
selftest: OK
run: [  42.3s] judge/grade.sh examples/good -> exit 0
{ ...verdict JSON, below... }
run: SUMMARY passed=True counter_360p=1.0 wer=0.0588 cues=6 keyframe_gaps=[4.0, 4.0, 4.0, 4.0] duration_dev=0.0213
run: killed and confirmed gone: 01a1402e-d4e7-7bd3-85b8-551567a104e2
EXIT=0
```

## The verdict JSON (byte-identical in RUN-A and RUN-B, `timing` excluded)

```json
{
  "artifact": "examples/good",
  "seed": 0,
  "source": { "width": 640, "height": 360, "fps": 24, "duration_s": 20.0 },
  "passed": true,
  "judge_unchanged": true,
  "gates": {
    "runs":      { "passed": true },
    "geometry":  { "passed": true,
                   "360p": { "width": 640, "height": 360, "video": "h264", "audio": "aac", "segments": 10 },
                   "720p": { "width": 1280, "height": 720, "video": "h264", "audio": "aac", "segments": 10 } },
    "duration":  { "passed": true,
                   "360p": { "seconds": 20.0213, "deviation_s": 0.0213 },
                   "720p": { "seconds": 20.0213, "deviation_s": 0.0213 } },
    "keyframes": { "passed": true,
                   "360p": { "keyframes": 5, "gaps": [4.0, 4.0, 4.0, 4.0], "min_gap": 4.0, "max_gap": 4.0 },
                   "720p": { "keyframes": 5, "gaps": [4.0, 4.0, 4.0, 4.0], "min_gap": 4.0, "max_gap": 4.0 } },
    "counter":   { "passed": true,
                   "360p": { "frames": 480, "samples": 40, "matched": 40, "match_fraction": 1.0, "misses": [] },
                   "720p": { "frames": 480, "samples": 40, "matched": 40, "match_fraction": 1.0, "misses": [] } },
    "poster":    { "passed": true, "width": 640, "height": 360,
                   "distinct_levels": 251, "distinct_fraction": 0.9805,
                   "nonmodal_fraction": 0.6821, "background_luma": 0, "centre_luma": 224 },
    "captions":  { "passed": true, "cues": 6, "speech_seconds": 7.056,
                   "coverage": 0.9297, "wer": 0.0588, "ref_words": 17,
                   "errors": 1, "echoed_transcript": false }
  },
  "timing": { "pipeline_s": 21.693, "geometry_s": 0.688, "duration_s": 0.281,
              "keyframes_s": 0.292, "counter_s": 14.237, "poster_s": 0.578,
              "captions_s": 0.857 }
}
```

## Tool versions (judge/VERSIONS.txt, written by setup.sh in the sandbox)

```text
# video-transcode-pipeline judge: versions installed by judge/setup.sh
# (Linux x86_64)
ffmpeg version 5.1.9-0+deb12u1 Copyright (c) 2000-2026 the FFmpeg developers
ffprobe version 5.1.9-0+deb12u1 Copyright (c) 2007-2026 the FFmpeg developers
eSpeak NG text-to-speech: 1.51  Data at: /usr/lib/x86_64-linux-gnu/espeak-ng-data
whisper.cpp 0c7be696371069e0baa2515ed7aa08d5a5473aa6
cmake cmake version 4.4.4
python3 3.12.15
model ggml-tiny.en.bin sha256 921e4cf86…89920b1f
```

## Criterion-by-criterion evidence

1. **Pinned + sha256-checked.** `judge/setup.sh` verifies every download with
   `sha256sum -c` before installing anything: the Debian `.deb` files, the
   whisper.cpp tarball at `0c7be696…`, the `ggml-tiny.en.bin` model, the
   DejaVu font package, and (via pip) `cmake==4.4.4`. `judge/requirements.txt`
   pins the matplotlib wheel set with `--require-hashes` for
   `media/make_media.sh` only — the judge is stdlib-only. The sha256s were
   computed from the files the pinned URLs serve; a mismatch exits non-zero
   and deletes the bad download so a re-run re-fetches it.
2. **Determinism.** `selftest.sh` runs `grade.sh --seed 1` twice and compares
   the verdict JSON with `timing` removed (paste above:
   `determinism OK`). Wall times live only under the `timing` key; the two
   fresh-sandbox runs above produced identical verdicts.
3. **Two fresh-sandbox runs.** Side-by-side table above; both exit 0, both
   verdicts identical.
4. **Judge strength.** Kill rate 100 % with 7 single-edit mutants. Every gate
   compares against something the artifact does not control: the burned
   frame counter (an independent, per-frame analytic value), the known
   transcript (WER), ffprobe's reading of the bytes, and the fixture's own
   geometry and duration.
5. **The demo the lead found incomplete now runs end to end** — `run.py`
   exits 0 in a fresh sandbox (two runs above), and every file
   `DEMO-STANDARD.md` lists is present.

## Deviations

- **The fixture speech clip is espeak-ng-rendered, not a recorded
  performance.** SPEC.md allows this ("espeak-ng-rendered if a recording is
  unavailable"). It keeps the fixture deterministic and free of third-party
  audio licensing; `fixtures/TRANSCRIPT.txt` is two public-domain pangrams.
- **`grade.sh` grades the *directory* holding `pipeline.sh`**, not a single
  file: the artifact is a script plus the fixtures it reads. Passing
  `examples/good` is the documented form.
- **The counter OCR is fixture-specific.** It renders its digit templates
  from the same font, size and crop `fixtures/gen_fixtures.sh` uses, rather
  than being a general OCR. It is the oracle for this fixture; a different
  counter layout would need a different decoder. Stated in README limits.
- **G5 samples by frame index, not by timestamp.** Seeking into HLS
  renditions is unreliable (the decoder lands on the preceding keyframe), so
  the judge decodes each rendition once and compares frame *i*'s counter to
  *i*. That detects dropped and duplicated frames; a uniformly re-timed
  rendition would pass G5 and is caught by G3 instead.
- **`judge/requirements.txt` is pinned for CPython 3.12 manylinux x86_64**
  (the interpreter `judge/VERSIONS.txt` records). Wheel tags are
  interpreter-specific.
- **Third-party content**: the pinned Debian packages (ffmpeg — LGPL/GPL,
  espeak-ng — GPLv3, DejaVu fonts — permissive) and whisper.cpp (MIT,
  licence kept in its source tree, cited by URL + SHA in `judge/setup.sh`).
  The fixtures, pipeline and judge are original to this demo.
- **`media/` needs the plotting venv**; `judge/setup.sh` does not install it.
  `media/make_media.sh` creates it from `judge/requirements.txt`.
