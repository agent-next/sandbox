#!/usr/bin/env python3 -I
"""media/make_data.py -- regenerate media/data/ from real judge outputs.

Usage (run by make_media.sh; needs the judge venv from judge/setup.sh):

    python -I make_data.py <demo_dir> <judge_venv_python> <stub_dir>

Produces, under media/data/:

  grade_good.json   verdict of `judge/grade.sh examples/good/panel.py`
                    (all four gates, real judge numbers)
  selftest.txt      verbatim `judge/selftest.sh` output (kill rate); the
                    scratch dir name in the first line is normalised to
                    "<scratch>" so the file is byte-stable across runs
  mutants.json      per-mutant verdicts from real grade.sh runs (the
                    `timing` key is dropped -- it is the one field the
                    standard lets vary between runs)
  render.png        the known-good panel's actual 1280x720 render, produced
                    by judge/render.py under exactly the environment
                    grade.sh uses (same env vars, same 9-frame settle, same
                    scratch-dir cwd)
  facts.json        the widget facts dump from that same render
  timings.json      measured wall seconds of the selftest and grade runs
                    (the video's sandbox segment states its real speed-up)

Nothing here invents a number: every value comes from a judge command, and
the render is byte-checked against the sha256 the grade verdict records.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEMO = Path(sys.argv[1]).resolve()
# NB: the venv interpreter must NOT be .resolve()d -- it is a symlink to the
# system python, and resolving it drops the venv's pyvenv.cfg (no
# site-packages, `import omni` fails under -I).
VENV_PY = Path(sys.argv[2])
STUB = Path(sys.argv[3]).resolve()
MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"

ENV = {
    **dict(os.environ),
    "OMNIUI_HEADLESS": "1",
    "OMNIUI_LAVAPIPE": "1",
    "OMNIUI_BACKEND": "vulkan",
    "LD_LIBRARY_PATH": f"{STUB}:{os.environ.get('LD_LIBRARY_PATH', '')}",
}

MUTANT_ORDER = [
    "missing_slider", "wrong_range", "wrong_swatch_color", "swatch_overflow",
    "empty_window", "wrong_button_text", "wrong_swatch_size",
    "missing_checkbox", "missing_swatch", "baked_png", "nondeterministic",
]

TOOLS = STUB.parent  # ~/tools/ovui-native-ui (venv + cuda-stub live here)


def normalize(text):
    """Strip machine-specific paths so data files are byte-stable and carry
    no internal hostnames/paths (public-repo hygiene; DEMO-STANDARD.md)."""
    text = text.replace(str(DEMO), "<demo>")
    text = text.replace(str(TOOLS), "<tools>")
    text = re.sub(r"/tmp/[A-Za-z0-9._-]+", "<scratch>", text)
    return text


def sh(cmd, cwd=None):
    return subprocess.run(cmd, check=True, capture_output=True,
                          text=True, cwd=cwd or DEMO, env=ENV).stdout


def stable_verdict(path):
    """Verdict JSON without the run-varying timing key, sorted keys,
    with internal paths normalised."""
    v = json.loads(Path(path).read_text())
    v.pop("timing", None)
    return normalize(json.dumps(v, indent=2, sort_keys=True)) + "\n"


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="ovui-media."))
    try:
        # -- 1. the known-good verdict (real grade.sh) ----------------------
        t0 = time.monotonic()
        grade = json.loads(sh(["bash", str(DEMO / "judge/grade.sh"),
                               str(DEMO / "examples/good/panel.py"),
                               "--json", str(work / "grade_good.json")]))
        grade_wall = time.monotonic() - t0
        (DATA / "grade_good.json").write_text(
            stable_verdict(work / "grade_good.json"))
        print(f"grade.sh examples/good/panel.py: pass={grade['pass']}")

        # -- 2. the self-test output (kill rate) ----------------------------
        t0 = time.monotonic()
        selftest = sh(["bash", str(DEMO / "judge/selftest.sh")])
        selftest_wall = time.monotonic() - t0
        (DATA / "selftest.txt").write_text(normalize(selftest))
        rate = [l for l in selftest.splitlines() if "kill rate" in l]
        print(f"selftest.sh: {rate[-1].strip() if rate else 'NO KILL RATE'}")
        (DATA / "timings.json").write_text(json.dumps({
            # rounded so the file is byte-stable across runs on the same box
            "selftest_wall_s": round(selftest_wall, 1),
            "grade_wall_s": round(grade_wall, 1),
        }, indent=2, sort_keys=True) + "\n")

        # -- 3. per-mutant verdicts (real grade.sh on each mutant) ----------
        mut_dir = work / "mutants"
        mut_dir.mkdir(exist_ok=True)
        sh([VENV_PY, "-I", str(DEMO / "judge/mutants.py"),
            str(DEMO / "examples/good/panel.py"), str(mut_dir)])
        mutants = {}
        for name in MUTANT_ORDER:
            out = work / f"mut_{name}.json"
            r = subprocess.run(
                ["bash", str(DEMO / "judge/grade.sh"),
                 str(mut_dir / f"mut_{name}.py"), "--json", str(out)],
                cwd=DEMO, env=ENV, capture_output=True, text=True)
            if out.exists():
                v = json.loads(stable_verdict(out))
            else:   # the run itself failed before a verdict was written
                v = {"pass": None,
                     "error": normalize((r.stdout + r.stderr)[-300:])}
            v["exit"] = r.returncode
            mutants[name] = v
        (DATA / "mutants.json").write_text(
            json.dumps(mutants, indent=2, sort_keys=True) + "\n")
        killed = sum(1 for v in mutants.values() if v.get("pass") is not True)
        print(f"mutants: {killed}/{len(mutants)} fail a gate")

        # -- 4. the real render + widget facts ------------------------------
        # grade.sh renders in a scratch dir it deletes on exit, so the
        # screenshot is taken here with the same harness (judge/render.py)
        # under exactly the environment grade.sh exports, then byte-checked
        # against the sha256 the verdict's determinism gate recorded --
        # proving it is the same image the judge graded.
        scratch = work / "render_scratch"
        scratch.mkdir()
        r = subprocess.run([VENV_PY, "-I", str(DEMO / "judge/render.py"),
                            str(DEMO / "examples/good/panel.py"),
                            str(scratch / "render.png"),
                            str(scratch / "facts.json")],
                           cwd=scratch, env=ENV, capture_output=True,
                           text=True, timeout=90)
        if r.returncode != 0:
            raise SystemExit(f"render failed:\n{r.stdout[-2000:]}"
                             f"\n{r.stderr[-2000:]}")
        sha = hashlib.sha256((scratch / "render.png").read_bytes()).hexdigest()
        det = [g for g in grade["gates"] if g["gate"] == "determinism"][0]
        if sha[:16] != det["sha256"]:
            raise SystemExit(
                f"render sha {sha[:16]} != graded sha {det['sha256']} -- the "
                "captured render differs from what the judge graded; "
                "refusing to ship it")
        (DATA / "render.png").write_bytes(
            (scratch / "render.png").read_bytes())
        (DATA / "facts.json").write_text((scratch / "facts.json").read_text())
        print(f"render.png: sha256 {sha[:16]} == graded determinism sha")
    finally:
        subprocess.run(["rm", "-rf", str(work)], check=True)

    print("make_data.py: done")


if __name__ == "__main__":
    main()
