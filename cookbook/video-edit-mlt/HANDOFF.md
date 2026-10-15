# Handoff — video-edit-mlt (2026-10-15)

Work in progress on this branch. Delete this file in the last commit before
merge.

## State

| item | state |
|---|---|
| judge, `run.py`, tests | done: two fresh `run.py` runs pass at 5ef90b8c; independent reproduction passes (`REPRODUCE.md`); 27 unit tests OK; 11/11 mutants rejected at their intended gates |
| video source | rewritten in Remotion 4.0.531 (`media/video/`) as moving real renders with an animated HUD, per `cookbook/DEMO-STANDARD.md` (no slides) |
| test render | 37.5 s, yuv420p, 6.04 MiB, motion_fraction 0.578, scene cuts 3.2 per 10 s; `video_gate.py` passed every check |
| frame check | the off-by-one scene was broken: `<Loop>` defaults to absolute-fill, so one video covered the whole screen instead of two side by side. Fixed in 70928927 (`layout="none"`). That render was not committed. |
| committed `media/demo.mp4` | still the old slide video; it must be re-rendered |
| `media/REVIEW.json` | still the "not done" placeholder |
| code review, merge, gallery entry | not done |

## Next steps

1. In a fresh sandbox (`sbx create --timeout-min 240`; the timeout is the
   sandbox's whole lifetime), run `bash cookbook/video-edit-mlt/media/make_media.sh`.
   The full run takes about 25 min:

   | step | time |
   |---|---|
   | setup | about 80 s |
   | grade | — |
   | selftest | about 200 s |
   | off-by-one grade | — |
   | `npm ci` | 2–3 min |
   | Remotion render (1 core) | about 15 min |

2. Copy these files back and check each sha256:
   - `media/demo.mp4`, `media/video_gate.json`, `media/MANIFEST.json`
   - `media/result.json`, `media/result.png`, `media/loop.png`

   Then run `python3 -m pytest -q cookbook/tools/test_video_gate.py -k baseline`.
3. Open the frames yourself (1 s, 25 %, 60 %, and the proof scene at about 32 s):
   - Confirm the good edit and the off-by-one cut now play side by side.
   - Commit 4 frames to `media/frames/*.jpg`, each under 250 KB.
   - Point `result.json` hero/gallery at them, then run `python3 cookbook/tools/result.py check`.
4. Blind panel per `cookbook/tools/video_review_prompt.md`, with two vision
   models from different families.
   - Store both raw verdicts in `media/REVIEW.json`.
   - Fix what is now stale:
     - the REVIEW.json line in `make_media.py manifest`;
     - `media/STORYBOARD.md`, whose rows still describe the old slides;
     - the README's "40-second demo";
     - the RECEIPT media paragraph.
5. Independent code review of the PR, fix the findings, delete this file, merge.
6. Add the gallery entry.

## Pitfalls

- `remotion render --concurrency=2` fails because the sandbox exposes 1 core. Use the default.
- Remotion's H.264 output is `yuvj420p`. `make_media.sh` now encodes with
  `-vf scale=out_range=tv` to get `yuv420p`.
- Inside `sbx exec`, a `ps | awk '/make_media/'` kill matches the exec's own
  shell line and kills itself. Kill by PID instead.
- `sbx exec` with a `setsid` background child may not return, but the job
  keeps running. Read its log file.
