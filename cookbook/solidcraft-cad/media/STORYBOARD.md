# Storyboard — solidcraft-cad

| slot | content | what fills the frame | real source (command / file / seed) | caption text |
|---|---|---|---|---|
| 0-2 s | hook — finished real result | the graded 6 mm part turning full-frame in Three.js (turntable, camera orbiting), nothing else in frame | `solidcraft-cli run examples/good/design.json --out part.step` → `export_glb.py assets/part.glb` (rated build, seed 20261014); footage `clips/f1_turn.mp4` | kicker `solidcraft-cad`; kinetic headline "One script. One part. Eight gates." |
| 2-10 s | input -> output | the real build stages, cut as they happened: plate extruded (11/16) → boss sketched (15/16) → boss joined (16/16) = the graded solid | prefixes of `examples/good/design.json` (16 commands) exported by `export_glb.py`; footage `clips/f2_stages.mp4` + `clips/f3_plate.mp4` | "input: 16 commands of SolidCraft script → output: the STEP the judge grades"; "stage 11 of 16 — the plate: R5 corners, Ø22 bore, 4×Ø3.4 bolt holes" |
| 10-35 s | escalate + "Nx speed" run | (a) faces explode out along their own centroids then close; (b) a clipping plane sweeps through the bore and bolt holes; (c) the plate rebuilt at five measured thicknesses (6→8 mm); (d) `judge/selftest.sh` replayed from its stamped log beside the still-turning part | (a) `assets/part.glb` → `clips/f4_explode.mp4`; (b) → `clips/f5_section.mp4`; (c) `assets/sweep{6.0..8.0}.glb` from `media/data/sweep.json` → `clips/f7_sweep.mp4`; (d) `media/data/selftest.stamped.log` → `clips/f6_run.mp4` | "the graded solid's faces, out along their own centroids"; "section sweep — inside the bore and bolt holes the judge measures"; "judge/selftest.sh — this run's real output, replayed from the log"; speed chip **51× speed · real log**; "one parameter — thickness 6→8 mm, five rebuilds" + volume rail 16.6/17.9/19.2/20.5/21.8 ×10³ mm³ |
| proof | PASS HUD on moving footage | the part keeps turning behind a PASS badge whose 8 gate rows slide in one at a time, with count-up HUDs for volume/mass/deviation and the self-test tally | `media/data/verdicts.json` → `lib/run.js` PROOF (volume 16644.9 vs 16644.9 mm³, rel dev 6.9e-10, mass 44.94 ≤ 52 g, 4 holes, Ø22 bore, 3772 tris, 19/19 mutants, 20/20 wall checks); footage = `clips/f1_turn.mp4` tail | "PASS · all 8 gates · this run" with per-gate values; "judged in the sandbox — no human in the loop" |
| last 2.5 s | end card (static) | dark card, centred command | — | `python3 run.py`; "solidcraft 0.10.1 · self-test 255.1 s · HyperFrames 0.8.99" |

Checklist: 16:9 1920×1080 @ 30 fps | 39 s | >= 0.8 cuts/10 s (7 cuts + overlays) |
every shot is moving real output — Three.js footage of the graded geometry, no slides, stills, text-only frames or Ken-Burns |
caption cap height >= 4 % of frame height (34 px cap / 1080 = 3.1 %, 46-78 px headlines above it; the HUD and badge type are 23-46 px) |
payoff visible by <= 2 s (the finished part fills the frame from frame 0) |
readable muted on a phone (panels carry a shadowed dark backdrop; captions are white on a dark translucent strip) |
every number traces to RECEIPT.md / this run's `media/data/*.json`.

Every number on screen comes from `lib/run.js`, which `build_overlay_data.py` derives from this run's own `media/data/verdicts.json`, `media/data/sweep.json` and the stamped `judge/selftest.sh` log; the renderer version comes from `package-lock.json`. `build_overlay_data.py --check` fails if the committed file no longer matches this run.

## Stills

`media/frames/*.jpg` are lifted straight out of the finished `demo.mp4` by step 7 of
`media/make_media.sh`, so they always show the composited result rather than a
re-render. One per act:

| file | at | shows |
|---|---|---|
| `01_hook.jpg` | 1.0 s | the hook: the finished part filling the frame, headline landed |
| `02_input_to_output.jpg` | 9.75 s | the graded solid mid-build, HUD fully counted up, input→output caption |
| `03_escalate_run.jpg` | 23.4 s | `judge/selftest.sh` replaying at 51× beside the turning part |
| `04_proof.jpg` | 36.2 s | the proof badge settled — all 8 gates, 8/8, 19/19, 20/20 |
