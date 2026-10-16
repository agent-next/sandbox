#!/usr/bin/env python3
"""Render the judge's cavity trace as real animated clips for Remotion.

Reads the trace directory that judge/grade.sh --trace wrote during THIS
run's icoFoam replay (saved time dirs 0.5..30, residuals.csv,
cellcentres.csv) plus the captured stdout log of this run, and renders
30 fps 1920x1080 RGB frames in numpy/PIL:

  * |U| field bilinearly interpolated between saved solver snapshots
  * hundreds of tracer particles advected through the interpolated U
    field with RK2 and drawn as fading streaks
  * wide shots show the square domain panel over a blurred ambient fill
    of the same field (the cavity is 1x1, the frame is 16:9)
  * a camera that pans/zooms for close-ups and push-ins
  * a terminal clip scrolling this run's real judge/setup log

Every pixel of field motion is solver output; particle motion integrates
the real U field.  ffmpeg only encodes the raw frames to H.264 — it never
draws anything.

Usage: render_clips.py <cavity_trace_dir> <run_log> <clips_dir>
Writes clips/{hook,develop,closeup,agent,proof,verdict}.mp4 and
endcard_still.jpg into <clips_dir>.
"""
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
FPS = 30
UMAX = 1.05          # colour normalisation (lid speed = 1 m/s)
FONT_MONO = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'
FONT_MONO_B = '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf'

# ----------------------------- trace loading --------------------------------


def read_centres(trace):
    pts = []
    with open(os.path.join(trace, 'cellcentres.csv')) as f:
        for line in f:
            if line.startswith('x,y') or not line.strip():
                continue
            x, y = line.split(',')
            pts.append((float(x), float(y)))
    return np.array(pts)


def read_U(path):
    vals, started = [], False
    for line in open(path):
        s = line.strip()
        if s.startswith('internalField'):
            started = True
            continue
        if started and s.startswith('('):
            t = s.strip('()').split()
            if len(t) >= 2:
                vals.append((float(t[0]), float(t[1])))
    return np.array(vals)


def load_fields(trace):
    """Return (times, U list shaped (ny,nx,2), grid coords xs,ys)."""
    cent = read_centres(trace)
    xs = np.unique(np.round(cent[:, 0], 6))
    ys = np.unique(np.round(cent[:, 1], 6))
    nx, ny = len(xs), len(ys)
    times = sorted(
        (float(d) for d in os.listdir(trace)
         if re.fullmatch(r'\d+(\.\d+)?', d)
         and os.path.isdir(os.path.join(trace, d)) and float(d) > 0))
    fields = []
    for t in times:
        u = read_U(os.path.join(trace, '%g' % t, 'U'))
        if len(u) != len(cent):
            sys.exit('render_clips: %s/U has %d cells, centres %d'
                     % (t, len(u), len(cent)))
        # blockMesh ordering: x index fastest  ->  k = j*nx + i
        fields.append(u.reshape(ny, nx, 2))
    return np.array(times), fields, (xs, ys)


# ----------------------------- colour map -----------------------------------


def make_lut():
    """Deep navy -> blue -> cyan -> green -> amber -> hot red."""
    stops = [
        (0.00, (11, 18, 26)),     # ink, matches video background
        (0.06, (16, 32, 58)),
        (0.22, (22, 60, 120)),
        (0.42, (42, 120, 214)),   # BLUE
        (0.58, (58, 190, 220)),
        (0.74, (140, 220, 150)),
        (0.88, (235, 160, 60)),   # ORANGE-ish
        (1.00, (245, 84, 48)),    # hot red
    ]
    xs = np.array([s[0] for s in stops])
    lut = np.zeros((256, 3))
    g = np.linspace(0, 1, 256)
    for c in range(3):
        lut[:, c] = np.interp(g, xs, [s[1][c] for s in stops])
    return lut.astype(np.float32) / 255.0


LUT = make_lut()


def bilerp_grid(grid, x, y, xs, ys):
    """Bilinear sample of grid (ny,nx[,2]) at arrays x,y in data coords."""
    gx = (x - xs[0]) / (xs[-1] - xs[0]) * (len(xs) - 1)
    gy = (y - ys[0]) / (ys[-1] - ys[0]) * (len(ys) - 1)
    gx = np.clip(gx, 0, len(xs) - 1.001)
    gy = np.clip(gy, 0, len(ys) - 1.001)
    x0 = gx.astype(np.int32)
    y0 = gy.astype(np.int32)
    x1 = np.minimum(x0 + 1, len(xs) - 1)
    y1 = np.minimum(y0 + 1, len(ys) - 1)
    if grid.ndim == 3:
        fx = (gx - x0)[..., None]
        fy = (gy - y0)[..., None]
    else:
        fx = gx - x0
        fy = gy - y0
    return ((grid[y0, x0] * (1 - fx) + grid[y0, x1] * fx) * (1 - fy)
            + (grid[y1, x0] * (1 - fx) + grid[y1, x1] * fx) * fy)


class Field:
    """Interpolates U between saved snapshots; renders |U| viewports."""

    def __init__(self, times, fields, grid_xy):
        self.times = times
        self.fields = fields
        self.xs, self.ys = grid_xy

    def U_at(self, tau):
        i = int(np.searchsorted(self.times, tau) - 1)
        i = min(max(i, 0), len(self.times) - 2)
        t0, t1 = self.times[i], self.times[i + 1]
        a = 0.0 if t1 == t0 else (tau - t0) / (t1 - t0)
        return self.fields[i] * (1 - a) + self.fields[i + 1] * a

    def render_mag(self, tau, view, w, h):
        """|U| image (h,w) float 0..1 for viewport view=(cx,cy,half_h)."""
        cx, cy, hh = view
        hw = hh * w / h
        ys = np.linspace(cy + hh, cy - hh, h, dtype=np.float32)
        xs = np.linspace(cx - hw, cx + hw, w, dtype=np.float32)
        gx, gy = np.meshgrid(xs, ys)
        mag = np.hypot(self.U_at(tau)[..., 0], self.U_at(tau)[..., 1])
        m = bilerp_grid(mag, gx, gy, self.xs, self.ys)
        # outside the domain: ink (LUT[0]), not streaked boundary values
        m[(gx < 0) | (gx > 1) | (gy < 0) | (gy > 1)] = 0.0
        return np.clip(m / UMAX, 0, 1)

    def colour(self, m01):
        idx = np.clip((m01 * 255).astype(np.int32), 0, 255)
        return LUT[idx]                       # (h,w,3) float


class Particles:
    """Tracers advected with RK2 through the interpolated U field, drawn
    as fading streaks into a persistent trail buffer (w x h pixels)."""

    def __init__(self, n, seed, xs, ys, w, h, trail=0.80):
        rng = np.random.default_rng(seed)
        self.n = n
        self.rng = rng
        self.xs, self.ys = xs, ys
        self.w, self.h = w, h
        self.pos = rng.uniform(0.02, 0.98, (n, 2))
        self.prev = self.pos.copy()
        self.trail = trail
        self.buf = np.zeros((h, w, 3), np.float32)
        self.img = Image.new('L', (w, h), 0)
        self.dr = ImageDraw.Draw(self.img)

    def step(self, U, view, dt_domain):
        p = self.pos
        v1 = bilerp_grid(U, p[:, 0], p[:, 1], self.xs, self.ys)
        mid = p + 0.5 * v1 * dt_domain
        v2 = bilerp_grid(U, mid[:, 0], mid[:, 1], self.xs, self.ys)
        newp = p + v2 * dt_domain
        out = (newp[:, 0] < 0.003) | (newp[:, 0] > 0.997) | \
              (newp[:, 1] < 0.003) | (newp[:, 1] > 0.997)
        # stalled particles (|u| ~ 0 near walls/vortex cores) get recycled
        # so the streak field never thins out
        speed = np.linalg.norm(v2, axis=1)
        stall = out | (speed * abs(dt_domain) < 3e-4)
        stall |= self.rng.uniform(0, 1, self.n) < 0.004
        nst = int(stall.sum())
        if nst:
            newp[stall] = self.rng.uniform(0.03, 0.97, (nst, 2))
        self.prev, self.pos = p, newp
        self.prev[stall] = newp[stall]
        self._draw(view)

    def _to_px(self, pts, view):
        cx, cy, hh = view
        hw = hh * self.w / self.h
        px = (pts[:, 0] - (cx - hw)) / (2 * hw) * self.w
        py = ((cy + hh) - pts[:, 1]) / (2 * hh) * self.h
        return px, py

    def _draw(self, view):
        self.buf *= self.trail
        self.img.paste(0, (0, 0, self.w, self.h))
        x0, y0 = self._to_px(self.prev, view)
        x1, y1 = self._to_px(self.pos, view)
        vis = (x1 > -20) & (x1 < self.w + 20) & \
              (y1 > -20) & (y1 < self.h + 20)
        lw = max(2, self.w // 640)
        for a, b, c, d in zip(x0[vis], y0[vis], x1[vis], y1[vis]):
            self.dr.line([(a, b), (c, d)], fill=200, width=lw)
            r = lw * 1.3
            self.dr.ellipse([c - r, d - r, c + r, d + r], fill=235)
        mask = np.asarray(self.img, np.float32) / 255.0
        tint = np.array([0.92, 0.97, 1.0], np.float32)
        self.buf = np.maximum(self.buf, mask[..., None] * tint)

    def composite(self, base, strength=0.9):
        return np.clip(base * (1 - self.buf * 0.55) + self.buf * strength,
                       0, 1)


def smoothstep(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def cam_at(keys, f, n):
    """Camera keys [(cx,cy,half_h)] eased along the clip."""
    if len(keys) == 1:
        return keys[0]
    seg = (len(keys) - 1) * smoothstep(f / max(n - 1, 1))
    i = min(int(seg), len(keys) - 2)
    a = smoothstep(seg - i)
    return tuple(keys[i][k] * (1 - a) + keys[i + 1][k] * a for k in range(3))


# ------------------------------ encoder -------------------------------------


def encoder(path):
    cmd = ['ffmpeg', '-y', '-loglevel', 'error',
           '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (W, H),
           '-r', str(FPS), '-i', '-',
           '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
           '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', path]
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


def finish(enc, path):
    enc.stdin.close()
    enc.wait()
    if enc.returncode != 0:
        sys.exit('render_clips: ffmpeg failed on %s' % path)


# ----------------------- wide shot (domain panel) ----------------------------

PANEL = 1040          # crisp domain panel, square, centred at PANEL_CX
PANEL_CX = 1010
PANEL_Y = (H - PANEL) // 2
AMBIENT = (480, 270)  # blurred fill rendered at low res, upscaled


def wide_view(cam_hh):
    """Panel viewport: whole domain plus a small margin."""
    return (0.5, 0.5, cam_hh)


def field_clip(field, path, seconds, t0, t1, cam_keys, n_part=650,
               seed=7, flow_gain=1.0, trail=0.80, panel=True):
    """Render a clip.  panel=True: domain panel over blurred ambient fill
    (wide shots); panel=False: cam_keys viewport fills the 16:9 frame
    (close-ups, where the view rect is inside the domain)."""
    n = int(seconds * FPS)
    enc = encoder(path)
    if panel:
        pw, ph = PANEL, PANEL
    else:
        pw, ph = W, H
    part = Particles(n_part, seed, field.xs, field.ys, pw, ph, trail)
    for f in range(n):
        tau = t0 + (t1 - t0) * smoothstep(f / max(n - 1, 1)) \
            if t1 != t0 else t0
        view = cam_at(cam_keys, f, n)
        m = field.render_mag(tau, view, pw // 2, ph // 2)
        base_img = Image.fromarray(
            (field.colour(m) * 255).astype(np.uint8)
        ).resize((pw, ph), Image.BICUBIC)
        U = field.U_at(tau)
        part.step(U, view, flow_gain / FPS)
        comp = part.composite(np.asarray(base_img, np.float32) / 255.0)
        panel_img = Image.fromarray((comp * 255).astype(np.uint8))
        if panel:
            # ambient fill: stretched crop of the same live field, blurred
            crop = panel_img.crop((0, int(PANEL * 0.14),
                                   PANEL, int(PANEL * 0.86)))
            bg = crop.resize(AMBIENT, Image.BICUBIC) \
                      .filter(ImageFilter.GaussianBlur(9)) \
                      .resize((W, H), Image.BICUBIC)
            canvas = Image.eval(bg, lambda v: int(v * 0.42))
            canvas.paste(panel_img, (PANEL_CX - PANEL // 2, PANEL_Y))
            d = ImageDraw.Draw(canvas)
            d.rectangle([PANEL_CX - PANEL // 2 - 3, PANEL_Y - 3,
                         PANEL_CX + PANEL // 2 + 3, PANEL_Y + PANEL + 3],
                        outline=(70, 100, 135), width=3)
        else:
            canvas = panel_img
        enc.stdin.write(np.asarray(canvas, np.uint8).tobytes())
    finish(enc, path)


# --------------------------- terminal clip -----------------------------------


def term_clip(log_path, out_path, seconds, field):
    lines = [l for l in open(log_path, errors='replace').read().splitlines()
             if l.strip()]
    font = ImageFont.truetype(FONT_MONO, 30)
    font_b = ImageFont.truetype(FONT_MONO_B, 30)
    lh, n = 40, int(seconds * FPS)
    rows = (H - 120) // lh
    total = len(lines)
    enc = encoder(out_path)
    pip_w, pip_h = 560, 315
    for f in range(n):
        top = int((f / n) * max(total - rows, 1))
        im = Image.new('RGB', (W, H), (7, 11, 16))
        dr = ImageDraw.Draw(im)
        dr.rectangle([0, 0, W, 64], fill=(16, 24, 33))
        dr.text((40, 16), 'sandbox shell — judge run, this build',
                font=font_b, fill=(140, 170, 200))
        for r in range(rows):
            i = top + r
            if i >= total:
                break
            ln = lines[i][:150]
            col, ft = (175, 195, 210), font
            if 'PASS' in ln or '"passed": true' in ln or 'kill' in ln:
                col = (120, 235, 140)
            if 'FAIL' in ln or '"passed": false' in ln or 'ERROR' in ln:
                col = (250, 110, 90)
            if ln.startswith('===') or ln.startswith('[grade]') \
                    or ln.startswith('[setup]'):
                col, ft = (255, 205, 120), font_b
            if '"gate"' in ln or '"name"' in ln:
                col = (120, 180, 250)
            dr.text((40, 84 + r * lh), ln, font=ft, fill=col)
        # picture-in-picture: the developing field in the corner
        tau = float(field.times[-1]) * f / n
        m = field.render_mag(tau, (0.5, 0.5, 0.56), pip_w // 2, pip_h // 2)
        pip = Image.fromarray(
            (field.colour(m) * 255).astype(np.uint8)
        ).resize((pip_w, pip_h), Image.BICUBIC)
        im.paste(pip, (W - pip_w - 40, H - pip_h - 40))
        dr.rectangle([W - pip_w - 44, H - pip_h - 44, W - 36, H - 36],
                     outline=(90, 120, 150), width=3)
        dr.text((W - pip_w - 40, H - pip_h - 78),
                'icoFoam |U| · t=%4.1f s' % tau, font=font,
                fill=(200, 220, 235))
        enc.stdin.write(np.asarray(im, np.uint8).tobytes())
    finish(enc, out_path)


# --------------------------------- main -------------------------------------


def main():
    trace, logf, clips = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(clips, exist_ok=True)
    times, fields, grid_xy = load_fields(trace)
    field = Field(times, fields, grid_xy)
    print('[clips] %d snapshots t=%g..%g'
          % (len(times), times[0], times[-1]))

    T_END = float(times[-1])

    # hook: converged field already moving, slow push-in
    field_clip(field, os.path.join(clips, 'hook.mp4'), 4.0,
               T_END, T_END, [wide_view(0.56), wide_view(0.50)],
               n_part=800, flow_gain=1.0, seed=11)
    print('[clips] hook.mp4')

    # develop: the whole solve 0 -> T_END spinning up, wide view
    field_clip(field, os.path.join(clips, 'develop.mp4'), 9.0,
               0.0, T_END, [wide_view(0.58), wide_view(0.54)],
               n_part=650, flow_gain=1.6, seed=23)
    print('[clips] develop.mp4')

    # closeup: camera dives into the top-left corner and sweeps the lid
    field_clip(field, os.path.join(clips, 'closeup.mp4'), 6.0,
               T_END * 0.6, T_END,
               [(0.50, 0.70, 0.24), (0.42, 0.84, 0.155), (0.58, 0.74, 0.19)],
               n_part=420, flow_gain=0.55, seed=37, trail=0.85,
               panel=False)
    print('[clips] closeup.mp4')

    # the agent's real sandbox run, sped up (log captured during this build)
    term_clip(logf, os.path.join(clips, 'agent.mp4'), 7.0, field)
    print('[clips] agent.mp4')

    # proof: field keeps moving behind the HUD — slow drift + particles
    field_clip(field, os.path.join(clips, 'proof.mp4'), 8.0,
               T_END * 0.85, T_END,
               [wide_view(0.55), wide_view(0.50)],
               n_part=750, flow_gain=1.0, seed=53)
    print('[clips] proof.mp4')

    # verdict hold: converged field, gentle pull-back under the PASS banner
    field_clip(field, os.path.join(clips, 'verdict.mp4'), 2.5,
               T_END, T_END, [wide_view(0.48), wide_view(0.56)],
               n_part=800, flow_gain=1.0, seed=71)
    print('[clips] verdict.mp4')

    # end-card backdrop still (converged frame, no trails baked in)
    m = field.render_mag(T_END, (0.5, 0.5, 0.56), W, H)
    img = Image.fromarray((field.colour(m) * 255).astype(np.uint8))
    img.save(os.path.join(clips, 'endcard_still.jpg'), quality=88)
    print('[clips] endcard_still.jpg')


if __name__ == '__main__':
    main()
