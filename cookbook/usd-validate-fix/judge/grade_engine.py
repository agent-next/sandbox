#!/usr/bin/env python3
"""Grade engine for the usd-validate-fix judge (called by grade.sh).

Runs the three SPEC.md gates on a scratch copy of the artifact:
  gate 1  nvidia_usd_validate (pinned build), default rule set, the one
          rule that cannot pass under pip usd-core disabled; zero
          FAILURE/ERROR issues and status PASS required.
  gate 2  judge/oracle.py -- an independent recount with usd-core alone.
  gate 3  oracle geometry check against task/traffic_cone_broken.usda
          (point count and bbox invariance).

Prints one JSON verdict on stdout.  Wall-clock fields live only under the
"timing" key, so two runs with the same seed are byte-identical.  Exits 0
only if all gates pass.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

JDIR = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(JDIR)
VENV = os.path.expanduser("~/.usd-validate-fix-venv")
VALIDATE = os.path.join(VENV, "bin", "nvidia_usd_validate")
VENV_PY = os.path.join(VENV, "bin", "python")

# Gate 1 disables exactly this rule: under pip usd-core the Sdr registry has
# no shaderDefs.usda, so no shader id ever resolves and the rule can only
# report its environmental warning -- as a FAIL for the stage.
DISABLED_RULE = "MaterialUsdPreviewSurfaceChecker"
REFERENCE = os.path.join(DEMO, "task", "traffic_cone_broken.usda")


def gate1_validator(copy: str) -> tuple[list, dict]:
    """Run the pinned NVIDIA validator on the scratch copy."""
    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "validate.json")
        proc = subprocess.run(
            [VALIDATE, copy, "-D", DISABLED_RULE,
             "--json-output", report],
            capture_output=True, text=True, timeout=600)
        data = None
        if os.path.exists(report):
            with open(report, encoding="utf-8") as fh:
                data = json.load(fh)
    errors = []
    if proc.returncode != 0:
        errors.append("nvidia_usd_validate exited %d" % proc.returncode)
    if data is None:
        errors.append("validator produced no JSON report")
        return errors, {"validator_exit": proc.returncode}
    if data.get("status") != "PASS":
        errors.append("validator status %r != 'PASS'" % data.get("status"))
    severities: dict[str, int] = {}
    rules_failed = []
    for entry in data.get("rules", []):
        name = entry.get("rule", {}).get("name", "?")
        if entry.get("status") != "PASS":
            rules_failed.append(name)
        for issue in entry.get("issues", []):
            sev = issue.get("severity", "?")
            severities[sev] = severities.get(sev, 0) + 1
            if sev in ("FAILURE", "ERROR"):
                errors.append("%s: %s" % (name, issue.get("message", "")))
    facts = {"validator_exit": proc.returncode,
             "validator_status": data.get("status"),
             "issues_by_severity": severities,
             "rules_not_passing": sorted(rules_failed)}
    return errors, facts


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json")
    args, _ = ap.parse_known_args()

    timing = {"total_s": None}
    t0 = time.monotonic()
    gates: dict[str, dict] = {}
    ok = True

    with tempfile.TemporaryDirectory() as tmp:
        # scratch copy: the artifact must never touch the judge or the repo
        copy = os.path.join(tmp, "artifact.usda")
        with open(args.artifact, "rb") as src, open(copy, "wb") as dst:
            dst.write(src.read())

        t1 = time.monotonic()
        g1_errors, g1_facts = gate1_validator(copy)
        t2 = time.monotonic()
        sys.path.insert(0, JDIR)
        import oracle  # noqa: E402  (needs the venv's pxr)

        g2_errors, g2_facts = oracle.check_asset(copy)
        t3 = time.monotonic()
        g3_errors, g3_facts = oracle.check_geometry(copy, REFERENCE)
        t4 = time.monotonic()

        timing.update(validator_s=round(t2 - t1, 3),
                      oracle_s=round(t3 - t2, 3),
                      geometry_s=round(t4 - t3, 3),
                      total_s=round(t4 - t0, 3))

        gates["validator"] = {"passed": not g1_errors,
                             "errors": g1_errors, **g1_facts}
        gates["oracle"] = {"passed": not g2_errors,
                           "errors": g2_errors}
        gates["geometry"] = {"passed": not g3_errors,
                             "errors": g3_errors}

        verdict = {
            "artifact": os.path.abspath(args.artifact),
            "seed": args.seed,
            "passed": ok and all(g["passed"] for g in gates.values()),
            "failed_gate": next((name for name, g in gates.items()
                                 if not g["passed"]), None),
            "gates": gates,
            "facts": {"validator": g1_facts, "oracle": g2_facts,
                      "geometry": g3_facts},
            "timing": timing,
        }
        verdict["passed"] = all(g["passed"] for g in gates.values())
        verdict["failed_gate"] = next(
            (name for name, g in gates.items() if not g["passed"]), None)

        text = json.dumps(verdict, indent=1, sort_keys=True)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        else:
            print(text)
        return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
