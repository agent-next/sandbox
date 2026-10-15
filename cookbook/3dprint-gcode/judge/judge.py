#!/usr/bin/env python3
"""Grader for the 3dprint-gcode demo (OrcaSlicer + Klipper + own interpreter).

Usage: judge.py <artifact-dir> [--seed N] [--json out.json]

The artifact directory holds profile.ini + part.gcode.  Gates (see SPEC.md):

  slice_clean            OrcaSlicer re-slices bracket.stl with the profile
  artifact_matches       re-sliced G-code == artifact part.gcode (normalised)
  moves_inside_bed       every extruding move inside 250x210, z >= 0
  moves_near_part        extruding moves within brim_max of the STL footprint
  layer_z_sequence       layer Z monotonic; first/steady layer heights in spec
  volume_matches_model   deposited volume vs analytic STL raster model band
  cube_crosscheck        same measurement on judge-sliced cube.stl (judge QA)
  pla_temperatures       nozzle/bed set points in the PLA window, in order
  time_estimate          interpreter time vs slicer estimate, +-25%, <= spec
  klipper_batch          klippy exit 0 and no ERROR/shutdown lines
  profile_contract       wall_loops/infill/nozzle/filament from profile.ini
  judge_intact           sha256 of judge/ unchanged

Prints exactly one verdict JSON; exit 0 only if every gate passes.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import interp  # noqa: E402  (judge's own G-code interpreter, stdlib only)

TOOLS = os.path.expanduser("~/tools")
ORCA = os.path.join(TOOLS, "orca", "bin", "orca-slicer")
ORCA_PROFILES = os.path.join(TOOLS, "orca", "resources", "profiles", "BBL")
KLIPPER_DIR = os.path.join(TOOLS, "klipper")
KLIPPY = os.path.join(KLIPPER_DIR, "klippy", "klippy.py")
KLIPPER_DICT = os.path.join(KLIPPER_DIR, "out", "klipper.dict")

# System presets the judge always loads (machine, filament, process).
MACHINE_PRESET = os.path.join(ORCA_PROFILES, "machine", "Bambu Lab A1 0.4 nozzle.json")
FILAMENT_PRESET = os.path.join(ORCA_PROFILES, "filament", "Bambu PLA Basic @BBL A1.json")

# Slicing is deterministic; cache by (settings content, stl content) so the
# selftest's repeat runs and mutants that share a profile slice only once.
SLICE_CACHE = os.path.join(tempfile.gettempdir(), "3dprint-gcode-slice-cache")

GATE_ORDER = ["slice_clean", "artifact_matches", "moves_inside_bed",
              "moves_near_part", "layer_z_sequence", "volume_matches_model",
              "cube_crosscheck", "pla_temperatures", "time_estimate",
              "klipper_batch", "profile_contract", "judge_intact"]


# ------------------------------------------------------------- helpers ----
def load_spec():
    with open(os.path.join(DEMO, "task", "spec.json")) as fh:
        return json.load(fh)


def load_profile(path):
    """Parse the artifact's flat profile.ini into a dict (later keys win)."""
    prof = {}
    if not os.path.exists(path):
        return prof
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.split(";")[0].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        prof[k.strip()] = v.strip()
    return prof


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def gcode_content_hash(path):
    """Hash of the machine-readable G-code: comments stripped, whitespace
    normalised, so cosmetic header differences don't fail the match gate."""
    h = hashlib.sha256()
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            s = interp.strip_comment(line)
            if s:
                h.update((" ".join(s.split()) + "\n").encode())
    return h.hexdigest()


def judge_dir_hash():
    """sha256 over every file under judge/ (tamper check)."""
    h = hashlib.sha256()
    for root, _, files in sorted(os.walk(HERE)):
        for f in sorted(files):
            p = os.path.join(root, f)
            if os.path.samefile(root, HERE) and f == "VERSIONS.txt":
                continue  # setup artifact, not judge logic
            h.update(os.path.relpath(p, HERE).encode())
            h.update(open(p, "rb").read())
    return h.hexdigest()


# ------------------------------------------------------------- slicing ----
def write_merged_process(artifact_dir, workdir):
    """Merge judge's orca-base.json (a process preset inheriting
    0.20mm Standard @BBL A1) with the artifact's profile.ini overrides, in
    that order; return the path of the merged process JSON."""
    with open(os.path.join(HERE, "orca-base.json")) as fh:
        base = json.load(fh)
    prof = load_profile(os.path.join(artifact_dir, "profile.ini"))
    merged = dict(base)
    merged.update(prof)
    # 'inherits' must survive for the system process preset to apply.
    if "inherits" in merged and merged["inherits"] != base.get("inherits"):
        # the artifact may not re-point the inheritance (slicing must stay
        # inside the pinned process family); it is an override set.
        merged["inherits"] = base["inherits"]
    out = os.path.join(workdir, "merged-process.json")
    with open(out, "w") as fh:
        json.dump(merged, fh, indent=2)
    return out


def run_orca(process_json, stl, outdir):
    """Slice stl with OrcaSlicer; return (rc, gcode_path_or_None, log)."""
    os.makedirs(outdir, exist_ok=True)
    env = dict(os.environ)
    env["APPDIR"] = os.path.join(TOOLS, "orca")
    env["HOME"] = os.path.expanduser("~")
    cmd = [ORCA, "--slice", "0", "--arrange", "0", "--orient", "0",
           "--load-settings", ";".join([MACHINE_PRESET, FILAMENT_PRESET,
                                         process_json]),
           "--outputdir", outdir, stl]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env=env, timeout=900)
    log = p.stdout.decode(errors="replace")
    gcode = None
    for cand in sorted(os.listdir(outdir)):
        if cand.endswith(".gcode"):
            gcode = os.path.join(outdir, cand)
    return p.returncode, gcode, log


def cached_slice(process_json, stl, workdir):
    key = hashlib.sha256(open(process_json, "rb").read()
                         + open(stl, "rb").read()).hexdigest()[:24]
    cache_dir = os.path.join(SLICE_CACHE, key)
    marker = os.path.join(cache_dir, ".done")
    if os.path.exists(marker):
        for cand in sorted(os.listdir(cache_dir)):
            if cand.endswith(".gcode"):
                return 0, os.path.join(cache_dir, cand), "cache"
    os.makedirs(cache_dir, exist_ok=True)
    rc, gcode, log = run_orca(process_json, stl, cache_dir)
    with open(os.path.join(workdir, "orca.log"), "a") as fh:
        fh.write(log)
    if rc == 0 and gcode:
        open(marker, "w").close()
    return rc, gcode, log


# ------------------------------------------------------------- klipper ----
def run_klipper(gcode, workdir):
    """Run klippy batch mode on the artifact G-code; return (rc, log)."""
    out_serial = os.path.join(workdir, "klipper-out.serial")
    p = subprocess.run(
        [sys.executable, KLIPPY, os.path.join(HERE, "printer.cfg"),
         "-i", gcode, "-o", out_serial, "-v", "-d", KLIPPER_DICT],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900)
    return p.returncode, p.stdout.decode(errors="replace")


def klipper_bad_lines(log):
    """Real failures: klippy errors, shutdowns, out-of-range moves.
    'Unknown command' is INFO-level and benign (Bambu-specific M-codes)."""
    bad = []
    for line in log.splitlines():
        t = line.strip()
        if re.search(r"\bERROR\b", t) or "Shutdown" in t \
                or "out of range" in t.lower() or "Timer too close" in t:
            if "Unknown command" in t:
                continue
            bad.append(t)
    return bad


# ------------------------------------------------------------- geometry ----
def layer_heights(layer_first_z):
    """Steady layer heights = consecutive Z deltas between extrusion layers."""
    return [round(layer_first_z[i + 1][0] - layer_first_z[i][0], 4)
            for i in range(len(layer_first_z) - 1)]


# --------------------------------------------------------------- main ----
def grade(artifact_dir, seed, json_path):
    t_start = time.time()
    spec = load_spec()
    artifact = os.path.abspath(artifact_dir)
    if not os.path.isdir(artifact):
        sys.exit("artifact directory not found: %s" % artifact)
    profile_ini = os.path.join(artifact, "profile.ini")
    part_gcode = os.path.join(artifact, "part.gcode")
    workdir = tempfile.mkdtemp(prefix="3dprint-grade-")
    stl_dir = os.path.join(workdir, "stl")
    os.makedirs(stl_dir, exist_ok=True)
    subprocess.run([sys.executable, os.path.join(DEMO, "task", "make_stl.py"),
                     "--outdir", stl_dir], check=True,
                    stdout=subprocess.DEVNULL)
    bracket_stl = os.path.join(stl_dir, "bracket.stl")
    cube_stl = os.path.join(stl_dir, "cube.stl")

    gates = {g: {"pass": False, "detail": ""} for g in GATE_ORDER}
    metrics = {}
    timing = {"grade_start_epoch": t_start}

    judge_hash_before = judge_dir_hash()

    def pass_fail(name, ok, detail):
        gates[name]["pass"] = bool(ok)
        gates[name]["detail"] = str(detail)

    # -- gate: slice_clean ------------------------------------------------
    t0 = time.time()
    process_json = write_merged_process(artifact, workdir)
    rc, resliced, log = cached_slice(process_json, bracket_stl, workdir)
    timing["slice_bracket_s"] = round(time.time() - t0, 1)
    ok = rc == 0 and resliced is not None
    if ok:
        metrics["resliced_gcode"] = os.path.basename(resliced)
    pass_fail("slice_clean", ok,
              "orca rc=%s gcode=%s" % (rc, os.path.basename(resliced)
                                       if resliced else "none"))

    # -- gate: artifact_matches -------------------------------------------
    if resliced and os.path.exists(part_gcode):
        h1 = gcode_content_hash(resliced)
        h2 = gcode_content_hash(part_gcode)
        metrics["artifact_hash"] = h2[:12]
        metrics["reslice_hash"] = h1[:12]
        ok = h1 == h2
        detail = "content hash match" if ok else \
            "re-slice %s != artifact %s (normalised)" % (h1[:12], h2[:12])
    else:
        ok = False
        detail = "missing part.gcode or failed re-slice"
        metrics["artifact_hash"] = None
    pass_fail("artifact_matches", ok, detail)

    # -- replay BOTH G-code files: the artifact's own part.gcode (the object
    #    under test) and the judge's re-slice of the same profile.  Every
    #    behavioural gate must hold on each: a bad G-code is caught on the
    #    artifact file, a bad profile on its re-slice. ------------------------
    t0 = time.time()
    m = interp.replay(part_gcode) if os.path.exists(part_gcode) else None
    m_res = interp.replay(resliced) if (resliced and os.path.exists(resliced)) else None
    timing["replay_s"] = round(time.time() - t0, 1)

    fa = 3.141592653589793 * (spec["filament_diameter_mm"] / 2.0) ** 2

    tris = interp.load_stl(bracket_stl)
    stl_vol = interp.stl_volume(tris)
    bbox = interp.stl_bbox(tris)
    metrics["stl_volume_mm3"] = round(stl_vol, 1)

    # -- behavioural gates, evaluated on BOTH replays -----------------------
    # Profile values the volume gate needs.
    prof = load_profile(profile_ini)
    wall_loops = int(float(prof.get("wall_loops", 2)))
    infill_pct = float(prof.get("sparse_infill_density", 15))
    infill = infill_pct / 100.0
    solid_b = int(float(prof.get("bottom_shell_layers", 3)))
    solid_t = int(float(prof.get("top_shell_layers", 4)))
    line_width = float(prof.get("line_width", 0.42))
    lh_max_spec = min(spec["layer_height_max_mm"],
                      0.8 * spec["nozzle_diameter_mm"])
    band = spec["volume_band_frac"]
    skirt = spec["skirt_allowance_mm3"]
    fp = interp.footprint_segments(tris, bbox)

    BEHAVIOURAL = ["moves_inside_bed", "moves_near_part", "layer_z_sequence",
                   "volume_matches_model", "pla_temperatures",
                   "time_estimate"]

    def behavioural(rm, gcode_path, label):
        """Evaluate the six behavioural gates on one G-code replay.

        Returns {gate: (ok, detail, extra_metrics)}; extra_metrics are
        merged into the verdict only for the artifact's own file (the
        object under test).
        """
        if rm is None or not gcode_path or not os.path.exists(gcode_path):
            return {g: (False, "no G-code to replay (%s)" % label, {})
                    for g in BEHAVIOURAL}
        out = {}

        # moves_inside_bed
        inside = all(0.0 <= mv[1] and mv[3] <= spec["bed_size_mm"][0]
                     and 0.0 <= mv[2] and mv[4] <= spec["bed_size_mm"][1]
                     and mv[0] >= 0.0
                     for mv in rm.extr_moves)
        worst = None
        if not inside:
            worst = min(rm.extr_moves,
                        key=lambda mv: min(mv[1], mv[3], mv[2], mv[4],
                                           -mv[0]))
        out["moves_inside_bed"] = (
            inside and not rm.errors,
            "all %d extruding moves inside bed" % len(rm.extr_moves)
            if inside else "move outside bed: %s" % (worst,), {})

        # moves_near_part
        tol = spec["brim_max_mm"]
        maxdist = 0.0
        off_part = []
        for mv in rm.extr_moves:
            if mv[0] > bbox[1][2] + tol:      # above part: travel/none
                continue
            d = interp.dist_to_footprint(mv[1], mv[2], fp)
            d2 = interp.dist_to_footprint(mv[3], mv[4], fp)
            dmax = max(d, d2)
            if dmax > tol:
                off_part.append((mv, dmax))
            maxdist = max(maxdist, dmax)
        out["moves_near_part"] = (
            not off_part,
            "max extrusion distance from footprint %.2f mm (tol %.2f)"
            % (maxdist, tol),
            {"max_dist_from_footprint_mm": round(maxdist, 2)})

        # layer_z_sequence
        zl = [z for z, _s in rm.layer_first_z]
        first_z = zl[0] if zl else None
        hs = layer_heights(rm.layer_first_z)
        steady = hs[1:] if len(hs) > 1 else []
        problems = []
        if first_z is None:
            problems.append("no extrusion layers")
        else:
            if not (spec["first_layer_height_min_mm"] <= first_z
                    <= spec["first_layer_height_max_mm"]):
                problems.append("first layer Z %.3f outside [%.2f, %.2f]"
                                % (first_z,
                                   spec["first_layer_height_min_mm"],
                                   spec["first_layer_height_max_mm"]))
            if first_z > spec["max_first_layer_vs_nozzle"] \
                    * spec["nozzle_diameter_mm"]:
                problems.append("first layer Z %.3f > %.2f x nozzle"
                                % (first_z,
                                   spec["max_first_layer_vs_nozzle"]))
        bad_steady = [h for h in steady if not (0.0 < h <= lh_max_spec)]
        if bad_steady:
            problems.append("steady layer heights out of band: %s"
                            % sorted(set(bad_steady))[:4])
        if rm.errors:
            problems.append("Z regression: " + rm.errors[0])
        out["layer_z_sequence"] = (
            not problems,
            "; ".join(problems) if problems
            else "first Z %.3f, %d layers, steady h %s"
                 % (first_z, len(zl), sorted(set(steady))),
            {"first_layer_z_mm": first_z, "layer_count": len(zl),
             "steady_layer_height_mm": sorted(set(steady))})

        # volume_matches_model
        deposited_mm3 = rm.e_consumed * fa
        lhs = [first_z] + [(z2 - z1) for z1, z2 in zip(zl, zl[1:])] \
            if first_z is not None else []
        if lhs:
            expected = interp.expected_deposit(tris, bbox, zl, lhs, 0.5,
                                               wall_loops, line_width,
                                               infill, solid_b, solid_t)
        else:
            expected = 0.0
        lo = expected * (1 - band) - skirt
        hi = expected * (1 + band) + skirt
        mass_g = deposited_mm3 / 1000.0 * spec["pla_density_g_cm3"]
        ok = lo <= deposited_mm3 <= hi and mass_g <= spec["max_filament_g"]
        out["volume_matches_model"] = (
            ok,
            "deposited %.1f mm3 vs expected %.1f (band %.1f..%.1f), "
            "mass %.2f g (max %.1f g)"
            % (deposited_mm3, expected, lo, hi, mass_g,
               spec["max_filament_g"]),
            {"deposited_volume_mm3": round(deposited_mm3, 1),
             "expected_volume_mm3": round(expected, 1),
             "volume_band_mm3": [round(lo, 1), round(hi, 1)],
             "filament_mass_g": round(mass_g, 2)})

        # pla_temperatures
        probs = []
        # Only set points issued while printing (before the last extruding
        # move) are constrained: trailing M104/M140 S0 is the normal cooldown.
        last_ext_seq = rm.last_extrude_seq
        printing_nozzle = [t for s, t in rm.nozzle_cmds
                           if s < (last_ext_seq or 0)]
        printing_bed = [t for s, t in rm.bed_cmds
                        if s < (last_ext_seq or 0)]
        nozzle_ok = all(spec["nozzle_temp_min_c"] <= t
                        <= spec["nozzle_temp_max_c"]
                        for t in printing_nozzle)
        bed_ok = all(spec["bed_temp_min_c"] <= t <= spec["bed_temp_max_c"]
                     for t in printing_bed)
        if not nozzle_ok:
            badt = [t for t in printing_nozzle
                    if not (spec["nozzle_temp_min_c"] <= t
                            <= spec["nozzle_temp_max_c"])]
            probs.append("nozzle temps out of PLA window: %s" % badt[:4])
        if not bed_ok:
            badt = [t for t in printing_bed
                    if not (spec["bed_temp_min_c"] <= t
                            <= spec["bed_temp_max_c"])]
            probs.append("bed temps out of PLA window: %s" % badt[:4])
        first_bed_seq = min((s for s, _t in rm.bed_cmds), default=None)
        if rm.first_extrude_seq is None or first_bed_seq is None \
                or first_bed_seq > rm.first_extrude_seq:
            probs.append("first bed-heat command does not precede "
                         "first extrusion")
        if rm.first_extrude_seq is None:
            probs.append("no extrusion in file")
        out["pla_temperatures"] = (
            not probs,
            "; ".join(probs) if probs else
            "nozzle %s C, bed %s C, bed heated before first extrusion"
            % (sorted({t for _s, t in rm.nozzle_cmds}),
               sorted({t for _s, t in rm.bed_cmds})),
            {"nozzle_setpoints_c": sorted({t for _s, t in rm.nozzle_cmds}),
             "bed_setpoints_c": sorted({t for _s, t in rm.bed_cmds})})

        # time_estimate
        slicer_t = interp.slicer_estimated_time_s(gcode_path)
        judge_t = rm.time_s
        ok = slicer_t is not None and judge_t is not None \
            and abs(judge_t - slicer_t) <= spec["time_band_frac"] * slicer_t \
            and slicer_t <= spec["max_print_time_s"]
        out["time_estimate"] = (
            ok,
            "judge %.0fs vs slicer %ss (band +-%.0f%%), max %ss"
            % (judge_t, slicer_t, 100 * spec["time_band_frac"],
               spec["max_print_time_s"]),
            {"judge_time_s": round(judge_t, 1), "slicer_time_s": slicer_t})

        return out

    t0 = time.time()
    art = behavioural(m, part_gcode if os.path.exists(part_gcode) else None,
                      "artifact")
    res = behavioural(m_res, resliced, "re-slice")
    for gname in BEHAVIOURAL:
        ok_a, det_a, extra_a = art[gname]
        ok_r, det_r, _ = res[gname]
        if ok_a and ok_r:
            detail = det_a
        elif not ok_a:
            detail = "artifact: %s" % det_a
        else:
            detail = "re-slice: %s" % det_r
        # metrics come from the artifact's own file (the object under test)
        metrics.update(extra_a)
        pass_fail(gname, ok_a and ok_r, detail)
    metrics["profile_wall_loops"] = wall_loops
    metrics["profile_infill_pct"] = infill_pct
    timing["behavioural_gates_s"] = round(time.time() - t0, 1)

    # -- gate: cube_crosscheck (judge QA: analytic band must hold on a
    #    simple solid) -------------------------------------------------------
    t0 = time.time()
    rc_c, cube_gcode, _log = cached_slice(process_json, cube_stl, workdir)
    ok = False
    detail = "cube slice failed rc=%s" % rc_c
    if rc_c == 0 and cube_gcode:
        cm = interp.replay(cube_gcode)
        cube_tris = interp.load_stl(cube_stl)
        cube_bbox = interp.stl_bbox(cube_tris)
        cube_vol = interp.stl_volume(cube_tris)
        czl = [z for z, _s in cm.layer_first_z]
        clhs = [czl[0]] + [(b - a) for a, b in zip(czl, czl[1:])]
        # 25mm cube, 2 walls, sparse infill; solid shell top/bottom
        cexp = interp.expected_deposit(cube_tris, cube_bbox, czl, clhs, 0.5,
                                       wall_loops, line_width, infill,
                                       solid_b, solid_t)
        cdep = cm.e_consumed * fa
        cband = cexp * (1 - band) - skirt
        chband = cexp * (1 + band) + skirt
        ok = cband <= cdep <= chband
        detail = ("cube deposited %.1f mm3 vs expected %.1f "
                  "(band %.1f..%.1f); stl vol %.1f"
                  % (cdep, cexp, cband, chband, cube_vol))
        metrics["cube_deposited_mm3"] = round(cdep, 1)
        metrics["cube_expected_mm3"] = round(cexp, 1)
        metrics["cube_stl_volume_mm3"] = round(cube_vol, 1)
    pass_fail("cube_crosscheck", ok, detail)
    timing["cube_gate_s"] = round(time.time() - t0, 1)

    # -- gate: klipper_batch ------------------------------------------------
    t0 = time.time()
    if os.path.exists(part_gcode):
        rc_k, klog = run_klipper(part_gcode, workdir)
        bad = klipper_bad_lines(klog)
        ok = rc_k == 0 and not bad
        detail = "klippy rc=%d, %d bad lines" % (rc_k, len(bad))
        if bad:
            detail += "; first: %s" % bad[0][:160]
    else:
        rc_k, bad, ok = None, [], False
        detail = "no part.gcode to run"
    metrics["klipper_exit"] = rc_k
    metrics["klipper_bad_lines"] = len(bad)
    pass_fail("klipper_batch", ok, detail)
    timing["klipper_gate_s"] = round(time.time() - t0, 1)

    # -- gate: profile_contract ---------------------------------------------
    probs = []
    if wall_loops < spec["wall_loops_min"]:
        probs.append("wall_loops %d < %d" % (wall_loops,
                                             spec["wall_loops_min"]))
    if not (spec["infill_pct_min"] <= infill_pct <= spec["infill_pct_max"]):
        probs.append("infill %.0f%% outside [%d%%, %d%%]"
                     % (infill_pct, spec["infill_pct_min"],
                        spec["infill_pct_max"]))
    fd = float(prof.get("filament_diameter", 1.75))
    nd = float(prof.get("nozzle_diameter", 0.4))
    if abs(fd - spec["filament_diameter_mm"]) > 1e-9:
        probs.append("filament_diameter %.2f != %.2f"
                     % (fd, spec["filament_diameter_mm"]))
    if abs(nd - spec["nozzle_diameter_mm"]) > 1e-9:
        probs.append("nozzle_diameter %.2f != %.2f"
                     % (nd, spec["nozzle_diameter_mm"]))
    pass_fail("profile_contract", not probs,
              "; ".join(probs) if probs
              else "wall_loops=%d infill=%.0f%% filament=%.2f nozzle=%.2f"
                   % (wall_loops, infill_pct, fd, nd))
    timing["profile_gate_s"] = round(time.time() - t0, 1)

    # -- gate: judge_intact -------------------------------------------------
    ok = judge_hash_before == judge_dir_hash()
    pass_fail("judge_intact", ok,
              "judge/ sha256 unchanged" if ok else "judge/ was modified")

    # -- verdict -------------------------------------------------------------
    verdict_pass = all(g["pass"] for g in gates.values())
    result = {
        "verdict": "PASS" if verdict_pass else "FAIL",
        "seed": seed,
        "artifact": artifact,
        "gates": gates,
        "metrics": metrics,
        "timing": dict(timing, grade_wall_s=round(time.time() - t_start, 1)),
    }
    out = json.dumps(result, indent=2, sort_keys=False)
    print(out)
    if json_path:
        with open(json_path, "w") as fh:
            fh.write(out + "\n")
    shutil.rmtree(workdir, ignore_errors=True)
    return 0 if verdict_pass else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()
    sys.exit(grade(args.artifact, args.seed, args.json))


if __name__ == "__main__":
    main()
