"""Artifact is data: no submitted Python is ever executed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from artifact import read_settings

HERE = Path(__file__).resolve().parent


def checksum():
    return {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(HERE.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def grade(artifact, seed, output=None):
    before = checksum()
    start = time.monotonic()
    verdict = {"pass": False, "gates": {}, "seed": seed}
    try:
        with tempfile.TemporaryDirectory(prefix="studio-grade-") as directory:
            temp = Path(directory)
            copy = temp / "scene.py"
            shutil.copyfile(artifact, copy)
            settings = read_settings(copy)
            trusted = temp / "judge"
            shutil.copytree(HERE, trusted, ignore=shutil.ignore_patterns("__pycache__"))
            (temp / "settings.json").write_text(json.dumps(settings))
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4",
                       OPENBLAS_NUM_THREADS="1")
            command = ["blender", "-b", "--factory-startup", "--python-exit-code", "1",
                       "-t", "4", "-P", str(trusted / "measure.py"), "--",
                       str(temp / "settings.json"), str(temp / "renders"), "--seed", str(seed)]
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=120, env=env)
            if result.returncode:
                raise RuntimeError("Blender failed: " + result.stderr[-2000:] +
                                   result.stdout[-2000:])
            verdict = json.loads((temp / "renders/measure.json").read_text())
            if output:
                output.mkdir(parents=True, exist_ok=True)
                for file in (temp / "renders").iterdir():
                    shutil.copyfile(file, output / file.name)
    except Exception as exc:
        verdict["error"] = f"{type(exc).__name__}: {exc}"
        verdict["pass"] = False
    verdict["judge_unchanged"] = before == checksum()
    verdict["pass"] = bool(verdict["pass"] and verdict["judge_unchanged"])
    verdict["timing"] = {"total_seconds": round(time.monotonic() - start, 3)}
    return verdict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("artifact", type=Path)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--json", type=Path)
    p.add_argument("--renders", type=Path)
    args = p.parse_args()
    if not 0 <= args.seed < 32000:
        p.error("seed must be in [0, 32000)")
    verdict = grade(args.artifact, args.seed, args.renders)
    text = json.dumps(verdict, sort_keys=True, allow_nan=False) + "\n"
    if args.json:
        args.json.write_text(text)
    print(text, end="")
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
