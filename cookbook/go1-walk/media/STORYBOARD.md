# Go1: the walk, the fall, the independent test

Every frame before the single 2.5 s end card is a newly rendered, moving
MuJoCo view of recorded judge states. A MuJoCo tracking camera follows
the trunk at 0.98–1.15 m. No interpolated poses, frozen-fall inserts,
screenshots, plots, slides, or image pans appear in the video.
Numbers are measured results, not animated estimates.

| Seconds | Moving simulation | Muted-readable HUD and source |
|---|---|---|
| 0–5 | Close tracking shot of trained seed 101, starting mid-walk | “It learned to walk.” 0.768 m/s, falls 0/192. `data/trained.json`. |
| 5–8 | Close side angle of the same scored walk | Random-weights training, 486.1 s PPO, 4 GiB allocation. `examples/good/curve.json`, `RECEIPT.md`. No tiny curve. |
| 8–9.933 | Real random-initialization fall, seed 202, charcoal floor | “Before training: it falls.” The 64-episode judge measured 100% falls. Cut on the first failed control step, never hold a terminated state. `data/untrained-202.npz`. |
| 9.933–14 | Trained seed 202 walking | “After training: it keeps walking.” Per-seed 0.770 m/s, falls 0/64. `data/trained.json`. |
| 14–18 | Trained seed 303, new close angle | “Tested on starts it never trained on.” Per-seed 0.761 m/s, falls 0/64. |
| 18–23.5 | Trained seed 303 still walking behind a compact HUD | Five checkmarks draw in one by one: speed, falls, torque saturation, baseline margin, repeatability. Values and limits from `data/trained.json`. |
| 23.5–27.5 | Trained seed 202 still walking | “Judge failed all 11 deliberately broken policies.” Eleven checks animate in, with the real 11/11 result always labelled. `data/selftest.json`. |
| 27.5–30 | The only static shot, final simulator frame | Exact launch command; “GPU released after the run.” |

Every moving shot has an advancing replay clock taken from the exact
trace index and a progress bar. All footage plays at real time (the
1.9 s fall occupies 58 frames). All three trained seeds remain episode
zero, fixed before grading.

Neither Remotion nor HyperFrames was installed. The existing Pillow HUD
and ffmpeg compositor writes CRF 0 clips and master, then the CRF 22
H.264 web encode. The more active, close-up cut exceeded 8 MB at CRF 18.
The charcoal floor and sideways gate-shot framing are render-only;
neither changes the robot, physics, poses, or numbers. Rebuild without a lease:

```bash
bash cookbook/go1-walk/media/make_media.sh --render-only
```

The script extracts all 30 decoded 1 fps review frames into ignored
`media/work/review-1fps/`.
