# Receipt — 2026-10-14

Showcase commit `5b3078e92959b86c0dee18742d84473ef0a385c9`, template `node:22-bookworm`
`standard` (4 vCPU / 16 GB, Node v22.23.3), Playwright 1.48.2 Chromium, SwiftShader WebGL.
`npm run build`: 782 MB `dist/`.

## Runs

| round | targets | shards | outcome |
| --- | --- | --- | --- |
| 1 | all 32 | 8 | pixel gate only, 180 s screenshot timeout: 23 drawn, 9 no frame in time; frames showed 7 of the 23 still under the loading overlay -> overlay gate added, timeout 600 s |
| 2 | the 16 not clean in round 1 + 2 known-clean | 6 | overlay gate; one shard hung on its last target (no CPU use) -> 30 min per-target watchdog added |
| 3 | 7 left over (a lost shard + re-checks) | 2 | 9 PASS, 2 controls behaved |
| final | crown-chest, bmx-endurance | 1 | the committed `run.py` end to end, see below |
| 5 | low-poly-humanoid, monster-tree, iphone-duo.html | 3 | `--patience 3` (overlay 900 s, screenshot 1800 s): low-poly-humanoid rendered (240 s); monster-tree still loading (675 s); iphone-duo no frame (2751 s) |

Controls on every shard: `ctl-pos` PASS (luma std 91.2, 713 colours), `ctl-neg` FAIL (std 0,
1 colour).

## Per target (latest gated round; visual = checked by eye and by gemini-3.1-pro-preview, which agreed on all 31 frames)

| target | auto gate | visual (lead + gemini-3.1-pro) | wall s | round/shard |
|---|---|---|---|---|
| awp-medusa-v2 | PASS | RENDERED | 88 | r3/s1 |
| bmx-endurance | PASS | RENDERED | 160 | r1/s2 |
| boxing-man | PASS | RENDERED | 78 | r3/s1 |
| classic-fade | PASS | RENDERED | 95 | r2/s4 |
| crown-chest | PASS | RENDERED | 109 | r2/s4 |
| doraemon-house | PASS | RENDERED | 129 | r1/s7 |
| electric-mouse-mascot | PASS | RENDERED | 32 | r3/s0 |
| gerber-knife | PASS | RENDERED | 60 | r3/s0 |
| girl-character | PASS | RENDERED | 1208 | r2/s0 |
| girl-character-3 | LOADING_OVERLAY | RENDERED | 1317 | r2/s5 |
| glock-ghost-protocol | PASS | RENDERED | 249 | r1/s0 |
| greenvale.html | PASS | RENDERED | 42 | r3/s0 |
| iphone-duo.html | FAIL | NO_FRAME | 2751 | r5/s2 |
| issaca-shotgun | PASS | RENDERED | 99 | r2/s1 |
| leesin | PASS | RENDERED | 178 | r1/s7 |
| low-poly-humanoid | PASS | RENDERED | 240 | r5/s0 |
| m9-doppler | PASS | RENDERED | 70 | r2/s0 |
| man-robot-studio | PASS | RENDERED | 164 | r1/s5 |
| mars-cat | PASS | RENDERED | 1619 | r2/s1 |
| monster | PASS | RENDERED | 104 | r3/s1 |
| monster-tree | PASS | LOADING | 675 | r5/s1 |
| prs-ocean | PASS | RENDERED | 1036 | r2/s2 |
| raz | PASS | RENDERED | 177 | r1/s4 |
| regret-warrior-reconstruction | PASS | RENDERED | 186 | r1/s1 |
| snowy-village | PASS | RENDERED | 511 | r2/s1 |
| sony-wf1000xm3 | PASS | RENDERED | 128 | r2/s5 |
| sora | PASS | RENDERED | 158 | r1/s4 |
| starship-super-heavy | PASS | RENDERED | 150 | r1/s3 |
| talon-doppler-ruby | PASS | RENDERED | 86 | r2/s5 |
| tropical-island | PASS | RENDERED | 925 | r2/s0 |
| warhauler | PASS | RENDERED | 124 | r1/s0 |
| warrior | PASS | RENDERED | 517 | r3/s0 |

`iphone-duo.html` produced no frame within 600 s in rounds 1 and 2 and within 1800 s in round 5.
`low-poly-humanoid` was captured under the overlay in round 1 and its round-2 render hung; round 5
rendered it in 240 s. `monster-tree` passed the pixel gate in rounds 2 and 5 while the scene still
said "Preparing nearby woodland" (HTML over the canvas). `greenvale.html` is a 2D PixiJS page.

Media (`media/`): built by `media/make_media.sh` from rounds 1, 2, 3 and 5, cut to
`media/STORYBOARD.md`; 54 s, 5.8 MiB; `cookbook/tools/video_gate.py` passes (first frame luma mean
115, 1.48 scene cuts per 10 s, static end card). Frame-by-frame caption check by
gemini-3.1-pro-preview on an earlier 30-segment cut: round 1 REJECT (greenvale captioned like a 3D
model; fixed with `notes.json`), round 2 ACCEPT. Blind review panel: see `media/REVIEW.json`.

## Build wall time

`npm run build`: 205 s alone; 671-771 s with 8 shards building at once on one host.

## Deviations

- First template import from `mcr.microsoft.com` was refused (HTTP 400, registry not allowed);
  switched to `docker.io/library/node:22-bookworm` and install Chromium in the sandbox.
- Round-1 canvas readback was all zeros (WebGL without preserveDrawingBuffer); the gate now
  measures the composited screenshot instead.
- Several shard sandboxes expired before their downloads finished on a slow client link
  (~40 KB/s at the time); their videos were lost, verdicts and screenshots were kept. The
  committed run gives each sandbox the render deadline plus one hour and keeps it when a
  download fails.

## Final run of the committed run.py

`python3 cookbook/img2threejs-showcase/run.py --only crown-chest bmx-endurance --shards 1`,
20:35:21Z-20:52:21Z (17 min incl. download): clone 34 s, `npm ci` 31 s, build 6 min 27 s,
Chromium install 99 s, render 193 s, encode 67 s. Verdicts: ctl-pos PASS, ctl-neg FAIL,
crown-chest PASS (47 s, std 56.7), bmx-endurance PASS (74 s, std 27.9); both frames checked by
eye. Sandbox killed and confirmed gone (404).
