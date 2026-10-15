#!/usr/bin/env python3
"""render3d.py - MuJoCo kinematic replay of judge-graded cart-pole traces.

Loads a --trace CSV written by judge/grade.sh, resamples it to the
requested frame times by linear interpolation of the CSV columns (the
nonlinear plant is never re-simulated), sets qpos = [x, theta] on
cartpole.xml, calls mj_forward, and renders with mujoco.Renderer at
1920x1080 (or a caller-chosen size for side-by-side halves).

GL backend: MUJOCO_GL is tried in order egl -> osmesa (whichever works
first wins and is reported on stderr + recorded by make_media.sh). On a
headless host without libEGL, point CT_OSMESA_LIB at a libOSMesa shared
object and it is dlopen'd before the osmesa context is created.

Overlays are PIL-drawn onto the rendered RGB frame: t, theta, x, |F|,
|tau| sampled at the frame's trace time, the gate line for the scenario
(settle band + settle-time limit, measured value read from the verdict
JSON), and a PASS/FAIL tag that appears at the measured settle time (or
at the moment an actuator/settle limit is breached). The settle band is
also drawn in the scene itself: translucent green geoms on the rail
around x = 0, re-sized to the scenario's x band (+/-0.01 m S1,
+/-0.02 m S2).

Used as a library by make_video.py and make_result.py; the CLI exports
single stills for inspection:

    render3d.py still --candidate good --scenario 1 --time 0.70 \
        --camera hero34 --out /tmp/hero.png
    render3d.py backend          # report which GL backend works
"""
import argparse
import ctypes
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as c  # noqa: E402  (constants + verdict/trace loaders)

XML = os.path.join(HERE, "cartpole.xml")
W, H, FPS = 1920, 1080, 30

_BACKEND = None


def die(msg):
    sys.exit(f"render3d: {msg}")


# ----------------------------------------------------------------- GL setup
_PROBE = """
import ctypes, os
lib = os.environ.get("CT_OSMESA_LIB")
if lib and os.path.isfile(lib):
    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
import mujoco
m = mujoco.MjModel.from_xml_string(
    "<mujoco><visual><global offwidth='64' offheight='64'/></visual>"
    "<worldbody><geom type='sphere' size='.1'/></worldbody></mujoco>")
d = mujoco.MjData(m)
r = mujoco.Renderer(m, height=64, width=64)
mujoco.mj_forward(m, d); r.update_scene(d); r.render(); r.close()
"""


def gl_backend():
    """Pick a working offscreen GL backend. Order: $MUJOCO_GL if set,
    then egl, then osmesa. Each candidate is probed in a subprocess -
    a failed backend (e.g. missing libEGL, no DISPLAY) can abort the
    interpreter instead of raising, so it must not be tried in-process.
    The winner's MUJOCO_GL value is then set for this process."""
    global _BACKEND
    if _BACKEND:
        return _BACKEND
    import subprocess
    want = os.environ.get("MUJOCO_GL")
    order = ([want] if want else []) + ["egl", "osmesa"]
    tried = set()
    for be in order:
        if not be or be in tried:
            continue
        tried.add(be)
        env = dict(os.environ, MUJOCO_GL=be)
        rc = subprocess.call(
            [sys.executable, "-I", "-c", _PROBE], env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if rc == 0:
            os.environ["MUJOCO_GL"] = be
            if be == "osmesa":
                lib = os.environ.get("CT_OSMESA_LIB")
                if lib and os.path.isfile(lib):
                    ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            _BACKEND = be
            print(f"render3d: GL backend = {be}", file=sys.stderr)
            return be
    die("no GL backend works (tried $MUJOCO_GL, egl, osmesa; on a "
        "headless host set CT_OSMESA_LIB to a libOSMesa.so.8 path)")


# ------------------------------------------------------------- trace data
def load_trace(path):
    """CSV columns -> dict of numpy arrays (t, x, xdot, theta, thetadot,
    F, tau)."""
    cols = c_trace(path)
    names = ("t", "x", "xdot", "theta", "thetadot", "F", "tau")
    return {k: np.asarray(v, dtype=float) for k, v in zip(names, cols)}


def c_trace(path):
    import csv
    out = [[] for _ in range(7)]
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].startswith("t_s"):
                continue
            for i, v in enumerate(row):
                out[i].append(float(v))
    return out


def row_at(tr, t):
    """Linear interpolation of every CSV column at time t."""
    return {k: float(np.interp(t, tr["t"], tr[k]))
            for k in tr}


# ------------------------------------------------------- per-scenario gates
def gate_info(candidate, scenario):
    """Overlay description for a candidate/scenario, from data files.

    Returns dict(band, band_unit, var, var_label, limit_s, settle_s,
    settle_ok, tau_peak, tau_ok)."""
    v = c.verdict(candidate)
    g = v["gates"]
    if scenario == 1:
        info = dict(var="theta", sym="\u03b8", unit="rad",
                    band=c.S1_THETA_BAND, limit=c.S1_SETTLE_MAX,
                    gate="s1_theta_settle_s",
                    band2=c.S1_X_BAND, title="scenario 1 - recover from "
                                             "0.15 rad lean")
    else:
        info = dict(var="x", sym="x", unit="m",
                    band=c.S2_X_BAND, limit=c.S2_SETTLE_MAX,
                    gate="s2_x_settle_s",
                    band2=c.S2_X_BAND, title="scenario 2 - return from "
                                             "1 m displacement")
    info["settle_s"] = g[info["gate"]]["value"]
    info["settle_ok"] = g[info["gate"]]["pass"]
    tau_gate = f"s{scenario}_tau_demand_max_Nm"
    info["tau_peak"] = g[tau_gate]["value"]
    info["tau_ok"] = g[tau_gate]["pass"]
    info["passed"] = v["passed"]
    return info


# ------------------------------------------------------------------ fonts
_FONTS = {}


def font(size, bold=False, mono=False):
    key = (size, bold, mono)
    if key not in _FONTS:
        import matplotlib
        from PIL import ImageFont
        base = os.path.join(os.path.dirname(matplotlib.__file__),
                            "mpl-data", "fonts", "ttf")
        name = ("DejaVuSansMono-Bold.ttf" if (bold and mono) else
                "DejaVuSansMono.ttf" if mono else
                "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")
        path = os.path.join(base, name)
        if not os.path.isfile(path):
            path = os.path.join(base, "DejaVuSans.ttf")
        _FONTS[key] = ImageFont.truetype(path, size)
    return _FONTS[key]


def _hex(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


INK = _hex(c.INK)
INK2 = _hex(c.INK2)
MUTED = _hex(c.MUTED)
GOOD = _hex(c.GOOD)
CRIT = _hex(c.CRIT)
BLUE = _hex(c.BLUE)
SURFACE = _hex(c.SURFACE)


def _panel(dr, box, radius=14, fill=(252, 252, 251, 216),
           outline=None, ow=2):
    dr.rounded_rectangle(box, radius=radius, fill=fill,
                         outline=outline, width=ow)


def _pill(dr, xy, text, fg, size=30, pad=(18, 8)):
    f = font(size, bold=True)
    x, y = xy
    tb = dr.textbbox((0, 0), text, font=f)
    w, h = tb[2] - tb[0], tb[3] - tb[1]
    dr.rounded_rectangle((x, y, x + w + 2 * pad[0], y + h + 2 * pad[1]),
                         radius=(h + 2 * pad[1]) // 2, fill=fg + (232,))
    dr.text((x + pad[0], y + pad[1] - tb[1]), text, font=f, fill=(255, 255, 255))
    return w + 2 * pad[0], h + 2 * pad[1]


# ----------------------------------------------------------------- replayer
class Replayer:
    """One cart-pole rig bound to one trace CSV."""

    def __init__(self, trace_csv, scenario, camera="hero34",
                 width=W, height=H, band=None):
        gl_backend()
        import mujoco
        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_path(XML)
        self.data = mujoco.MjData(self.model)
        self.renderer = mujoco.Renderer(self.model, height=height,
                                        width=width)
        self.width, self.height = width, height
        self.camera = camera
        self.scenario = scenario
        self.tr = load_trace(trace_csv)
        self.band = None
        if band is not None:
            self.set_band(band)
        self.t_min = float(self.tr["t"][0])
        self.t_max = float(self.tr["t"][-1])

    def set_band(self, band):
        """Resize/reposition the translucent settle-band geoms to
        +/- `band` m around x = 0 on the rail."""
        m = self.model
        gi = self.mj.mj_name2id(m, self.mj.mjtObj.mjOBJ_GEOM,
                                "settle_strip")
        m.geom_size[gi][0] = band
        for name, sgn in (("settle_edge_lo", -1.0),
                          ("settle_edge_hi", 1.0)):
            gi = self.mj.mj_name2id(m, self.mj.mjtObj.mjOBJ_GEOM, name)
            m.geom_pos[gi][0] = sgn * band
        self.mj.mj_forward(m, self.data)
        self.band = band

    def raw(self, t):
        """Render the interpolated state at trace time t; returns
        (rgb, row dict)."""
        t = min(max(t, self.t_min), self.t_max)
        row = row_at(self.tr, t)
        self.data.qpos[:] = [row["x"], row["theta"]]
        self.mj.mj_forward(self.model, self.data)
        self.renderer.update_scene(self.data, camera=self.camera)
        return self.renderer.render(), row

    def frame(self, t, info, label=None, accent=None, compact=None):
        """Rendered frame + overlay for trace time t."""
        rgb, row = self.raw(t)
        return self.overlay(rgb, t, row, info, label=label, accent=accent,
                            compact=compact)

    def overlay(self, rgb, t, row, info, label=None, accent=None,
                compact=None):
        from PIL import Image, ImageDraw
        im = Image.fromarray(rgb)
        dr = ImageDraw.Draw(im, "RGBA")
        w, h = im.size
        compact = (w < 1200) if compact is None else compact
        accent = accent or BLUE
        fs = 26 if compact else 30
        pad = 14 if compact else 20

        # ---------------- HUD card (top-left)
        title = info["title"]
        if label:
            title = f"{title}  -  {label}"
        if compact:
            title = (label or info["title"])
        lines = [
            (title, fs + 4, True, INK),
            (f"t = {t:4.2f} s", fs, True, INK),
            (f"\u03b8 = {row['theta']:+.4f} rad    "
             f"x = {row['x']:+.4f} m", fs, False, INK2),
        ]
        tau_col = CRIT if abs(row["tau"]) > c.TAU_MAX else INK2
        f_col = CRIT if abs(row["F"]) > c.F_MAX else INK2
        y = pad
        x = pad
        f_t = font(fs + 4, bold=True)
        f_n = font(fs, bold=True)
        f_m = font(fs)
        heights = []
        hud_w = 0
        for text, s, bold, _c2 in lines:
            ff = f_t if s == fs + 4 else (f_n if bold else f_m)
            bb = dr.textbbox((0, 0), text, font=ff)
            heights.append(bb[3] - bb[1] + (10 if s == fs + 4 else 8))
            hud_w = max(hud_w, bb[2] - bb[0])
        act_txt = f"|F| = {abs(row['F']):.2f} N    " \
                  f"|\u03c4| = {abs(row['tau']):.3f} N\u00b7m"
        hud_w = max(hud_w, int(dr.textlength(act_txt, font=f_m)))
        hud_h = sum(heights) + 2 * pad + (fs + 8)
        _panel(dr, (x, y, x + hud_w + 2 * pad, y + hud_h))
        ty = y + pad
        for (text, s, bold, col), lh in zip(lines, heights):
            ff = f_t if s == fs + 4 else (f_n if bold else f_m)
            dr.text((x + pad, ty), text, font=ff, fill=col)
            ty += lh
        # actuator row: |F| and |tau| coloured against limits
        f_act = font(fs)
        dr.text((x + pad, ty), f"|F| = {abs(row['F']):.2f} N    ",
                font=f_act, fill=f_col)
        wF = dr.textlength(f"|F| = {abs(row['F']):.2f} N    ", font=f_act)
        dr.text((x + pad + wF, ty),
                f"|\u03c4| = {abs(row['tau']):.3f} N\u00b7m",
                font=f_act, fill=tau_col)

        # ---------------- gate card (top-right)
        band_str = (f"\u00b1{info['band']:.3f} {info['unit']}"
                    if info["var"] == "theta"
                    else f"\u00b1{info['band']:.2f} m")
        gl1 = (f"gate {info['gate']}: {info['sym']} settles into "
               f"{band_str} by {info['limit']:.0f} s")
        gl2 = (f"measured {info['settle_s']:.2f} s "
               f"\u2264 {info['limit']:.0f} s  "
               + ("PASS" if info["settle_ok"] else "FAIL"))
        f_g = font(fs - 4 if compact else fs - 2)
        g_w = max(dr.textlength(s, font=f_g) for s in (gl1, gl2))
        if compact:
            gx = pad          # stack below the HUD card instead
            gy = y + hud_h + 10
        else:
            gx = w - pad - g_w - 2 * pad
            gy = y
        _panel(dr, (gx, gy, gx + g_w + 2 * pad, gy + 2 * (fs + 4) + 2 * pad))
        col_g = GOOD if info["settle_ok"] else CRIT
        dr.text((gx + pad, gy + pad), gl1, font=f_g, fill=INK2)
        dr.text((gx + pad, gy + pad + fs + 6), gl2, font=f_g,
                fill=col_g, )

        # ---------------- settle/limit tag (bottom-left pill)
        tag = None
        if not info["settle_ok"]:
            trig = info["limit"]
            if t >= trig:
                tag = (f"FAIL \u00b7 {info['sym']} not settled by "
                       f"{info['limit']:.0f} s (measured "
                       f"{info['settle_s']:.2f} s)", CRIT)
        elif t >= info["settle_s"] - 1e-9:
            tag = (f"PASS \u00b7 {info['sym']} settled "
                   f"{info['settle_s']:.2f} s \u2264 "
                   f"{info['limit']:.0f} s", GOOD)
        else:
            tag = ("settling\u2026", MUTED)
        # torque-limit breach tag wins if the candidate fails the tau gate
        if not info["tau_ok"]:
            over = self.tr["t"][np.where(np.abs(self.tr["tau"])
                                         > c.TAU_MAX)[0]]
            if len(over) and t >= over[0]:
                tag = (f"FAIL \u00b7 gate s{self.scenario}_tau: peak "
                       f"|\u03c4| = {info['tau_peak']:.2f} N\u00b7m "
                       f"> {c.TAU_MAX:.0f} N\u00b7m", CRIT)
        pill_h = 0
        if tag:
            _, pill_h = _pill(dr, (pad, h - pad - 2 * fs - 30), tag[0],
                              tag[1], size=fs + 2)

        # ---------------- live breach flash (if currently over tau limit)
        if abs(row["tau"]) > c.TAU_MAX:
            f_b = font((fs - 6) if compact else (fs + 8), bold=True)
            txt = (f"LIMIT BREACHED  |\u03c4| = {abs(row['tau']):.2f} "
                   f"N\u00b7m > {c.TAU_MAX:.0f} N\u00b7m")
            tw = dr.textlength(txt, font=f_b)
            bb = dr.textbbox((0, 0), txt, font=f_b)
            ty = h - pad - 2 * fs - 30 - pill_h - 16 - (bb[3] - bb[1])
            dr.rectangle(((w - tw) / 2 - 12, ty - 6,
                          (w + tw) / 2 + 12, ty + (bb[3] - bb[1]) + 6),
                         fill=(252, 252, 251, 190))
            dr.text(((w - tw) / 2, ty - bb[1]), txt, font=f_b,
                    fill=CRIT)

        # ---------------- sparkline (bottom-right, wide frames only)
        if not compact:
            self._sparkline(dr, t, info, accent, w, h)
        return np.asarray(im)

    def _sparkline(self, dr, t, info, accent, w, h):
        """Time-domain pass line: the scenario variable over the full
        10 s trace with band, measured settle and limit markers, plus a
        playhead."""
        pw, ph = 430, 200
        x0, y0 = w - pw - 22, h - ph - 26
        _panel(dr, (x0, y0, x0 + pw, y0 + ph), radius=10,
               fill=(252, 252, 251, 200))
        pad_l, pad_r, pad_t, pad_b = 52, 14, 30, 26
        px0, py0 = x0 + pad_l, y0 + pad_t
        px1, py1 = x0 + pw - pad_r, y0 + ph - pad_b
        v = self.tr[info["var"]]
        tt = self.tr["t"]
        band = info["band"]
        lo = min(float(v.min()), -band * 1.4)
        hi = max(float(v.max()), band * 1.4)
        span = hi - lo
        lo -= 0.06 * span
        hi += 0.06 * span

        def X(tv):
            return px0 + (tv - tt[0]) / (tt[-1] - tt[0]) * (px1 - px0)

        def Y(vv):
            return py1 - (vv - lo) / (hi - lo) * (py1 - py0)

        # band
        by1, by2 = Y(band), Y(-band)
        dr.rectangle((px0, by1, px1, by2), fill=GOOD + (28,))
        dr.line((px0, by1, px1, by1), fill=GOOD + (140,), width=2)
        dr.line((px0, by2, px1, by2), fill=GOOD + (140,), width=2)
        # settle limit (red) and measured settle (green/red) markers
        dr.line((X(info["limit"]), py0, X(info["limit"]), py1),
                fill=CRIT + (200,), width=2)
        ms = info["settle_s"]
        mcol = GOOD if info["settle_ok"] else CRIT
        if ms < tt[-1]:
            dr.line((X(ms), py0, X(ms), py1), fill=mcol + (220,), width=3)
        # curve
        pts = [(X(a), Y(b)) for a, b in zip(tt, v)]
        dr.line(pts, fill=accent, width=3)
        # playhead
        row = row_at(self.tr, t)
        cx, cy = X(t), Y(row[info["var"]])
        dr.line((cx, py0, cx, py1), fill=INK2 + (110,), width=2)
        dr.ellipse((cx - 6, cy - 6, cx + 6, cy + 6), fill=accent,
                   outline=(255, 255, 255), width=2)
        # labels
        f_s = font(19)
        dr.text((x0 + 10, y0 + 6),
                f"{info['sym']}(t)  \u00b7  band {band_txt(info)}",
                font=f_s, fill=INK2)
        dr.text((px0 - 6, y0 + ph - pad_b + 4), "0", font=f_s, fill=MUTED)
        tl = f"{tt[-1]:.0f} s"
        dr.text((px1 - dr.textlength(tl, font=f_s), y0 + ph - pad_b + 4),
                tl, font=f_s, fill=MUTED)
        # limit tag
        dr.text((X(info["limit"]) + 6, py0 + 4),
                f"limit {info['limit']:.0f} s", font=f_s, fill=CRIT,
                anchor="la")

    def close(self):
        self.renderer.close()


def band_txt(info):
    return (f"\u00b1{info['band']:.3f} rad" if info["var"] == "theta"
            else f"\u00b1{info['band']:.2f} m")


def make(candidate, scenario, camera="hero34", width=W, height=H):
    """Replayer + gate info for one committed candidate trace."""
    info = gate_info(candidate, scenario)
    r = Replayer(c.require(f"{candidate}/s{scenario}_trace.csv"),
                 scenario, camera=camera, width=width, height=height,
                 band=info["band2"])
    return r, info


# --------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("backend")
    st = sub.add_parser("still")
    st.add_argument("--candidate", default="good")
    st.add_argument("--scenario", type=int, default=1)
    st.add_argument("--time", type=float, required=True)
    st.add_argument("--camera", default="hero34")
    st.add_argument("--width", type=int, default=W)
    st.add_argument("--height", type=int, default=H)
    st.add_argument("--label", default=None)
    st.add_argument("--out", required=True)
    args = ap.parse_args()
    if args.cmd == "backend":
        print(gl_backend())
        return
    if args.cmd == "still":
        from PIL import Image
        r, info = make(args.candidate, args.scenario, camera=args.camera,
                       width=args.width, height=args.height)
        frame = r.frame(args.time, info, label=args.label)
        Image.fromarray(frame).save(args.out)
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
