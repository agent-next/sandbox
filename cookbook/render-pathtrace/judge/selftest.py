"""Execute, do not infer, the judge's positive and negative controls."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from driver import Renderer
from grade import checksum, g1
from mutants import generate

HERE = Path(__file__).resolve().parent
GOOD = HERE.parent / "examples/good/scene.json"


def grade(path, seed, backend, api):
    proc = subprocess.run(
        ["sh", str(HERE / "grade.sh"), str(path), "--seed", str(seed),
         "--backend", backend, "--api", api],
        text=True, capture_output=True, timeout=630,
    )
    if proc.stderr:
        print(proc.stderr, file=sys.stderr, end="")
    verdict = json.loads(proc.stdout)
    assert (proc.returncode == 0) == verdict["pass"], "exit/verdict mismatch"
    return verdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--backend", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--api", choices=("webgpu", "webgl"), default="webgpu")
    args = parser.parse_args()
    before = checksum()
    start = time.monotonic()
    a = grade(GOOD, args.seed, args.backend, args.api)
    print("GOOD", json.dumps(a, sort_keys=True), flush=True)
    if not a["pass"]:
        print(json.dumps({"selftest_pass": False, "kill_rate": None,
                          "reason": "good control failed; mutant and determinism results not valid",
                          "timing": {"total_seconds": round(time.monotonic()-start, 3)}},
                         sort_keys=True), flush=True)
        return 1
    b = grade(GOOD, args.seed, args.backend, args.api)
    print("GOOD_REPEAT", json.dumps(b, sort_keys=True), flush=True)
    a.pop("timing", None)
    b.pop("timing", None)
    deterministic = a == b
    print(f"verdict_determinism={deterministic}", flush=True)
    killed = []
    with tempfile.TemporaryDirectory(prefix="pathtrace-mutants-") as temp:
        for name, path in generate(json.loads(GOOD.read_text()), temp):
            verdict = grade(path, args.seed, args.backend, args.api)
            caught = not verdict["pass"] and (
                verdict.get("error_kind") == "artifact"
                or any(not g["pass"] for g in verdict["gates"].values()))
            killed.append(caught)
            print("MUTANT", name, json.dumps(verdict, sort_keys=True), flush=True)
    try:
        with Renderer(args.backend, args.api) as renderer:
            wrong = g1(renderer, args.seed, wrong=True)
    except Exception as exc:
        wrong = {"pass": False, "error": f"{type(exc).__name__}: {exc}"}
    print("WRONG_ALBEDO_G1", json.dumps(wrong, sort_keys=True), flush=True)
    rate = sum(killed) / len(killed)
    wrong_rejected = "error" not in wrong and not wrong["pass"]
    ok = (a["pass"] and b["pass"] and deterministic and all(killed)
          and rate >= 0.9 and wrong_rejected and before == checksum())
    print(json.dumps({"selftest_pass": ok, "killed": sum(killed), "total": len(killed),
                      "kill_rate": rate, "verdict_determinism": deterministic,
                      "wrong_albedo_rejected": wrong_rejected,
                      "timing": {"total_seconds": round(time.monotonic()-start, 3)}},
                     sort_keys=True), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
