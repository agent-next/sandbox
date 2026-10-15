# Storyboard — img2threejs-showcase

Slot order and craft rules: `cookbook/DEMO-STANDARD.md` (Media). Machine check:
`cookbook/tools/video_gate.py`; blind panel verdicts: `media/REVIEW.json`. Every shot is cut by
`make_media.py` from the run directories named in `MANIFEST.json`.

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0-3 s | hook — finished real result | `doraemon-house` rendered, slow push-in | last 3 s of its recording (`shard-*/out/doraemon-house.mp4`) | "32 web 3D scenes, rendered in cloud sandboxes / with no GPU: 30 of 32 rendered" |
| 3-7 s | input -> output | the command and pipeline beside `result.png` | `run.py`, `pipeline.sh`; `result.png` from every `results.json` | "input: one repo, one command ... output: 32 screenshots + clips" |
| 7-16 s | sandbox run, "50x speed" | `tropical-island` from page load through the "Framing" overlay to the lit scene | first 450 s of its 925 s recording, 50x | "tropical-island loading in a sandbox: its first 450 s at 50x speed" |
| 16-38 s | escalate — highlights | 9 rendered targets, slow push-in | last 2.5 s of each target's recording from the run that gave its verdict | "<name> · first frame after <s> s" (from `results.json` `ms`) |
| 38-46 s | every result | all 32 screenshots on three 4x3 pages, verdict colour per tile | the same screenshots as `result.png` | per tile: "<name> <s> s" |
| proof | judge verdicts + controls | counts, the two non-rendered targets, the controls | `results.json` (`verdict`, `canvas.lumaStd`), `visual.json` | "30 of 32 rendered", "control on all 17 sandboxes: WebGL triangle PASS, luma std 91.2" / "empty canvas FAIL, luma std 0" |
| last 3 s | end card | the "Ask your agent" prompt and `python3 cookbook/img2threejs-showcase/run.py` | README | static |

The showcase has no input photos in its repository, so the input slot shows the command and the
pipeline it runs instead of a source image.
