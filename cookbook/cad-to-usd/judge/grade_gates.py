"""grade_gates.py — run the cad-to-usd judge gates (see SPEC.md).

Invoked by judge/grade.sh; never by the artifact. Runs the gates against
a scratch copy of the artifact, writes the verdict JSON to
<work>/verdict.json, prints a human summary, exits 0 only if all gates
pass.

Determinism: --seed is accepted and recorded (the converter pipeline has
no random element; a fixed seed keeps the contract uniform with the
other cookbook demos). Grade output is byte-identical across runs
except the "timing" key.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oracle  # noqa: E402  (judge dir; -I keeps cwd out of sys.path)

GATES = ["file_set", "stage_meta", "geometry_counts", "bbox_match",
         "area_match", "conversion_script"]


def fail(msg):
    print(f"[grade] ERROR: {msg}", file=sys.stderr)
    sys.exit(2)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def gate_file_set(art):
    """All three usda present, non-empty, parse, and pairwise distinct."""
    detail = {"parts": {}, "pairwise_distinct": True}
    ok = True
    sums = {}
    for key, _src in oracle.PARTS:
        p = os.path.join(art, key + ".usda")
        entry = {"present": os.path.isfile(p)}
        if entry["present"]:
            entry["bytes"] = os.path.getsize(p)
            entry["sha256"] = sha256_file(p)
            sums[key] = entry["sha256"]
            if entry["bytes"] == 0:
                entry["present"] = False
                entry["error"] = "file is empty"
        else:
            entry["error"] = "missing"
            ok = False
        detail["parts"][key] = entry
    vals = list(sums.values())
    if len(set(vals)) != len(vals):
        detail["pairwise_distinct"] = False
        ok = False
    return ok, detail


def gate_per_part(art, sources_dir, stage_meta_only=False):
    """Measure each part's USDA and check meta/counts/bbox/area.

    Returns dict key -> {"ok": bool, "measure": {...}, "check": {...},
    "error": str?}; the USD side is measured with usd-core and the
    source side with OpenCASCADE (results in mm).
    """
    results = {}
    for key, src in oracle.PARTS:
        usd_path = os.path.join(art, key + ".usda")
        src_path = os.path.join(sources_dir, src)
        r = {"ok": False, "error": None, "measure": None, "check": None}
        try:
            meas = oracle.measure_usd(usd_path)
        except Exception as e:  # noqa: BLE001 — reported in the verdict
            r["error"] = f"usd: {e}"
            results[key] = r
            continue
        r["measure"] = oracle.jsonable(meas)
        try:
            ref = oracle.measure_source(src_path)
        except Exception as e:  # noqa: BLE001
            r["error"] = f"oracle: {e}"
            results[key] = r
            continue
        try:
            mpu_ok = abs(meas["meters_per_unit"] - oracle.REQUIRED_MPU) <= 1e-9
            up_ok = meas["up_axis"] == oracle.REQUIRED_UPAXIS
            counts_ok = meas["prims"] > 0 and meas["meshes"] > 0
            geom_ok, cmp_detail = oracle.compare(ref, oracle.to_mm(meas))
        except Exception as e:  # noqa: BLE001
            r["error"] = f"compare: {e}"
            results[key] = r
            continue
        r["check"] = {
            "meters_per_unit_ok": mpu_ok,
            "up_axis_ok": up_ok,
            "counts_ok": counts_ok,
            "geometry": oracle.jsonable(cmp_detail),
            "oracle": oracle.jsonable(ref),
        }
        r["ok"] = mpu_ok and up_ok and counts_ok and geom_ok
        results[key] = r
    return results


def pinned_source_hashes(demo_dir):
    """{sha256: source path} from judge/sources.txt (the pinned inputs)."""
    hashes = {}
    with open(os.path.join(demo_dir, "judge", "sources.txt")) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sha, path, _key = line.split("|")
            hashes[sha] = path
    return hashes


def conversions_of_pinned_sources(log_path, demo_dir):
    """Which pinned sources the artifact's convert.sh actually converted.

    Reads the judge-owned shim log (one 'call sha256=<..> out=<..>' line per
    converter invocation). An artifact that regenerates its outputs without
    feeding the pinned sources to the converter (e.g. by copying pre-made
    files) converts none of them and fails the gate.
    """
    wanted = pinned_source_hashes(demo_dir)
    converted = {}
    if os.path.isfile(log_path):
        with open(log_path) as f:
            for line in f:
                m = re.match(r"call sha256=([0-9a-f]{64}) out=(\S+)", line)
                if m and m.group(1) in wanted:
                    converted.setdefault(m.group(1), []).append(m.group(2))
    return converted, wanted


def run_convert_script(art, out_dir, sources_dir, conv_bin, log_path):
    """Run the artifact's convert.sh in a fresh dir with fresh sources.

    Working dir: <out_dir> with sources/ copied in untouched. The
    contract (SPEC.md): convert.sh reads sources/<original names> and
    writes <key>.usda into the cwd, exit 0 only if all conversions
    succeeded.
    """
    script = os.path.join(art, "convert.sh")
    if not os.path.isfile(script):
        return False, "convert.sh missing"
    if not os.access(script, os.X_OK):
        return False, "convert.sh not executable"
    os.makedirs(out_dir, exist_ok=True)
    shutil.copytree(sources_dir, os.path.join(out_dir, "sources"),
                    dirs_exist_ok=True)
    shutil.copy(script, os.path.join(out_dir, "convert.sh"))
    os.chmod(os.path.join(out_dir, "convert.sh"), 0o755)
    env = dict(os.environ)
    env["USD_CONVERT_CAD"] = conv_bin
    with open(log_path, "w") as log:
        try:
            rc = subprocess.run(
                ["bash", "convert.sh"], cwd=out_dir, env=env,
                stdout=log, stderr=subprocess.STDOUT, timeout=1800).returncode
        except subprocess.TimeoutExpired:
            return False, "convert.sh timed out after 1800 s"
    if rc != 0:
        with open(log_path) as log:
            tail = log.read()[-2000:]
        return False, f"convert.sh exited {rc}; tail:\n{tail}"
    for key, _src in oracle.PARTS:
        if not os.path.isfile(os.path.join(out_dir, key + ".usda")):
            return False, f"convert.sh did not produce {key}.usda"
    return True, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--demo", required=True)
    ap.add_argument("--seed", default="0")
    ap.add_argument("--python", required=True,
                    help="judge venv python (for subprocess oracle calls)")
    ap.add_argument("--converter", required=True,
                    help="path to the usd-convert-cad binary (the judge's shim)")
    ap.add_argument("--convert-log", required=True,
                    help="shim-owned log of converter invocations")
    ap.add_argument("--reconvert", default="1", choices=["0", "1"],
                    help="0 = skip gate 6 (self-test speed-up; the gate "
                         "reports 'skipped' and does not count)")
    args = ap.parse_args()

    t0 = time.monotonic()
    art = os.path.join(args.work, "artifact")
    sources = os.path.join(args.work, "sources")
    verdict = {
        "demo": "cad-to-usd",
        "seed": args.seed,
        "gates": {},
        "all_gates_passed": False,
    }

    # sources: fetched (or reused) into <work>/sources, sha256-verified
    fetch = subprocess.run(
        ["bash", os.path.join(args.demo, "judge", "fetch_sources.sh"),
         args.work],
        capture_output=True, text=True)
    print(fetch.stdout.strip())
    if fetch.returncode != 0:
        fail(f"fetch_sources.sh failed:\n{fetch.stdout}\n{fetch.stderr}")
    verdict["timing"] = {"fetch_sources_s": round(time.monotonic() - t0, 1)}

    # gate 1: file_set
    t = time.monotonic()
    ok, detail = gate_file_set(art)
    verdict["gates"]["file_set"] = {"passed": ok, "detail": detail}
    print(f"[grade] file_set: {'PASS' if ok else 'FAIL'}")
    verdict["timing"]["file_set_s"] = round(time.monotonic() - t, 1)
    if not ok:
        # every later gate would only re-report the same missing files
        verdict["gates"]["skipped_reason"] = "file_set failed"
        return finish(verdict, args.work, t0, 1)

    # gates 2-5: per-part measurement against the oracle
    t = time.monotonic()
    per_part = gate_per_part(art, sources)

    def part_gate(pred):
        """A gate passes when pred(check-or-error) holds for every part;
        a part that errored before its check was built fails the gate."""
        vals = []
        for r in per_part.values():
            if r["check"] is None:
                vals.append(False)
            else:
                vals.append(pred(r["check"]))
        return all(vals)

    verdict["gates"]["stage_meta"] = {
        "passed": part_gate(lambda c: c["meters_per_unit_ok"]
                            and c["up_axis_ok"]),
        "detail": {k: {"meters_per_unit": v["measure"]["meters_per_unit"],
                       "up_axis": v["measure"]["up_axis"],
                       "default_prim": v["measure"]["default_prim"]}
                   for k, v in per_part.items() if v["measure"]},
    }
    verdict["gates"]["geometry_counts"] = {
        "passed": part_gate(lambda c: c["counts_ok"]),
        "detail": {k: {"prims": v["measure"]["prims"],
                       "meshes": v["measure"]["meshes"],
                       "triangles": v["measure"]["triangles"]}
                   for k, v in per_part.items() if v["measure"]},
    }
    verdict["gates"]["bbox_match"] = {
        "passed": part_gate(lambda c: c["geometry"]["bbox_pass"]),
        "detail": {k: (v["check"]["geometry"]["bbox"] if v["check"] else
                       {"error": v["error"]})
                   for k, v in per_part.items()},
    }
    verdict["gates"]["area_match"] = {
        "passed": part_gate(lambda c: c["geometry"]["area_pass"]),
        "detail": {k: ({"area_usd_mm2": round(v["measure"]["area"] *
                                              ((v["measure"]["meters_per_unit"]
                                                * 1000) ** 2), 4),
                         "area_oracle_mm2": round(
                             v["check"]["oracle"]["area"], 4),
                         "rel_error": v["check"]["geometry"]["area_rel"],
                         "pass": v["check"]["geometry"]["area_pass"]}
                        if v["check"] else {"error": v["error"]})
                   for k, v in per_part.items()},
    }
    verdict["per_part"] = {k: {"ok": v["ok"], "error": v["error"]}
                           for k, v in per_part.items()}
    verdict["measures"] = {k: v["measure"] for k, v in per_part.items()}
    verdict["timing"]["gates_2_5_s"] = round(time.monotonic() - t, 1)

    # gate 6: conversion_script — re-run convert.sh on fresh sources
    t = time.monotonic()
    if args.reconvert == "0":
        verdict["gates"]["conversion_script"] = {
            "skipped": True,
            "detail": "skipped by --no-reconvert (self-test speed-up)"}
        print("[grade] conversion_script: SKIPPED (--no-reconvert)")
    else:
        regen = os.path.join(args.work, "regen")
        log = os.path.join(args.work, "convert_log.txt")
        conv_ok, conv_err = run_convert_script(art, regen, sources,
                                               args.converter, log)
        regen_detail = {"reproduced": conv_ok, "error": conv_err}
        if conv_ok:
            # gate 6 proof: every pinned source must appear in the judge's
            # converter-invocation log (the shim recorded each call's
            # input sha256). Copying shipped outputs converts nothing.
            converted, wanted = conversions_of_pinned_sources(
                args.convert_log, args.demo)
            regen_detail["sources_converted"] = {
                path: {"converted": sha in converted,
                       "outputs": converted.get(sha, [])}
                for sha, path in wanted.items()}
            unconverted = [p for sha, p in wanted.items()
                           if sha not in converted]
            if unconverted:
                regen_detail["unconverted_sources"] = unconverted
                conv_ok = False
                conv_err = ("convert.sh never converted the pinned source(s): "
                            + ", ".join(unconverted))
                regen_detail["error"] = conv_err
        if conv_ok:
            # grade the regenerated parts against gates 2-5
            regen_results = gate_per_part(regen, sources)
            regen_ok = all(v["ok"] for v in regen_results.values())
            regen_detail["per_part"] = {
                k: {"ok": v["ok"], "error": v["error"]}
                for k, v in regen_results.items()}
            regen_detail["measures"] = {
                k: v["measure"] for k, v in regen_results.items()}
        else:
            regen_ok = False
        verdict["gates"]["conversion_script"] = {
            "passed": regen_ok, "detail": regen_detail}
        print(f"[grade] conversion_script: "
              f"{'PASS' if regen_ok else 'FAIL'}")
    verdict["timing"]["conversion_script_s"] = round(time.monotonic() - t, 1)

    verdict["all_gates_passed"] = all(
        g["passed"] for g in verdict["gates"].values()
        if isinstance(g, dict) and "passed" in g)
    for name in ("stage_meta", "geometry_counts", "bbox_match", "area_match"):
        print(f"[grade] {name}: "
              f"{'PASS' if verdict['gates'][name]['passed'] else 'FAIL'}")
    return finish(verdict, args.work, t0,
                  0 if verdict["all_gates_passed"] else 1)


def finish(verdict, work, t0, rc):
    verdict["timing"]["total_s"] = round(time.monotonic() - t0, 1)
    out = os.path.join(work, "verdict.json")
    with open(out, "w") as f:
        json.dump(verdict, f, indent=2, sort_keys=True)
    print(f"[grade] verdict: "
          f"{'PASS' if verdict['all_gates_passed'] else 'FAIL'} "
          f"({out})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
