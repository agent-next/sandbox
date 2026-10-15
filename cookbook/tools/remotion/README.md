# remotion/ — cookbook demo-video template

One reusable Remotion project that turns a demo's real outputs — motion
clips plus the `media/result.json` numbers — into an animated
`media/demo.mp4` that passes `cookbook/tools/video_gate.py`.

## Usage

```bash
# write media/props.json for your demo (shape below), then:
bash cookbook/tools/remotion/render.sh media/props.json media/demo.mp4
```

Remotion is pinned to **4.0.532** (published 2026-10-01, the newest 4.0.x at
least 14 days before 2026-10-15; `npm view remotion time`). Node >= 22.

`render.sh` validates the props, copies every referenced clip into
`public/staged/`, renders the `Demo` composition (1920×1080, 30 fps,
H.264 yuv420p, CRF 18), remuxes with `+faststart`, re-encodes at a higher
CRF if the file is still over 8 MiB, then runs `video_gate.py` and exits
non-zero if the gate fails.

Clip paths in props are resolved relative to the props file's directory.

## Props shape (see `props.example.json`)

```jsonc
{
  "headline": "one sentence stating the measured result",
  "shots": [
    {
      "clip": "clips/sim.mp4",     // required; video files only
      "start": 0,                  // optional: seconds into the clip
      "duration": 7,               // required: on-screen seconds
      "speed": 4,                  // optional: playback rate; >1 draws an "Nx speed" chip
      "hud": [                     // optional: numbers that count up on a glass panel
        {"label": "cutoff", "value": 1000, "unit": "Hz"}
      ]
    }
  ],
  "model3d": {"glb": "clips/part.glb"}, // optional: one turntable shot after the hook
  "verdict": {
    "pass": true,
    "gates": [
      {"name": "cutoff", "measured": "1000 Hz", "threshold": "990-1010"}
    ]
  },
  "launch": {
    "command": "python3 run.py",
    "ask_agent": "build me a 1 kHz low-pass filter and prove it"
  }
}
```

`validate_props.py` enforces the contract without node (what CI runs):
unknown keys are rejected, image clips (`.png`/`.jpg`/…) are rejected —
every shot must be real motion footage — and the estimated timeline must
land inside the gate's 25–60 s window.

## What the composition does

- Every shot plays a real clip via `<OffthreadVideo>`, cropped to fill
  the frame, with a subtle camera push on top. Shots that run out of
  source under `speed > 1` are looped.
- `model3d` inserts a live `@remotion/three` turntable (orbiting camera,
  studio lighting) as the second shot.
- HUD values count up with `spring()`; the headline is a kinetic caption
  in by 0.5 s; the verdict slides in over the still-playing final clip;
  the last 2.5 s is a static end card (dimmed final frame + launch line).
- Shots join with hard cuts — a 0.2 s wipe smooths the join below the gate's
  scene-cut detector (calibration: wipe joins scored 0.0 cuts per 10 s).
- Colour-blind-safe palette: teal `#2EC4B6` = PASS, orange `#F58518` =
  FAIL.
- Font: Inter (OFL) bundled in `public/fonts/` — no network at render.

## Headless system requirements

Node >= 22, Python 3.10+, ffmpeg/ffprobe, plus the Chrome Headless Shell
shared libraries. On Debian 12:

```
apt-get install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
  libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 libatspi2.0-0 \
  libxshmfence1 ffmpeg python3
```

`render.sh` runs `npm ci` and `npx remotion browser ensure` itself.

## Example / proof

```bash
# generate the four lavfi clips + a torus glb (see props.example.json)
mkdir -p clips
for s in "mandelbrot=s=640x360:r=30" \
    "life=s=640x360:r=30:mold=10:ratio=0.1:death_color=#0B3D2E:life_color=#2EC4B6" \
    "testsrc2=s=1920x1080:r=30" "cellauto=s=640x360:r=30:rule=110"; do
  n="${s%%=*}"
  ffmpeg -y -f lavfi -i "$s" -t 8 -vf "scale=1920:1080:flags=neighbor" \
    -c:v libx264 -crf 18 -pix_fmt yuv420p "clips/$n.mp4"
done
python3 gen_glb.py clips/torus.glb
bash render.sh props.example.json /tmp/demo.mp4
```

`preview/` holds three stills extracted at 1 s / mid / proof time.
