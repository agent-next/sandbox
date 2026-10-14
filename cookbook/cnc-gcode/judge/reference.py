"""Cross-check the emitted G-code against LinuxCNC's rs274 interpreter.

The judge's own heightmap simulator (gcode_sim.py) is the primary oracle; this
module adds an *independent, mature open-source* second opinion: LinuxCNC's
standalone RS274/NGC interpreter (`rs274`, Debian bookworm
linuxcnc-uspace, GPLv2+, https://github.com/LinuxCNC/linuxcnc).

Setup extracts three pinned, sha256-checked Debian .debs rootless into
$HOME/.cnc-gcode/rs274; here we only run `usr/bin/rs274 -g part.nc canon.txt`
and parse the canonical move list it prints.

Reference semantics used by gate `reference`:
  * EXIT = program accepted (parsed and executed to PROGRAM_END)
  * nonzero exit => the reference rejected the program (message on stderr)
  * the canonical `USE_LENGTH_UNITS` for this program must be MM (G21): a G20
    (inch) program is "rejected" by the reference for this millimetre job --
    rs274 parses it fine, but it interprets every coordinate/feed in inches,
    which is exactly the semantic error the `units` gate guards.

We compare the reference's canonical geometry to the judge simulator's own
move statistics within a stated tolerance, so the two oracles must agree.

Reference quirks handled here (documented, deterministic):
  * rs274 requires a program-end word (M2/M30). The job spec makes M2/M30
    optional, so we append `M2` on our own line before invoking rs274 -- the
    only accepted extra token; appended verbatim, byte-identical every run.
  * `-g` selects batch mode; stdin is /dev/null so no interactive menu.
  * A fixed empty tool table (one T1 entry, D6) is written so rs274 never
    prompts; the tool geometry is not used for the move list we compare.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile

RS274_ROOT = os.path.expanduser("~/.cnc-gcode/rs274")
RS274_BIN = os.path.join(RS274_ROOT, "root/usr/bin/rs274")

# Canonical-call lines look like:
#    14 N..... STRAIGHT_TRAVERSE(18.0000, 15.0000, 0.0000, ...)
_CANON_RE = re.compile(r"^\s*\d+\s+N\.+\s+([A-Z_0-9]+)\(([^)]*)\)")

# Positional tolerance when comparing reference mm coordinates to the judge.
GEOM_TOL_MM = 1e-3


def _ld_library_path():
    r = os.path.join(RS274_ROOT, "root")
    return os.pathsep.join([
        os.path.join(r, "usr/lib/x86_64-linux-gnu"),
        os.path.join(r, "usr/lib"),
        os.path.join(r, "usr/lib/linuxcnc"),
    ])


def available():
    return os.path.isfile(RS274_BIN) and os.access(RS274_BIN, os.X_OK)


def _tool_table(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("T1 P6.0 D6.0 X0 Y0 Z0 ; 6mm flat end mill (reference)\n")


def run(program_text, timeout_s=60):
    """Interpret `program_text` with LinuxCNC rs274.

    Returns a dict:
      {
        "ok": bool,               # exit 0 AND produced a canonical listing
        "exit": int,
        "stderr_tail": str,
        "units_mm": bool,         # the program's own length-units call was mm
        "feeds": int, "rapids": int, "arcs": int,
        "z_max": float, "z_min": float,
        "bbox": [xmin, ymin, xmax, ymax],
        "n_canon": int,
      }
    """
    # Append a program-end word so rs274 terminates in batch mode.  The
    # program is run verbatim apart from this one trailing line.
    escaped = program_text.rstrip("\n") + "\nM2\n"

    with tempfile.TemporaryDirectory() as td:
        nc = os.path.join(td, "part.nc")
        canon = os.path.join(td, "canon.txt")
        tbl = os.path.join(td, "tool.tbl")
        with open(nc, "w", encoding="utf-8") as fh:
            fh.write(escaped)
        _tool_table(tbl)
        env = dict(os.environ)
        env["LD_LIBRARY_PATH"] = _ld_library_path()
        with open(os.devnull, "rb") as devnull:
            proc = subprocess.run(
                [RS274_BIN, "-g", "-t", tbl, nc, canon],
                stdin=devnull, capture_output=True, text=True,
                timeout=timeout_s, env=env)
        try:
            with open(canon, "r", encoding="utf-8") as fh:
                canon_text = fh.read()
        except OSError:
            canon_text = ""

    return _interpret(proc.returncode, proc.stderr, canon_text)


def _interpret(rc, stderr, canon_text):
    out = {
        "ok": False, "exit": rc,
        "stderr_tail": (stderr or "").strip()[-300:],
        "units_mm": None,
        "feeds": 0, "rapids": 0, "arcs": 0,
        "z_max": None, "z_min": None,
        "bbox": None, "n_canon": 0,
    }
    if not canon_text:
        return out

    feeds = rapids = arcs = 0
    xs, ys, zs = [], [], []
    prog_units = None  # first USE_LENGTH_UNITS after the interpreter default
    n_calls = 0
    use_units_seen = 0
    for line in canon_text.splitlines():
        m = _CANON_RE.match(line)
        if not m:
            continue
        n_calls += 1
        name, arglist = m.group(1), m.group(2)
        if name == "USE_LENGTH_UNITS":
            use_units_seen += 1
            # First call is rs274's default initialisation (mm); the program's
            # own G20/G21 shows up as the next USE_LENGTH_UNITS.
            if use_units_seen >= 2 and prog_units is None:
                prog_units = arglist.strip()
            continue
        # Pull all floats from the argument list.
        try:
            args = [float(a) for a in arglist.split(",")]
        except ValueError:
            continue
        if name == "STRAIGHT_FEED":
            feeds += 1
            x, y, z = args[0], args[1], args[2]
            xs.append(x); ys.append(y); zs.append(z)
        elif name == "STRAIGHT_TRAVERSE":
            rapids += 1
            x, y, z = args[0], args[1], args[2]
            xs.append(x); ys.append(y); zs.append(z)
        elif name == "ARC_FEED":
            arcs += 1
            # ARC_FEED(x, y, center_x, center_y, turn, z, ...)
            x, y = args[0], args[1]
            cx, cy = args[2], args[3]
            z = args[5]
            xs.extend([x, cx]); ys.extend([y, cy]); zs.append(z)

    out["n_canon"] = n_calls
    if prog_units is not None:
        out["units_mm"] = ("MM" in prog_units)
    if xs:
        out["bbox"] = [min(xs), min(ys), max(xs), max(ys)]
    if zs:
        out["z_max"] = max(zs)
        out["z_min"] = min(zs)
    out["feeds"] = feeds
    out["rapids"] = rapids
    out["arcs"] = arcs
    out["ok"] = (rc == 0 and n_calls > 0)
    return out


def sim_stats(moves):
    """Move statistics from the judge's own parsed moves, for comparison.

    Counts feeds/rapids/arcs and computes the naive endpoint+arc-center bounding
    box (same convention as the reference extractor above: arc bbox includes the
    center point, so both sides use the same conservative bound)."""
    feeds = rapids = arcs = 0
    xs, ys, zs = [], [], []
    for mv in moves:
        sx, sy, sz = mv["start"]
        ex, ey, ez = mv["end"]
        if mv["kind"] == "feed" and mv["motion"] == "line":
            feeds += 1
        elif mv["kind"] == "rapid":
            rapids += 1
        if mv["motion"] == "arc":
            arcs += 1
            cx, cy = mv["center"]
            xs.extend([sx, ex, cx]); ys.extend([sy, ey, cy])
        else:
            xs.extend([sx, ex]); ys.extend([sy, ey])
        zs.extend([sz, ez])
    return {
        "feeds": feeds, "rapids": rapids, "arcs": arcs,
        "z_max": max(zs) if zs else None, "z_min": min(zs) if zs else None,
        "bbox": [min(xs), min(ys), max(xs), max(ys)] if xs else None,
    }
