#!/usr/bin/env python3
"""Grade engine for the usd-validate-fix judge (called by grade.sh).

Runs the SPEC.md gates on a scratch copy of the artifact:
  gate 1  nvidia_usd_validate (pinned build), default rule set, the one
          rule that cannot pass under pip usd-core disabled; zero
          FAILURE/ERROR issues and status PASS required.
  gate 2  judge/oracle.py -- an independent recount with usd-core alone.
  gate 3  oracle geometry check against task/traffic_cone_broken.usda:
          world-space bbox invariance (kills xformOp scale/move cheats).
  gate 4  judge/text_recount.py -- a clean-room recount from the artifact's
          own text (stdlib only), cross-checked against the oracle's
          numbers.  Kills an artifact that composes in external geometry
          (subLayers) or otherwise influences the pxr stack: the oracle
          sees the composed stage while the text parser sees only the one
          self-contained layer, and any disagreement fails the grade.
          Also rejects any xformOp the original does not author.
  gate 5  oracle.check_up_axis -- the stage's declared upAxis must be the
          axis the measured world bbox is tallest along.

Every gate runs behind _safe(), so a gate that raises becomes that gate's
failure (a named error and a verdict), never a traceback and a missing
verdict: the self-test must only count mutants killed BY A GATE.
  gate 4  judge/text_recount.py -- a clean-room recount from the artifact's
          own text (stdlib only), cross-checked against the oracle's
          numbers.  Kills an artifact that composes in external geometry
          (subLayers) or otherwise influences the pxr stack: the oracle
          sees the composed stage while the text parser sees only the one
          self-contained layer, and any disagreement fails the grade.

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


def _safe(fn):
    """Wrap one gate so an exception becomes that gate's *failure*.

    A judging gate that raises (a malformed artifact the oracle cannot open,
    a recount that cannot parse the bytes) must still produce a verdict and
    a named failed_gate -- an AttributeError traceback with no JSON is how
    a crash gets miscounted as a killed mutant.
    """
    def wrapper(*args):
        try:
            return fn(*args)
        except Exception as exc:                      # noqa: BLE001
            # Never let building the error message lose the verdict: a pxr
            # exception holding non-UTF-8 bytes raises in both str() and
            # repr(), so fall back to the type name and the arg count.
            try:
                detail = str(exc)
            except Exception:                         # noqa: BLE001
                try:
                    detail = repr(exc)
                except Exception:                     # noqa: BLE001
                    detail = "<%s with %d arg(s)>" % (type(exc).__name__,
                                                      len(exc.args))
            return ["%s raised %s: %s"
                    % (fn.__name__, type(exc).__name__, detail)], {}
    return wrapper


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
        name = (entry.get("rule") or {}).get("name", "?")
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

    with tempfile.TemporaryDirectory() as tmp:
        # scratch copy: the artifact must never touch the judge or the repo
        copy = os.path.join(tmp, "artifact.usda")
        with open(args.artifact, "rb") as src, open(copy, "wb") as dst:
            dst.write(src.read())

        t1 = time.monotonic()
        g1_errors, g1_facts = _safe(gate1_validator)(copy)
        t2 = time.monotonic()
        sys.path.insert(0, JDIR)
        import oracle  # noqa: E402  (needs the venv's pxr)

        g2_errors, g2_facts = _safe(oracle.check_asset)(copy)
        t3 = time.monotonic()
        g3_errors, g3_facts = _safe(oracle.check_geometry)(copy, REFERENCE)
        t4 = time.monotonic()

        g5_errors, g5_facts = _safe(oracle.check_up_axis)(copy)
        t4b = time.monotonic()

        # gate 4: clean-room text recount + cross-check against the oracle.
        # text_recount is stdlib-only and reads the artifact's own text file,
        # never pxr, so composing an external layer (subLayers cheat) is
        # visible to it even when the pxr oracle sees the composed stage.
        import text_recount  # noqa: E402  (stdlib only; is our code, not the
        #                                     artifact -- it runs in this process,
        #                                     the artifact itself never executes)
        r4_errors, r4_facts = _safe(text_recount.check_asset)(copy)
        r4g_errors, r4g_facts = _safe(text_recount.check_geometry)(
            copy, REFERENCE)
        x_errors = _safe(text_recount.cross_check)(
            g2_facts, r4_facts, g3_facts, r4g_facts)
        g4_errors = (r4_errors + r4g_errors + x_errors)
        t5 = time.monotonic()

        timing.update(validator_s=round(t2 - t1, 3),
                      oracle_s=round(t3 - t2, 3),
                      geometry_s=round(t4 - t3, 3),
                      up_axis_s=round(t4b - t4, 3),
                      recount_s=round(t5 - t4b, 3),
                      total_s=round(t5 - t0, 3))

        gates["validator"] = {"passed": not g1_errors,
                             "errors": g1_errors, **g1_facts}
        gates["oracle"] = {"passed": not g2_errors,
                           "errors": g2_errors}
        gates["geometry"] = {"passed": not g3_errors,
                             "errors": g3_errors}
        gates["up_axis"] = {"passed": not g5_errors,
                            "errors": g5_errors}
        gates["recount"] = {"passed": not g4_errors,
                            "errors": g4_errors}

        facts = {"validator": g1_facts, "oracle": g2_facts,
                 "geometry": g3_facts, "up_axis": g5_facts,
                 "recount": r4_facts,
                 "recount_geometry": r4g_facts,
                 "crosscheck": {"passed": not x_errors,
                                "errors": x_errors}}

        verdict = {
            "artifact": os.path.abspath(args.artifact),
            "seed": args.seed,
            "gates": gates,
            "facts": facts,
            "timing": timing,
        }
        verdict["passed"] = all(g["passed"] for g in gates.values())
        verdict["failed_gate"] = next(
            (name for name, g in gates.items() if not g["passed"]), None)

        text = json.dumps(verdict, indent=1, sort_keys=True)
        # Always print the verdict on stdout (run.py parses it from there)
        # and additionally write the file when --json was given.
        print(text)
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                fh.write(text + "\n")
        return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
