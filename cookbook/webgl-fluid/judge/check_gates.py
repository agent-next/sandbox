#!/usr/bin/env python3
"""
WebGL-fluid judge — evaluate the six gates of SPEC.md on one scene run.

Usage: check_gates.py <artifact_dir> <blob.json> [--json out.json]
                     [--save-frames DIR]

  <artifact_dir>  scratch copy of the artifact (config.json is read from it)
  <blob.json>     JSON blob produced by judge/run_scene.cjs — contains the
                  judge's own per-frame measurements of the dye texture
                  (sha256, mass, centroid, per-obstacle mass, NaN flag,
                  SSIM between the two determinism runs)

Everything in the verdict comes from the judge's readback of the GPU dye
texture plus the artifact's declared config.json — never from numbers the
artifact's own code produced.  Gate rules are SPEC.md, "Gates".
"""

import json
import math
import os
import struct
import sys
import zlib

# --- SPEC bounds for the artifact's declared config -------------------------
CONFIG_BOUNDS = {
    'SIM_RESOLUTION': (64, 128),
    'DYE_RESOLUTION': (128, 256),
    'DENSITY_DISSIPATION': (0.5, 2.0),
    'VELOCITY_DISSIPATION': (0.0, 4.0),
    'PRESSURE': (0.0, 1.0),
    'PRESSURE_ITERATIONS': (1, 40),
    'CURL': (0, 50),
    'SPLAT_RADIUS': (0.01, 1.0),
    'SPLAT_FORCE': (0, 10000),
}
REQUIRED_FALSE = ('SHADING', 'BLOOM', 'SUNRAYS', 'COLORFUL')

SSIM_MIN = 0.99          # gate 2 fallback when hashes differ
ANGLE_MIN_DEG = 60.0     # gate 3: displacement within this of probe v
DIST_MIN = 0.02          # gate 3: minimum displacement, normalized units
SUBSTEP = 6              # gate 3: forward-progress granularity (frames)
OBSTACLE_FRAC = 0.005    # gate 4: max in-obstacle dye mass fraction
MASS_GROW_TOL = 1.001    # gate 5: per-step mass-growth tolerance (quantization)
DECAY_LO, DECAY_HI = 0.75, 1.25  # gate 5: measured/configured decay band
MIN_MASS = 0.5           # gate 6: not blank
MIN_NONBLANK = 100       # gate 6: extra floor when float readback unavailable


def fail(msg):
    print('[check_gates] ERROR: %s' % msg, file=sys.stderr)
    sys.exit(2)


def load_artifact_config(artifact):
    cfg_path = os.path.join(artifact, 'config.json')
    if not os.path.isfile(cfg_path):
        fail('missing config.json in %s' % artifact)
    try:
        with open(cfg_path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        fail('config.json is not valid JSON: %s' % e)


def config_violations(cfg):
    """Declared-config contract violations (SPEC.md, Artifact)."""
    out = []
    over = cfg.get('config') or {}
    for k in REQUIRED_FALSE:
        if over.get(k, False) is not False:
            out.append('config.%s must be false' % k)
    for k, (lo, hi) in CONFIG_BOUNDS.items():
        if k in over:
            v = over[k]
            if not isinstance(v, (int, float)) or not (lo <= v <= hi):
                out.append('config.%s=%r outside [%s, %s]' % (k, v, lo, hi))
    for key in ('dt', 'frames', 'probe', 'decay', 'obstacles', 'aim', 'show'):
        if key not in cfg:
            out.append('missing key %r' % key)
    if out:
        return out
    if not isinstance(cfg['obstacles'], list) or not cfg['obstacles']:
        out.append('obstacles must be a non-empty list')
    p = cfg['probe']
    if p.get('trackFrames', 0) < SUBSTEP:
        out.append('probe.trackFrames must be >= %d' % SUBSTEP)
    if p['frame'] + p['trackFrames'] >= cfg['frames']:
        out.append('probe window exceeds frames')
    if 'box' in p:
        for k in ('x0', 'y0', 'x1', 'y1'):
            if k not in p['box']:
                out.append('probe.box.%s missing' % k)
    else:
        out.append('probe.box missing')
    d = cfg['decay']
    for k in ('frame', 'x', 'y', 'rgb', 'box', 'trackFrames'):
        if k not in d:
            out.append('decay.%s missing' % k)
    if 'box' in d:
        for k in ('x0', 'y0', 'x1', 'y1'):
            if k not in d['box']:
                out.append('decay.box.%s missing' % k)
    if d.get('frame', 0) + d.get('trackFrames', 0) >= cfg['frames']:
        out.append('decay window exceeds frames')
    return out


def write_png(path, w, h, rgba):
    """RGBA bytes -> PNG, rows flipped (readPixels row 0 is v=0/bottom)."""
    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + \
            struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    raw = bytearray()
    for row in range(h - 1, -1, -1):
        raw.append(0)
        raw += rgba[row * w * 4:(row + 1) * w * 4]
    png = (b'\x89PNG\r\n\x1a\n'
           + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
           + chunk(b'IDAT', zlib.compress(bytes(raw), 6))
           + chunk(b'IEND', b''))
    with open(path, 'wb') as f:
        f.write(png)


def gate(name, passed, **detail):
    return {'gate': name, 'passed': bool(passed), **detail}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    json_out = frames_dir = None
    argv = sys.argv[1:]
    i = 0
    while i < len(argv):
        if argv[i] == '--json':
            json_out = argv[i + 1]; i += 2
        elif argv[i] == '--save-frames':
            frames_dir = argv[i + 1]; i += 2
        else:
            i += 1
    if len(args) < 2:
        fail('usage: check_gates.py <artifact_dir> <blob.json> '
             '[--json out.json] [--save-frames DIR]')
    cfg = load_artifact_config(args[0])
    try:
        with open(args[1]) as f:
            blob = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        fail('cannot read blob %s: %s' % (args[1], e))

    violations = config_violations(cfg)
    run1, run2 = blob.get('run1') or {}, blob.get('run2') or {}
    f1, f2 = run1.get('frames') or [], run2.get('frames') or []
    nframes = cfg.get('frames', 0)
    errors = blob.get('console_errors') or []
    meta = blob.get('meta') or {}

    # -- gate 1: loads clean --------------------------------------------------
    complete = (len(f1) == nframes and len(f2) == nframes
                and run1.get('complete') == nframes
                and run2.get('complete') == nframes)
    g1 = gate('loads_clean',
              blob.get('ok') is True and not errors and complete
              and bool(meta.get('renderer')) and not violations,
              console_errors=len(errors),
              run_frames=[len(f1), len(f2)],
              expected_frames=nframes,
              renderer=meta.get('renderer'),
              dye_size=[meta.get('dyeWidth'), meta.get('dyeHeight')],
              float_readback=meta.get('floatRead'),
              config_violations=violations,
              error=blob.get('error'))

    # -- gate 2: deterministic ------------------------------------------------
    hash_equal = True
    ssims = []
    for k in range(min(len(f1), len(f2))):
        if f1[k].get('hash') == f2[k].get('hash'):
            ssims.append(1.0)
        else:
            hash_equal = False
            s = f2[k].get('ssim')
            if s is None:
                s = 0.0
            ssims.append(s)
    mean_ssim = sum(ssims) / len(ssims) if ssims else 0.0
    g2 = gate('deterministic',
              (len(f1) == nframes and len(f2) == nframes
               and (hash_equal or mean_ssim >= SSIM_MIN)),
              hash_equal=hash_equal,
              mean_ssim=round(mean_ssim, 6),
              min_ssim=round(min(ssims) if ssims else 0.0, 6),
              rule=('identical sha256 per frame' if hash_equal
                    else 'mean SSIM >= %s' % SSIM_MIN))

    # -- gate 3: dye advects along its declared velocity ----------------------
    # Centroid of the dye inside the artifact's probe.box (the probe splat
    # only — other dye lives outside it during the window).
    p = cfg['probe']
    pf, track = p['frame'], p['trackFrames']
    vx, vy = float(p['dx']), float(p['dy'])
    vnorm = math.hypot(vx, vy)
    detail = {'window': [pf, pf + track], 'declared_v': [vx, vy]}
    ok3 = False
    if vnorm > 0 and pf + track < len(f1):
        uhat = (vx / vnorm, vy / vnorm)
        cents = [(fr.get('tcx') if fr.get('tcx') is not None
                  else fr.get('cx'),
                  fr.get('tcy') if fr.get('tcy') is not None
                  else fr.get('cy')) for fr in f1]
        if all(c[0] is not None and c[1] is not None
               for c in cents[pf:pf + track + 1]):
            d = (cents[pf + track][0] - cents[pf][0],
                 cents[pf + track][1] - cents[pf][1])
            dnorm = math.hypot(*d)
            cosang = ((d[0] * vx + d[1] * vy) / (dnorm * vnorm)
                      if dnorm > 0 else -1.0)
            forward = []
            for k in range(pf, pf + track - SUBSTEP + 1):
                step = ((cents[k + SUBSTEP][0] - cents[k][0]) * uhat[0]
                        + (cents[k + SUBSTEP][1] - cents[k][1]) * uhat[1])
                forward.append(step)
            min_fwd = min(forward) if forward else 0.0
            ok3 = (dnorm >= DIST_MIN and cosang >= math.cos(
                math.radians(ANGLE_MIN_DEG)) and min_fwd > 0.0)
            detail.update(displacement=[round(d[0], 5), round(d[1], 5)],
                          distance=round(dnorm, 5),
                          angle_deg=round(math.degrees(
                              math.acos(max(-1.0, min(1.0, cosang)))), 2),
                          min_forward_step=round(min_fwd, 6))
        else:
            detail['error'] = 'null centroid in probe window'
    else:
        detail['error'] = ('probe velocity is zero'
                           if vnorm == 0 else 'probe window out of range')
    g3 = gate('advected', ok3, **detail)

    # -- gate 4: obstacles respected ------------------------------------------
    obs = cfg['obstacles']
    start = cfg['aim']['frame'] + 8
    worst = 0.0
    n_checked = 0
    for k in range(start, len(f1)):
        m = f1[k].get('mass') or 0.0
        for o, inside in enumerate(f1[k].get('inside') or []):
            n_checked += 1
            frac = inside / m if m > 0 else (1.0 if inside > 0 else 0.0)
            worst = max(worst, frac)
    g4 = gate('obstacles_respected',
              n_checked > 0 and worst <= OBSTACLE_FRAC,
              obstacle_count=len(obs),
              frames_checked=n_checked,
              worst_fraction=round(worst, 6),
              limit=OBSTACLE_FRAC)

    # -- gate 5: dye dissipates as configured ---------------------------------
    # The oracle is the artifact's stationary decay patch: a zero-velocity
    # splat whose mass inside its declared box can only shrink via
    # DENSITY_DISSIPATION (no flow reaches the corner before the window ends).
    dec = cfg.get('decay') or {}
    df = dec.get('frame', pf)
    dtrack = dec.get('trackFrames', track)
    diss = float((cfg.get('config') or {}).get('DENSITY_DISSIPATION', 1.0))
    expected = math.exp(-cfg['dt'] * diss)
    dmass = [fr.get('decayMass') for fr in f1]
    have_d = (all(isinstance(m, (int, float)) for m in dmass)
              and len(dmass) > df + dtrack)
    mono_ok = have_d and all(
        dmass[k + 1] <= MASS_GROW_TOL * dmass[k]
        for k in range(df, df + dtrack))
    decay_meas = ratio = None
    if have_d and dmass[df] and dmass[df] > 0:
        decay_meas = (dmass[df + dtrack] / dmass[df]) ** (1.0 / dtrack)
        ratio = decay_meas / expected
    in_band = ratio is not None and DECAY_LO <= ratio <= DECAY_HI
    diss_ok = (CONFIG_BOUNDS['DENSITY_DISSIPATION'][0] <= diss
               <= CONFIG_BOUNDS['DENSITY_DISSIPATION'][1])
    g5 = gate('dissipation',
              mono_ok and in_band and diss_ok,
              window=[df, df + dtrack],
              configured=diss,
              configured_in_spec_range=diss_ok,
              expected_per_frame=round(expected, 6),
              measured_per_frame=(round(decay_meas, 6)
                                  if decay_meas is not None else None),
              ratio=round(ratio, 4) if ratio is not None else None,
              monotone=mono_ok)

    # -- gate 6: no NaN, no blank frames --------------------------------------
    bad = []
    float_ok = meta.get('floatRead')
    for run_i, frames in ((1, f1), (2, f2)):
        for k, fr in enumerate(frames):
            if (fr.get('mass') or 0) < MIN_MASS or fr.get('nan'):
                bad.append('run%d f%d' % (run_i, k))
            if not float_ok and (fr.get('nonblank') or 0) < MIN_NONBLANK:
                bad.append('run%d f%d nonblank' % (run_i, k))
    g6 = gate('no_nan_no_blank', not bad,
              bad_frames=bad[:12],
              float_readback=meta.get('floatRead'))

    gates = [g1, g2, g3, g4, g5, g6]
    verdict = {
        'demo': 'webgl-fluid',
        'all_gates_passed': all(g['passed'] for g in gates),
        'gates': gates,
        'meta': {
            'renderer': meta.get('renderer'),
            'gl_version': meta.get('glVersion'),
            'dye': [meta.get('dyeWidth'), meta.get('dyeHeight')],
            'sim': [meta.get('simWidth'), meta.get('simHeight')],
            'float_readback': meta.get('floatRead'),
        },
        'timing': {'scene_wall_ms': blob.get('wall_ms')},
    }

    if frames_dir and blob.get('raw_frames'):
        os.makedirs(frames_dir, exist_ok=True)
        w, h = meta.get('dyeWidth'), meta.get('dyeHeight')
        import base64
        saved = []
        for idx, b64 in zip(blob.get('stash_indices') or [],
                            blob['raw_frames']):
            if b64 is None or not (w and h):
                continue
            png = os.path.join(frames_dir, 'frame_%03d.png' % idx)
            write_png(png, w, h, base64.b64decode(b64))
            saved.append(png)
        verdict['frames_saved'] = saved

    out = json.dumps(verdict, indent=2) + '\n'
    if json_out:
        with open(json_out, 'w') as f:
            f.write(out)
    sys.stdout.write(out)
    sys.exit(0 if verdict['all_gates_passed'] else 1)


if __name__ == '__main__':
    main()
