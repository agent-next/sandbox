# media/video — the HyperFrames composition for demo.mp4

`media/make_media.sh` drives everything here. Nothing in this directory is run
by hand.

```
shots/f1_turn.html    the graded part, turning            (dark)
shots/f2_stages.html  the real build stages 11/15/16      (light / blueprint)
shots/f3_plate.html   the plate close-up                  (light)
shots/f4_explode.html faces out along their centroids     (dark)
shots/f5_section.html a clipping plane through the bore    (light)
shots/f6_run.html     judge/selftest.sh replayed, 51x      (dark, terminal pane)
shots/f7_sweep.html   the five thickness rebuilds          (light)
index.html            the master timeline: composes those clips and adds
                      every overlay (kinetic headline, count-up HUDs, PASS
                      badge, volume rail, speed chip, end card)
lib/part.js           the shared Three.js rig and glb loader
lib/run.js            GENERATED: every number on screen, from this run
lib/run.template.js   its source template
lib/VENDORED.md       provenance of the vendored Three.js files
assets/*.glb          GENERATED: this run's STEP output, meshed by OpenCascade
```

Two rules the composition is built around:

1. **Footage is real.** Each shot renders the STEP SolidCraft wrote this run
   (`export_glb.py` → `assets/*.glb`) as moving Three.js output. `index.html`
   never draws a chart, card or slide — it only layers captions and numbers over
   that footage. ffmpeg is called once, to encode.

2. **No invented numbers.** `index.html` and the shots read `lib/run.js`, which
   `build_overlay_data.py` derives from `media/data/verdicts.json`,
   `media/data/sweep.json` and the stamped `judge/selftest.sh` log — and from
   nothing else. After any run:
   `python3 media/video/build_overlay_data.py --check` fails if the committed
   `lib/run.js` no longer matches this run's numbers, so stale footage cannot be
   quietly re-labelled.

The dark/light alternation between shots is deliberate: the chapters are all
close-ups of the same grey part, so without the palette change each shot change
would be a near-invisible dissolve rather than a readable cut
(`cookbook/tools/video_gate.py`'s scene-cut check is what this is measured by).

Pinned deps: `package.json` / `package-lock.json` (HyperFrames 0.8.99, three
0.180.0 — the exact version, not a range). `npm --prefix media/video ci` to
install; Node >= 22.
