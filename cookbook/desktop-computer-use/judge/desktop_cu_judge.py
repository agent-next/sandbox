#!/usr/bin/env python3
"""Desktop computer-use judge engine.

Grades one artifact -- a Python file `actions.py` that drives LibreOffice
Calc on a real X display -- against the gates in SPEC.md.

  grade.sh <artifact.py> [--seed N] [--json out.json]

The judge opens the fixture CSV on a private X display itself, takes the
"before" screenshot, runs the artifact with DISPLAY set to that display,
takes the "after" screenshot, then grades the workbook at
/tmp/desktop-cu/report.xlsx read back by openpyxl (a different library than
the one that produced it) plus the screenshots.

Prints exactly one JSON verdict object; exits 0 only if every gate passes.
Exit 2 on usage errors.  Stdlib + openpyxl only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import zipfile
import zlib
from pathlib import Path

# --- judge constants (SPEC.md) --------------------------------------------
ROW_TOL = float(os.environ.get("ROW_TOL", "0.005"))
DIFF_PIXELS_MIN = int(os.environ.get("DIFF_PIXELS_MIN", "2000"))
SHOT_W = int(os.environ.get("SHOT_W", "1024"))
SHOT_H = int(os.environ.get("SHOT_H", "768"))
SOFFICE_READY_S = float(os.environ.get("SOFFICE_READY_S", "30"))
AGENT_S = float(os.environ.get("AGENT_S", "240"))

CU_DIR = Path("/tmp/desktop-cu")
REPORT = CU_DIR / "report.xlsx"

# openpyxl is installed by setup.sh into judge/.wheels (sha256-pinned);
# the engine runs with -I, so wire the path in explicitly before importing.
sys.path.insert(0, str(Path(__file__).resolve().parent / ".wheels"))


def log(msg: str) -> None:
    print(f"judge: {msg}", flush=True)


def sh(argv, **kw):
    return subprocess.run(argv, capture_output=True, text=True, **kw)


# --- independent oracles ---------------------------------------------------

def read_fixture(path: Path):
    """Judge's own arithmetic from the fixture; never trusts the artifact."""
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    headers = ["item", "qty", "price"]
    if list(rows[0].keys()) != headers:
        raise ValueError(f"fixture headers {list(rows[0].keys())} != {headers}")
    n = len(rows)
    expected = []
    for r in rows:
        qty = float(r["qty"])
        price = float(r["price"])
        expected.append((r["item"], qty, price, round(qty * price, 2)))
    return n, expected


def workbook_truth(fixture_path: Path):
    """What the workbook must hold once openpyxl reads it back."""
    n, expected = read_fixture(fixture_path)
    qty_sum = sum(r[1] for r in expected)
    total_sum = sum(r[3] for r in expected)
    return n, expected, qty_sum, total_sum


# --- screenshot helpers ----------------------------------------------------

def shot(display: str, out_path: Path) -> None:
    """Capture the whole display with ImageMagick import (judge-side)."""
    r = sh(["import", "-window", "root", str(out_path)], timeout=60,
           env={**os.environ, "DISPLAY": display})
    if r.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"screenshot failed: {r.stderr.strip()[:300]}")


def decode_png_rgb(path: Path):
    """Decode a PNG to (width, height, bytes) using zlib only (stdlib).

    Handles the 8-bit colour types ImageMagick writes (RGB/RGBA/grey),
    with filters 0-4.  Raises on anything else -- the judge fails closed
    on a screenshot it cannot parse.
    """
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos = 8
    width = height = None
    bit_depth = color_type = None
    idat = bytearray()
    while pos < len(data):
        (length,) = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if ctype == b"IHDR":
            width = int.from_bytes(chunk[0:4], "big")
            height = int.from_bytes(chunk[4:8], "big")
            bit_depth = chunk[8]
            color_type = chunk[9]
        elif ctype == b"IDAT":
            idat += chunk
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if width is None:
        raise ValueError("PNG has no IHDR")
    if bit_depth != 8:
        raise ValueError(f"PNG bit depth {bit_depth} != 8")
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"PNG colour type {type} unsupported")
    raw = zlib.decompress(bytes(idat))
    stride = width * channels
    out = bytearray(height * stride)
    prev = bytearray(stride)
    p = 0
    for y in range(height):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if f == 0:
            pass
        elif f == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise ValueError(f"PNG filter {f} unsupported")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return width, height, channels, out


def count_diff_pixels(png_a: Path, png_b: Path) -> tuple[int, int, int, str]:
    """Return (w, h, differing_pixels, note).  w/h = (w,h) of shot A."""
    wa, ha, ca, ba = decode_png_rgb(png_a)
    wb, hb, cb, bb = decode_png_rgb(png_b)
    if (wa, ha) != (wb, hb):
        return wa, ha, -1, f"screenshot size changed {wa}x{ha} -> {wb}x{hb}"
    diff = 0
    n = len(ba) // ca
    for i in range(n):
        a3 = ba[i * ca:i * ca + 3]
        b3 = bb[i * cb:i * cb + 3]
        if a3 != b3:
            diff += 1
    return wa, ha, diff, "ok"


def is_flat(png: Path) -> bool:
    """True if every pixel has the same RGB (a blank/desktop-only shot)."""
    w, h, c, buf = decode_png_rgb(png)
    first = bytes(buf[0:3])
    for i in range(0, len(buf), c):
        if bytes(buf[i:i + 3]) != first:
            return False
    return True


# --- verdict ---------------------------------------------------------------

def verdict(artifact: str, seed: int, passed: bool, gates: dict,
            failed_gate: str | None = None, reason: str | None = None,
            timing: dict | None = None) -> dict:
    v = {
        "artifact": artifact,
        "seed": seed,
        "passed": passed,
        "gates": gates,
    }
    if failed_gate is not None:
        v["failed_gate"] = failed_gate
    if reason is not None:
        v["reason"] = reason
    if timing:
        v["timing"] = timing
    return v


def emit(v: dict, json_path: str | None) -> None:
    text = json.dumps(v, indent=2, sort_keys=False) + "\n"
    print(text, end="", flush=True)
    if json_path:
        Path(json_path).write_text(text)


def gate(name: str, ok: bool, detail: dict | None = None) -> dict:
    g = {"passed": bool(ok)}
    if detail:
        g.update(detail)
    return g


# --- the desktop session ---------------------------------------------------

class Desktop:
    """A private X display + fluxbox + the fixture CSV opened in Calc."""

    # CSV import without the Text Import dialog (comma, quote ", UTF-8,
    # first line 1, quoted fields as text, detect special numbers).
    CSV_INFILTER = ("Text - txt - csv (StarCalc)"
                    ":44,34,76,1,,0,false,true,true")

    # Disable the first-run Tip-of-the-Day dialog: a modal on top of Calc
    # would eat the artifact's keystrokes.  Seeds a throwaway profile.
    PROFILE_XCU = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry"'
        ' xmlns:xs="http://www.w3.org/2001/XMLSchema">\n'
        ' <item oor:path="/org.openoffice.Office.Common/Misc">'
        '<prop oor:name="FirstRun" oor:op="fuse"><value>false</value>'
        '</prop></item>\n'
        ' <item oor:path="/org.openoffice.Office.Common/Misc">'
        '<prop oor:name="ShowTipOfTheDay" oor:op="fuse"><value>false'
        '</value></prop></item>\n'
        '</oor:items>\n'
    )

    def __init__(self, fixture: Path, seed: int):
        self.fixture = fixture
        self.seed = seed
        self.display = None
        self.xvfb = None
        self.wm = None
        self.soffice = None
        self.shots_dir = None

    def __enter__(self):
        # fresh display number
        base = 90 + (self.seed % 50) + int(time.time() * 1000) % 40
        for attempt in range(20):
            self.display = f":{base + attempt}"
            self.xvfb = subprocess.Popen(
                ["Xvfb", self.display, "-screen", "0",
                 f"{SHOT_W}x{SHOT_H}x24", "-nolisten", "tcp"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            r = sh(["xdpyinfo"], timeout=10, env={**os.environ, "DISPLAY": self.display})
            if r.returncode == 0:
                break
            self.xvfb.terminate()
            self.xvfb = None
        else:
            raise RuntimeError("could not start a free Xvfb display")

        self.shots_dir = Path("/tmp/desktop-cu-shots")
        if self.shots_dir.exists():
            shutil.rmtree(self.shots_dir)
        self.shots_dir.mkdir(parents=True)

        # window manager (real frames, focus, activation)
        self.wm = subprocess.Popen(
            ["fluxbox", "-display", self.display],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1.0)

        # the judge opens the CSV itself, so the "before" state is the same
        # for every artifact.  A throwaway profile keeps every run a
        # first-run-free, dialog-free start.
        profile = CU_DIR / "lo-profile"
        (profile / "user").mkdir(parents=True, exist_ok=True)
        (profile / "user" / "registrymodifications.xcu").write_text(
            self.PROFILE_XCU)
        env = dict(os.environ)
        env["DISPLAY"] = self.display
        self.soffice = subprocess.Popen(
            ["soffice", "--calc", "--norestore", "--nologo",
             f"-env:UserInstallation=file://{profile}",
             f"--infilter={self.CSV_INFILTER}",
             str(self.fixture)],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            start_new_session=True)
        # wait for the Calc window, reporting what the desktop was doing
        # instead of only the timeout (a silent 30 s wait tells no one why).
        # The VCL's class is "libreoffice" (checked against Debian's
        # libreoffice-calc 7.4 on Xvfb): the frame "input.csv - LibreOffice
        # Calc" is class libreoffice/libreoffice-calc, and only the frame is
        # visible -- VCL ImplGetDefaultWindow (class "libreoffice") is a
        # 1024x768 override-redirect sibling, so search --onlyvisible picks
        # the document window.
        deadline = time.monotonic() + SOFFICE_READY_S
        last_windows = None
        while time.monotonic() < deadline:
            r = sh(["xdotool", "search", "--onlyvisible", "--class",
                    "libreoffice"], timeout=10,
                  env={**os.environ, "DISPLAY": self.display})
            if r.returncode == 0 and r.stdout.strip():
                time.sleep(1.0)   # let it settle/repaint
                return self
            if self.soffice.poll() is not None:
                raise RuntimeError("soffice exited before showing its window")
            wins = sh(["xdotool", "search", "--name", "."], timeout=10,
                      env={**os.environ, "DISPLAY": self.display})
            names = sorted(set(wins.stdout.split()))[:6]
            if names != last_windows:
                log(f"no soffice window yet ({SOFFICE_READY_S:.0f}s budget); "
                    f"windows on :{self.display.split(':')[-1]}: {names or 'none'}")
                last_windows = names
            time.sleep(0.5)
        err_tail = ""
        try:
            _, err = self.soffice.communicate(timeout=2)
            err_tail = (err or "").decode(errors="replace").strip()[-300:]
        except Exception:
            pass
        self.__exit__()
        raise RuntimeError(f"Calc window did not appear within "
                           f"{SOFFICE_READY_S}s on display {self.display}; "
                           f"soffice stderr tail: {err_tail or 'captured separately'}")

    def before_shot(self) -> Path:
        p = self.shots_dir / "before.png"
        shot(self.display, p)
        return p

    def __exit__(self, *exc):
        # soffice runs in its own session (start_new_session): kill the
        # whole group or the wrapper's child (oosplash/soffice.bin) leaks
        # past the grade holding the profile lock.
        if self.soffice is not None:
            try:
                os.killpg(os.getpgid(self.soffice.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                self.soffice.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.soffice.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                try:
                    self.soffice.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
        if self.soffice is not None:
            try:
                self.soffice.communicate(timeout=1)
            except Exception:
                pass
        for proc in (self.wm, self.xvfb):
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self.soffice = self.wm = self.xvfb = None
        return False


# --- the gates ---------------------------------------------------------------

def grade(artifact: Path, seed: int, fixture_text: str) -> dict:
    timing: dict[str, float] = {}
    t_all = time.monotonic()

    # every grade starts from nothing: a stale report.xlsx from a previous
    # grade would let a no-save mutant pass, and a stale lock file would
    # pop a "locked for editing" dialog over Calc.
    if CU_DIR.exists():
        shutil.rmtree(CU_DIR)
    CU_DIR.mkdir(parents=True)
    fixture = CU_DIR / "input.csv"
    fixture.write_text(fixture_text)

    n, expected, qty_sum, total_sum = workbook_truth(fixture)

    gates: dict[str, dict] = {}

    before_path = after_path = None
    agent_rc = None
    agent_stderr = ""
    ran_ok = None

    with Desktop(fixture, seed) as desk:
        t0 = time.monotonic()
        before_path = desk.before_shot()
        timing["before_shot_s"] = round(time.monotonic() - t0, 2)

        # gate 2: before screenshot
        try:
            w, h, c, _ = decode_png_rgb(before_path)
            flat = is_flat(before_path)
            g2 = w >= 100 and h >= 100 and not flat
            gates["screenshot_before"] = gate(
                "screenshot_before", g2,
                {"width": w, "height": h, "flat": flat})
        except Exception as exc:
            gates["screenshot_before"] = gate(
                "screenshot_before", False, {"error": str(exc)})

        # run the agent on the private display
        env = dict(os.environ)
        env["DISPLAY"] = desk.display
        env["PYTHONUNBUFFERED"] = "1"
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-I", str(artifact)],
                cwd=str(artifact.parent), env=env,
                capture_output=True, text=True, timeout=AGENT_S)
            agent_rc = proc.returncode
            agent_stderr = proc.stderr
        except subprocess.TimeoutExpired:
            agent_rc = None
            agent_stderr = f"judge: artifact exceeded AGENT_S={AGENT_S}s"
        timing["agent_run_s"] = round(time.monotonic() - t0, 2)

        # gate 1: artifact ran cleanly
        tb = "Traceback" in agent_stderr
        ran_ok = (agent_rc == 0 and not tb)
        gates["artifact_ran"] = gate(
            "artifact_ran", ran_ok,
            {"exit": agent_rc, "traceback": tb,
             "stderr_tail": agent_stderr.strip()[-200:]})

        t0 = time.monotonic()
        try:
            after_path = desk.shots_dir / "after.png"
            shot(desk.display, after_path)
            timing["after_shot_s"] = round(time.monotonic() - t0, 2)

            # gate 3: after screenshot.  The raw pixel count varies with
            # the capture instant (caret, repaint), so it is recorded in
            # `timing`, not in the gate: same-seed verdicts must be
            # identical modulo `timing` (DEMO-STANDARD.md).
            w2, h2, c2, _ = decode_png_rgb(after_path)
            flat2 = is_flat(after_path)
            w1, h1, diff, note = count_diff_pixels(before_path, after_path)
            timing["diff_pixels"] = diff
            changed = diff >= DIFF_PIXELS_MIN
            g3 = (w2 >= 100 and h2 >= 100 and not flat2 and changed)
            gates["screenshot_after"] = gate(
                "screenshot_after", g3,
                {"width": w2, "height": h2, "flat": flat2,
                 "diff_pixels_min": DIFF_PIXELS_MIN,
                 "diff_note": note})
        except Exception as exc:
            timing["after_shot_s"] = round(time.monotonic() - t0, 2)
            gates["screenshot_after"] = gate(
                "screenshot_after", False, {"error": str(exc)})

    # gate 4: the report exists and is real OOXML.  The byte size carries
    # LibreOffice's save timestamp, so it lives in `timing` too.
    is_zip = False
    zip_note = ""
    if not (REPORT.exists() and REPORT.is_file()):
        gates["report_exists"] = gate(
            "report_exists", False,
            {"error": f"{REPORT} missing", "path": str(REPORT)})
    else:
        try:
            is_zip = zipfile.is_zipfile(REPORT)
            if is_zip:
                with zipfile.ZipFile(REPORT) as zf:
                    names = zf.namelist()
                    if "xl/workbook.xml" not in names:
                        is_zip = False
                        zip_note = "no xl/workbook.xml"
            else:
                zip_note = "not a ZIP container"
        except Exception as exc:
            is_zip = False
            zip_note = str(exc)
        timing["report_size_bytes"] = REPORT.stat().st_size
        gates["report_exists"] = gate(
            "report_exists", is_zip,
            {"path": str(REPORT), "zip": is_zip, "note": zip_note})

    # workbook gates, read back with openpyxl (different library than the
    # one that produced the file)
    wb_ok = False
    if is_zip:
        try:
            import openpyxl
            wb = openpyxl.load_workbook(REPORT, data_only=True)
            ws = wb.active
            wb_ok = True
        except Exception as exc:
            gates.setdefault("report_exists", gate(
                "report_exists", False,
                {"path": str(REPORT), "error": f"openpyxl: {exc}"}))

    if wb_ok:
        hdr = [ws.cell(row=1, column=c).value for c in range(1, 5)]
        gates["data_column_present"] = gate(
            "data_column_present",
            hdr == ["item", "qty", "price", "total"],
            {"header": hdr})

        # computed column D2..D{n} == round(B*C, 2)
        bad_cells = []
        for i, (_item, qty, price, want) in enumerate(expected):
            row = 2 + i
            got = ws.cell(row=row, column=4).value
            b = ws.cell(row=row, column=2).value
            c = ws.cell(row=row, column=3).value
            try:
                got_f = float(got)
                if abs(got_f - want) > ROW_TOL or b is None or c is None:
                    bad_cells.append({"cell": f"D{row}", "got": got,
                                      "want": want})
            except (TypeError, ValueError):
                bad_cells.append({"cell": f"D{row}", "got": got,
                                  "want": want})
        gates["computed_column_values"] = gate(
            "computed_column_values", not bad_cells,
            {"rows": n, "bad_cells": bad_cells, "row_tol": ROW_TOL})

        tr = n + 2   # total row
        a_t = ws.cell(row=tr, column=1).value
        b_t = ws.cell(row=tr, column=2).value
        c_t = ws.cell(row=tr, column=3).value
        d_t = ws.cell(row=tr, column=4).value

        gates["total_row_label"] = gate(
            "total_row_label",
            isinstance(a_t, str) and a_t.strip().lower() == "total",
            {"A": a_t})

        def num(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        b_ok = num(b_t) is not None and abs(num(b_t) - qty_sum) <= ROW_TOL
        gates["total_row_qty"] = gate(
            "total_row_qty", bool(b_ok),
            {"B": b_t, "want": qty_sum, "row_tol": ROW_TOL})

        d_ok = num(d_t) is not None and abs(num(d_t) - total_sum) <= ROW_TOL
        gates["total_row_total"] = gate(
            "total_row_total", bool(d_ok),
            {"D": d_t, "want": total_sum, "row_tol": ROW_TOL})

        gates["total_row_col_c"] = gate(
            "total_row_col_c", c_t is None or (isinstance(c_t, str)
                                               and c_t.strip() == ""),
            {"C": c_t})

        # no data row beyond the total row
        extras = []
        for row in range(tr + 1, ws.max_row + 5):
            vals = [ws.cell(row=row, column=c).value for c in range(1, 5)]
            if any(v is not None and str(v).strip() != "" for v in vals):
                extras.append({"row": row, "values": vals})
        gates["no_extra_rows"] = gate("no_extra_rows", not extras,
                                      {"extra": extras[:5]})

    timing["total_s"] = round(time.monotonic() - t_all, 2)

    order = ["artifact_ran", "screenshot_before", "screenshot_after",
             "report_exists", "data_column_present",
             "computed_column_values", "total_row_label", "total_row_qty",
             "total_row_total", "total_row_col_c", "no_extra_rows"]
    for name in order:
        if name in gates and not gates[name]["passed"]:
            return verdict(str(artifact), seed, False, gates,
                           failed_gate=name,
                           reason=f"gate {name} failed", timing=timing)

    return verdict(str(artifact), seed, True, gates, timing=timing)


# --- entry -------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args()

    artifact = Path(args.artifact)
    if not artifact.is_file():
        print(f"judge: artifact {artifact} not found", file=sys.stderr)
        return 2

    # fixtures.py holds the CSV as plain text; grade() materialises it
    # into a freshly wiped /tmp/desktop-cu.
    csv_text = (Path(__file__).resolve().parent / "fixtures.py").read_text()

    try:
        v = grade(artifact, args.seed, csv_text)
    except Exception as exc:
        v = verdict(str(artifact), args.seed, False, {},
                    failed_gate="judge", reason=f"judge error: {exc}")

    # judge_intact is graded by grade.sh around this process; the judge
    # records its own checksum here so the verdict JSON carries it too.
    jdir = Path(__file__).resolve().parent
    jsum = hashlib.sha256()
    for p in sorted(jdir.rglob("*")):
        if (p.is_file() and "__pycache__" not in p.parts
                and ".wheels" not in p.parts):
            jsum.update(p.read_bytes())
    v["gates"]["judge_intact"] = gate(
        "judge_intact", True,
        {"judge_sha256": jsum.hexdigest()[:16] + "…",
         "note": "grade.sh verifies this before/after each run"})

    emit(v, args.json_out)
    return 0 if v["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
