#!/usr/bin/env python3
"""pixel-diff-review judge engine.

Grades one review.py-style artifact against the gates in SPEC.md.  The
judge owns the fixture, the screenshots and the layout geometry; the
artifact only ever sees two PNGs and a grid.  Nothing the artifact reports
is taken as truth: every gate compares against the browser's own layout
geometry, the judge's independent reference diff, the sha256 of the
captured PNGs, or the checksum of judge/ itself.

Usage (grade.sh wraps this):
    python3 -I pdr_judge.py <artifact.py> [--seed N] [--json out.json]

stdlib only; deterministic for a fixed seed and toolchain (wall times live
under `timing` and are the only run-varying bytes in the verdict).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import importlib.util
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPORT_SCHEMA = "pixel-diff-review/report/1"
VERDICT_SCHEMA = "pixel-diff-review/verdict/1"

# Numeric constants (SPEC.md "Gates"; env so a receipt can name them).
VW, VH = (int(v) for v in
          os.environ.get("PDR_VIEWPORT", "1280x720").lower().split("x"))
COLS = int(os.environ.get("PDR_COLS", "40"))
ROWS = int(os.environ.get("PDR_ROWS", "30"))
SEED = int(os.environ.get("PDR_SEED", "20261015"))
ALLOW = os.environ.get("PDR_ALLOW", "card")          # card | none | page
OVERLAP_MIN = float(os.environ.get("PDR_OVERLAP_MIN", "0.90"))
BOX_TOL_PX = float(os.environ.get("PDR_BOX_TOL_PX", "8"))
CONV_TOL_PX = float(os.environ.get("PDR_CONV_TOL_PX", "16"))
OFFSET_TOL_PX = float(os.environ.get("PDR_OFFSET_TOL_PX", "1.5"))
DILATE_BLOCKS = int(os.environ.get("PDR_DILATE_BLOCKS", "1"))

CHROMIUM = os.environ.get("PDR_CHROMIUM", "chromium")
FONT = os.environ.get(
    "PDR_FONT",
    str(Path.home() / ".local/share/pixel-diff-review/DejaVuSans.ttf"))
CACHE = Path(os.environ.get("PDR_CACHE", "/tmp/pdr-cache"))
JUDGE_DIR = Path(os.environ.get(
    "PDR_JUDGE_DIR", str(Path(__file__).resolve().parent)))
DEMO_DIR = JUDGE_DIR.parent
HTTP_BASE_PORT = 8791

CHROMIUM_FLAGS = [
    "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
    "--force-device-scale-factor=1",
    "--window-size=%d,%d" % (VW, VH),
    "--run-all-compositor-stages-before-draw",
    "--virtual-time-budget=4000",
]

# Injected into a copy of each build to read the renderer's own layout
# geometry: the intended card's box, the footer's box and the footer's
# resolved transform.  This is the analytic mask of SPEC.md.
GEOM_SCRIPT = (
    '<script>(function(){function r(e){var b=e.getBoundingClientRect();'
    'return [b.x,b.y,b.width,b.height]}'
    'var c=document.querySelector("[data-pdr-intended]");'
    'var f=document.querySelector(\'[data-region="footer"]\');'
    'var out={card:r(c),footer:r(f),'
    'footer_transform:getComputedStyle(f).transform};'
    'document.documentElement.setAttribute("data-pdr-geom",'
    'JSON.stringify(out))})()</script>')


def log(msg: str) -> None:
    print("judge: %s" % msg, flush=True)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def judge_tree_digest() -> str:
    """sha256 over every file under judge/ (content + name)."""
    h = hashlib.sha256()
    for p in sorted(JUDGE_DIR.rglob("*")):
        if p.is_file() and p.suffix != ".pyc":
            h.update(str(p.relative_to(JUDGE_DIR)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def load_reference_diff():
    spec = importlib.util.spec_from_file_location(
        "pdr_reference_diff", JUDGE_DIR / "reference_diff.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# Capture: fixture -> served builds -> pinned-Chromium screenshots + geometry
# --------------------------------------------------------------------------
def wait_port(port: int, deadline_s: float = 20.0) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < deadline_s:
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError("http server on 127.0.0.1:%d never came up" % port)


def chromium_run(args: list[str, Path], timeout: float = 90.0):
    return subprocess.run([CHROMIUM, *CHROMIUM_FLAGS, *args],
                          capture_output=True, timeout=timeout)


def screenshot(url: str, out: Path, ref) -> None:
    """Capture `url` to `out`; retry on a blank frame (cold-profile race)."""
    for attempt in range(3):
        udd = out.parent / ("udd-%s-%d" % (out.stem, attempt))
        try:
            chromium_run(["--user-data-dir=%s" % udd,
                          "--screenshot=%s" % out, url])
            if not out.is_file():
                raise RuntimeError("chromium wrote no screenshot")
            if not ref.image_is_blank(out):
                return
            log("screenshot blank on attempt %d for %s -- retrying"
                % (attempt + 1, url))
        finally:
            shutil.rmtree(udd, ignore_errors=True)
    raise RuntimeError("blank screenshot for %s after 3 attempts" % url)


def dump_dom(url: str, ref) -> str:
    udd = Path(tempfile.mkdtemp(prefix="pdr-udd-"))
    try:
        proc = chromium_run(["--user-data-dir=%s" % udd, "--dump-dom", url])
        return proc.stdout.decode("utf-8", "replace")
    finally:
        shutil.rmtree(udd, ignore_errors=True)


def parse_geom(dom: str, variant: str) -> dict:
    m = re.search(r'data-pdr-geom="([^"]*)"', dom)
    if not m:
        raise RuntimeError("no data-pdr-geom in %s dump-dom output" % variant)
    return json.loads(html.unescape(m.group(1)))


def build_capture(cdir: Path, ref) -> dict:
    """Generate the fixture, capture screenshots and geometry into `cdir`."""
    fx = cdir / "fixture"
    subprocess.run([sys.executable, "-I",
                    str(DEMO_DIR / "fixture/gen.py"), str(fx),
                    "--seed", str(SEED), "--font", FONT],
                   check=True, capture_output=True)

    variants = ("base", "head", "sneaky")
    geom = {}
    shots = cdir / "shots"
    shots.mkdir(parents=True, exist_ok=True)
    # one warmup launch so the first real capture never races a cold profile
    chromium_run(["--user-data-dir=%s" % (cdir / "udd-warm"),
                  "--screenshot=%s" % (cdir / "warmup.png"), "about:blank"])
    shutil.rmtree(cdir / "udd-warm", ignore_errors=True)

    for i, v in enumerate(variants):
        port = HTTP_BASE_PORT + i
        geo_dir = cdir / ("geo-" + v)
        shutil.copytree(fx / v, geo_dir)
        index = geo_dir / "index.html"
        text = index.read_text(encoding="utf-8")
        if "</body>" not in text:
            raise RuntimeError("fixture %s/index.html has no </body>" % v)
        index.write_text(text.replace("</body>", GEOM_SCRIPT + "</body>"),
                         encoding="utf-8")

        for serve_dir, then in ((fx / v, "shot"), (geo_dir, "dom")):
            srv = subprocess.Popen(
                [sys.executable, "-m", "http.server", str(port),
                 "--bind", "127.0.0.1", "--directory", str(serve_dir)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                wait_port(port)
                url = "http://127.0.0.1:%d/index.html" % port
                if then == "shot":
                    screenshot(url, shots / ("%s.png" % v), ref)
                else:
                    geom[v] = parse_geom(dump_dom(url, ref), v)
            finally:
                srv.terminate()
                srv.wait(timeout=10)
        shutil.rmtree(geo_dir, ignore_errors=True)

    data = {
        "seed": SEED,
        "viewport": [VW, VH],
        "shots": {v: sha256_file(shots / ("%s.png" % v)) for v in variants},
        "geometry": geom,
    }
    (cdir / "capture.json").write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def ensure_capture(ref) -> tuple[Path, dict, bool]:
    cdir = CACHE / ("seed-%d" % SEED)
    marker = cdir / "capture.json"
    if marker.is_file():
        try:
            data = json.loads(marker.read_text())
            if data.get("seed") == SEED and all(
                    (cdir / "shots" / ("%s.png" % v)).is_file()
                    for v in ("base", "head", "sneaky")):
                log("capture cache hit at %s" % cdir)
                return cdir, data, True
        except (ValueError, OSError):
            pass
    if cdir.exists():
        shutil.rmtree(cdir)
    cdir.mkdir(parents=True)
    log("building capture (fixture + screenshots + geometry) at %s" % cdir)
    t0 = time.monotonic()
    data = build_capture(cdir, ref)
    log("capture done in %.1fs" % (time.monotonic() - t0))
    return cdir, data, False


# --------------------------------------------------------------------------
# Artifact runs
# --------------------------------------------------------------------------
REQUIRED_REPORT_KEYS = ("schema", "inputs", "grid", "regions", "changed_blocks")


def run_artifact(artifact: Path, workdir: Path, base: Path, head: Path,
                 tag: str, allow_bbox=None) -> tuple[int, dict | None, str]:
    """Copy the artifact and run it on the two PNGs; never touches judge/."""
    art_copy = workdir / "artifact.py"
    shutil.copyfile(artifact, art_copy)
    out = workdir / ("report-%s.json" % tag)
    cmd = [sys.executable, "-I", str(art_copy),
           "--base", str(base), "--head", str(head),
           "--cols", str(COLS), "--rows", str(ROWS)]
    if allow_bbox is not None:
        cmd += ["--allow-bbox", ",".join(str(int(v)) for v in allow_bbox)]
    cmd += ["--json", str(out)]
    proc = subprocess.run(cmd, capture_output=True, timeout=600, cwd=workdir)
    report = None
    if out.is_file():
        try:
            report = json.loads(out.read_text())
        except ValueError:
            report = None
    return proc.returncode, report, proc.stderr.decode("utf-8", "replace")


def valid_report(report) -> bool:
    if not isinstance(report, dict):
        return False
    for k in REQUIRED_REPORT_KEYS:
        if k not in report:
            return False
    if report.get("schema") != REPORT_SCHEMA:
        return False
    inputs = report.get("inputs")
    if not isinstance(inputs, dict) or set(inputs) != {"base", "head"}:
        return False
    grid = report.get("grid")
    if not isinstance(grid, dict) or not {
            "cols", "rows", "block_w", "block_h"} <= set(grid):
        return False
    return isinstance(report.get("regions"), list) and \
        isinstance(report.get("changed_blocks"), int)


# --------------------------------------------------------------------------
# Geometry helpers (rects are [x, y, w, h] in device px)
# --------------------------------------------------------------------------
def rect_area(r):
    return max(0.0, r[2]) * max(0.0, r[3])


def rect_intersect(a, b):
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[0] + a[2], b[0] + b[2])
    y1 = min(a[1] + a[3], b[1] + b[3])
    return [x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)]


def rect_dilate(r, dx, dy):
    return [r[0] - dx, r[1] - dy, r[2] + 2 * dx, r[3] + 2 * dy]


def block_rect(c, r, bw, bh):
    return [c * bw, r * bh, bw, bh]


def blocks_in_rect(blocks, rect, mode):
    """blocks (set of (c,r)) whose rect intersects (`hit`) or whose centre
    lies inside (`centre`) `rect`."""
    bw = VW // COLS
    bh = VH // ROWS
    out = set()
    for (c, r) in blocks:
        br = block_rect(c, r, bw, bh)
        if mode == "hit":
            if rect_area(rect_intersect(br, rect)) > 0:
                out.add((c, r))
        else:
            cx, cy = br[0] + bw / 2, br[1] + bh / 2
            if (rect[0] <= cx <= rect[0] + rect[2]
                    and rect[1] <= cy <= rect[1] + rect[3]):
                out.add((c, r))
    return out


def transform_ty(matrix: str) -> float:
    """Vertical translation out of a computed transform matrix string."""
    if matrix in ("none", ""):
        return 0.0
    nums = re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", matrix)
    if len(nums) != 6:
        raise RuntimeError("unexpected transform: %r" % matrix)
    return float(nums[5])


# --------------------------------------------------------------------------
# Gates
# --------------------------------------------------------------------------
def grade(artifact: Path, seed: int) -> dict:
    t_start = time.monotonic()
    ref = load_reference_diff()
    digest_before = judge_tree_digest()

    cdir, capture, cached = ensure_capture(ref)
    shots = cdir / "shots"
    geom = capture["geometry"]
    card = geom["base"]["card"]            # [x, y, w, h] device px
    footer_ty = transform_ty(geom["sneaky"]["footer_transform"])

    bw, bh = VW // COLS, VH // ROWS
    allow_rect = None
    if ALLOW == "card":
        allow_rect = card
    elif ALLOW == "page":
        allow_rect = [0, 0, VW, VH]
    elif ALLOW != "none":
        raise RuntimeError("PDR_ALLOW must be card, none or page, got %r"
                           % ALLOW)

    t_cap = time.monotonic()

    work = Path(tempfile.mkdtemp(prefix="pdr-grade-"))
    try:
        runs = {}
        timing_art = {}
        plan = [("head", "head", None), ("sneaky", "sneaky", None)]
        if ALLOW != "none":
            plan += [("head_allow", "head", allow_rect),
                     ("sneaky_allow", "sneaky", allow_rect)]
        for name, head_v, allow in plan:
            t0 = time.monotonic()
            rc, report, err = run_artifact(
                artifact, work, shots / "base.png",
                shots / ("%s.png" % head_v), name, allow_bbox=allow)
            timing_art[name] = round(time.monotonic() - t0, 3)
            runs[name] = {"rc": rc, "report": report, "stderr": err}

        t_ref0 = time.monotonic()
        ref_coarse = ref.diff(shots / "base.png", shots / "head.png", COLS, ROWS)
        ref_sneaky = ref.diff(shots / "base.png", shots / "sneaky.png",
                              COLS, ROWS)
        ref_fine = ref.diff(shots / "base.png", shots / "head.png",
                            COLS * 2, ROWS * 2)
        t_ref = time.monotonic() - t_ref0
    finally:
        shutil.rmtree(work, ignore_errors=True)

    # ---- gate helpers ----------------------------------------------------
    gates = {}
    failed = []

    def gate(name, measured, rule, ok):
        gates[name] = {"measured": measured, "rule": rule, "pass": bool(ok)}
        if not ok:
            failed.append(name)

    # 1 engine_runs: every artifact run exited 0 with a valid report
    ok1 = all(runs[n]["rc"] == 0 and valid_report(runs[n]["report"])
              for n in runs)
    gate("engine_runs",
         {"runs": {n: {"exit": runs[n]["rc"],
                       "valid_schema": valid_report(runs[n]["report"])}
                   for n in sorted(runs)}},
         "exit 0 and a schema-valid JSON report for all four runs", ok1)

    head_rep = runs["head"]["report"] or {}
    sneaky_rep = runs["sneaky"]["report"] or {}
    head_allow = runs["head_allow"]["report"] or {}
    sneaky_allow = runs["sneaky_allow"]["report"] or {}

    # 2 inputs_matched: the report names the PNGs the judge captured
    def inputs_ok(rep, head_variant):
        inp = rep.get("inputs") or {}
        return (inp.get("base") == capture["shots"]["base"]
                and inp.get("head") == capture["shots"][head_variant])
    ok2 = inputs_ok(head_rep, "head") and inputs_ok(sneaky_rep, "sneaky")
    gate("inputs_matched",
         {"report_base": (head_rep.get("inputs") or {}).get("base"),
          "report_head": (head_rep.get("inputs") or {}).get("head"),
          "report_sneaky": (sneaky_rep.get("inputs") or {}).get("head"),
          "captured_base": capture["shots"]["base"],
          "captured_head": capture["shots"]["head"],
          "captured_sneaky": capture["shots"]["sneaky"]},
         "report inputs sha256 == captured PNG sha256 (head and sneaky runs)",
         ok2)

    regions = head_rep.get("regions") or []
    # 3 region_count
    gate("region_count", len(regions), "exactly 1", len(regions) == 1)

    # 4/5 card overlap and spill (only meaningful when a region exists)
    r0 = regions[0]["bbox_px"] if regions else [0, 0, 0, 0]
    inter = rect_intersect(card, r0)
    overlap = rect_area(inter) / rect_area(card) if rect_area(card) else 0.0
    gate("bbox_overlap", round(overlap, 4), ">= %s" % OVERLAP_MIN,
         overlap >= OVERLAP_MIN)

    dilated = rect_dilate(card, DILATE_BLOCKS * bw, DILATE_BLOCKS * bh)
    spill = 1.0 - (rect_area(rect_intersect(r0, dilated)) /
                   (rect_area(r0) or 1))
    gate("no_spill", round(spill, 4), "= 0.0", spill == 0.0)

    # 6/7 recall and false positives against the reference diff
    reported = set()
    for reg in regions:
        for b in reg.get("blocks") or []:
            reported.add((int(b[0]), int(b[1])))
    ref_blocks = set(ref_coarse["changed_blocks"])
    expected = blocks_in_rect(ref_blocks, card, "centre")
    missed = expected - reported if expected else set()
    recall = (len(expected) - len(missed)) / len(expected) \
        if expected else 1.0
    gate("recall", round(recall, 4), "1.0 (all reference blocks inside "
         "the card rect are reported)", recall == 1.0)

    outside = reported - blocks_in_rect(reported, dilated, "hit")
    gate("no_false_positives", len(outside),
         "0 blocks outside the card rect dilated by %d block(s)"
         % DILATE_BLOCKS, len(outside) == 0)

    # 8 area_consistent
    ok8 = True
    for reg in regions:
        blocks = [(int(b[0]), int(b[1])) for b in reg.get("blocks") or []]
        connected = ref.four_connected(blocks)
        ok8 &= (reg.get("area_blocks") == len(blocks) and connected
                and reg.get("area_px") == reg.get("area_blocks") * bw * bh)
    gate("area_consistent", {"regions_checked": len(regions)},
         "area_blocks == len(blocks), blocks 4-connected, "
         "area_px == area_blocks * bw * bh", ok8)

    # 9 reference_agreement: region count and boxes vs the reference diff
    ref_boxes = ref_coarse["boxes_px"]
    rep_boxes = [reg["bbox_px"] for reg in regions]
    ok9 = len(ref_boxes) == len(rep_boxes)
    if ok9:
        for rb, pb in zip(ref_boxes, rep_boxes):
            if (abs(rb[0] - pb[0]) > BOX_TOL_PX
                    or abs(rb[1] - pb[1]) > BOX_TOL_PX
                    or abs(rb[0] + rb[2] - pb[0] - pb[2]) > BOX_TOL_PX
                    or abs(rb[1] + rb[3] - pb[1] - pb[3]) > BOX_TOL_PX):
                ok9 = False
    gate("reference_agreement",
         {"reference_boxes": ref_boxes, "report_boxes": rep_boxes},
         "same region count; every box corner within %g px of the "
         "reference diff" % BOX_TOL_PX, ok9)

    # 10 convergence: reference diff refined 2x agrees with itself
    fine_boxes = ref_fine["boxes_px"]
    ok10 = len(fine_boxes) == len(ref_boxes)
    conv_dev = None
    if ok10 and ref_boxes:
        dev = max(abs(fine_boxes[0][k] - ref_boxes[0][k])
                  for k in (0, 1))
        dev = max(dev,
                  abs((fine_boxes[0][0] + fine_boxes[0][2])
                      - (ref_boxes[0][0] + ref_boxes[0][2])),
                  abs((fine_boxes[0][1] + fine_boxes[0][3])
                      - (ref_boxes[0][1] + ref_boxes[0][3])))
        conv_dev = dev
        ok10 = dev <= CONV_TOL_PX
    gate("convergence",
         {"coarse_boxes": ref_boxes, "fine_boxes": fine_boxes,
          "max_box_deviation_px": conv_dev},
         "same region count at %dx%d and %dx%d; card box within %g px"
         % (COLS, ROWS, COLS * 2, ROWS * 2, CONV_TOL_PX), ok10)

    # 11/12 negative control: the sneaky build must be caught
    sneaky_regions = sneaky_rep.get("regions") or []
    gate("negctl_regions", len(sneaky_regions), "exactly 2",
         len(sneaky_regions) == 2)

    ok12 = False
    measured12 = {"footer_ty_px": footer_ty, "second_region_offset": None,
                  "offset_magnitude_px": None, "direction_error_deg": None}
    if len(sneaky_regions) == 2:
        off = sneaky_regions[1].get("offset_px") or [0, 0]
        mag = math.hypot(off[0], off[1])
        want = (0.0, -1.0 if footer_ty < 0 else 1.0)
        dot = (off[0] * want[0] + off[1] * want[1])
        cos = dot / mag if mag else 0.0
        ang = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
        measured12.update(second_region_offset=off,
                          offset_magnitude_px=round(mag, 3),
                          direction_error_deg=round(ang, 2))
        ok12 = (abs(mag - abs(footer_ty)) <= OFFSET_TOL_PX and ang <= 45.0)
    gate("negctl_offset", measured12,
         "|mag - %.1f| <= %g px and direction within 45 deg of (0, %g)"
         % (abs(footer_ty), OFFSET_TOL_PX, -1 if footer_ty < 0 else 1), ok12)

    # 13 verdict_wiring: the artifact's own allow-bbox verdict
    if ALLOW == "none":
        gate("verdict_wiring", "not_run (PDR_ALLOW=none)",
             "not run under PDR_ALLOW=none", True)
    else:
        ok13 = (head_allow.get("verdict") == "pass"
                and sneaky_allow.get("verdict") == "fail")
        gate("verdict_wiring",
             {"head_verdict": head_allow.get("verdict"),
              "sneaky_verdict": sneaky_allow.get("verdict"),
              "allow_mode": ALLOW},
             "verdict == pass on head and fail on sneaky under --allow-bbox "
             "(PDR_ALLOW=%s)" % ALLOW, ok13)

    # 14 judge_intact
    digest_after = judge_tree_digest()
    gate("judge_intact", {"before": digest_before[:16],
                          "after": digest_after[:16]},
         "sha256 of judge/ identical before and after",
         digest_before == digest_after)

    t_end = time.monotonic()
    verdict = {
        "schema": VERDICT_SCHEMA,
        "demo": "pixel-diff-review",
        "artifact": str(artifact),
        "seed": seed,
        "constants": {
            "viewport": [VW, VH], "cols": COLS, "rows": ROWS,
            "allow": ALLOW, "overlap_min": OVERLAP_MIN,
            "box_tol_px": BOX_TOL_PX, "conv_tol_px": CONV_TOL_PX,
            "offset_tol_px": OFFSET_TOL_PX, "dilate_blocks": DILATE_BLOCKS,
        },
        "analytic": {
            "card_rect_px": card,
            "footer_rect_px": geom["sneaky"]["footer"],
            "footer_transform": geom["sneaky"]["footer_transform"],
            "footer_ty_px": footer_ty,
            "shot_sha256": capture["shots"],
        },
        "gates": gates,
        "timing": {
            "capture_s": None if cached else round(t_cap - t_start, 3),
            "artifact_s": timing_art,
            "reference_s": round(t_ref, 3),
            "total_s": round(t_end - t_start, 3),
        },
        "passed": not failed,
        "failed_gate": failed[0] if failed else None,
    }
    return verdict


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--json", dest="json_out", default=None)
    args = ap.parse_args(argv[1:])

    artifact = Path(args.artifact).resolve()
    if not artifact.is_file():
        print("judge: no artifact at %s" % artifact, file=sys.stderr)
        return 2

    verdict = grade(artifact, args.seed)
    text = json.dumps(verdict, indent=2, sort_keys=True)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    print(text)
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
