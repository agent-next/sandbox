import argparse
import json
from pathlib import Path
import sys
import tempfile
import time

from grade import grade
from mutants import generate

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--out", type=Path, default=HERE.parent / "outputs-selftest")
    args = p.parse_args()
    if not 0 <= args.seed < 32000:
        p.error("seed must be in [0, 32000)")
    args.out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    good = HERE.parent / "examples/good/scene.py"
    a = grade(good, args.seed, args.out / "good")
    b = grade(good, args.seed)
    def stable(v):
        return json.dumps({k: value for k, value in v.items() if k != "timing"},
                          sort_keys=True)
    identical = stable(a) == stable(b)
    rows = {}
    with tempfile.TemporaryDirectory(prefix="studio-mutants-") as directory:
        for name, artifact in generate(good, Path(directory)).items():
            v = grade(artifact, args.seed, args.out / name)
            rows[name] = v
            failed = [k for k, g in v["gates"].items() if not g["pass"]]
            print(f"MUTANT {name}: killed={not v['pass']} failed={','.join(failed)}",
                  flush=True)
    killed = sum(not v["pass"] and bool(v["gates"]) and v["judge_unchanged"]
                 and "error" not in v for v in rows.values())
    summary = {"pass": a["pass"] and b["pass"] and identical and killed == len(rows),
               "good": a, "repeat": b, "deterministic": identical,
               "killed": killed, "total": len(rows), "kill_rate": killed / len(rows),
               "mutants": rows,
               "timing": {"total_seconds": round(time.monotonic() - start, 3)}}
    (args.out / "selftest.json").write_text(json.dumps(summary, sort_keys=True) + "\n")
    print(f"GOOD pass={a['pass']} repeat={b['pass']} byte_identical={identical}")
    print(f"SELFTEST killed={killed}/{len(rows)} kill_rate={100*killed/len(rows):.1f}% "
          f"exit={0 if summary['pass'] else 1} wall={summary['timing']['total_seconds']}s")
    print("GOOD_VERDICT " + json.dumps(a, sort_keys=True))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
