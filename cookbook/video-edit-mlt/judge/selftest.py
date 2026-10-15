"""Exercise actual renders, intended mutant gates, and repeatability."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grade import grade, DEMO, checksums
from mutants import generate, INTENDED


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    before = checksums()
    subprocess.run([sys.executable, "-B", "-m", "unittest", "discover",
                    "-s", str(DEMO / "tests"), "-v"], check=True)
    spec = json.loads((DEMO / "spec.json").read_text())
    good = DEMO / "examples/good/edit.mlt"
    first = grade(good, spec, 1)
    if not first["passed"]:
        print(json.dumps(first, indent=2), flush=True)
        return 1
    print("selftest: known-good PASSED all gates", flush=True)
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        generate(good, Path(tmp))
        for name, intended in INTENDED.items():
            v = grade(Path(tmp) / f"{name}.mlt", spec, 1)
            killed = not v["passed"] and v["failed_gate"] == intended
            results[name] = {"killed": killed, "intended": intended, "verdict": v}
            print(f"selftest: {'killed' if killed else 'WRONG RESULT'} {name} "
                  f"(gate: {v['failed_gate']}; intended: {intended})", flush=True)
    killed = sum(r["killed"] for r in results.values())
    print(f"selftest: kill rate {killed}/{len(results)} = {killed/len(results):.0%}", flush=True)
    second = grade(good, spec, 1)
    for v in (first, second):
        v.pop("timing", None)
    deterministic = first == second
    print(f"selftest: determinism {'OK' if deterministic else 'FAILED'} "
          "(two --seed 1 grades, excluding timing)", flush=True)
    intact = before == checksums()
    print(f"selftest: judge integrity {'OK' if intact else 'FAILED'}", flush=True)
    if args.json:
        args.json.write_text(json.dumps({"good": first, "mutants": results,
                                        "deterministic": deterministic, "intact": intact},
                                       sort_keys=True, indent=2)+"\n")
    ok = killed == len(results) and deterministic and intact
    print(f"selftest: {'OK' if ok else 'FAILED'}", flush=True)
    return int(not ok)


if __name__ == "__main__":
    sys.exit(main())
