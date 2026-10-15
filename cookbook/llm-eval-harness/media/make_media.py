#!/usr/bin/env python3
"""media/make_media.py — regenerate every media file from judge outputs.

Runs judge/setup.sh + judge/selftest.sh + judge/grade.sh (seed 42) locally,
then draws:

  result.png  judged pass@1/pass@k for the good artifact and the judge-built
              mixed file (k=2), with the pass line at 1.0
  loop.png    per-task pass counts (good artifact) + the self-test kill-rate
              bars (good vs each known-bad mutant)
  demo.mp4    captioned step-through of the above figures

matplotlib + ffmpeg must be installed (make_media.sh does that first).
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
JUDGE = DEMO / "judge"
GOOD = DEMO / "examples" / "good"
SEED = 42

# colour-blind-safe palette (Wong, 2011, Nature Methods)
C_BLUE = "#0072B2"
C_ORANGE = "#E69F00"
C_GREEN = "#009E73"
C_RED = "#D55E00"
C_GREY = "#999999"


def run(cmd, cwd=None, check=True):
    print("[media] $", " ".join(map(str, cmd)), flush=True)
    return subprocess.run(cmd, check=check, cwd=cwd or str(DEMO))


def grade(samples, eval_py, tag, out):
    # mutants are EXPECTED to fail grading; the verdict JSON still records it
    run(["bash", str(JUDGE / "grade.sh"), str(samples), str(eval_py),
         "--json", str(out), "--seed", str(SEED)], check=False)
    with open(out) as fh:
        return json.load(fh)


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tmp = Path(tempfile.mkdtemp(prefix="harness-media-"))
    good_verdict = grade(GOOD / "samples.jsonl", GOOD / "eval.py",
                         "good", tmp / "good.json")

    print("[media] selftest ...", flush=True)
    run(["bash", str(JUDGE / "selftest.sh")])

    # ---- selftest kill-rate data (re-grade the mutants) ----------------------
    bad_dir = DEMO / "examples" / "bad"
    mutants = sorted(d.name for d in bad_dir.iterdir() if d.is_dir())
    killed = []
    for m in mutants:
        d = bad_dir / m
        run(["bash", str(JUDGE / "grade.sh"), str(d / "samples.jsonl"),
             str(d / "eval.py"), "--json", str(tmp / f"{m}.json"),
             "--seed", str(SEED)])
        with open(tmp / f"{m}.json") as fh:
            v = json.load(fh)
        killed.append(not v["all_gates_passed"])

    mv = good_verdict["mixed_samples"]

    # ============================== result.png ==============================
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    labels = [f"good artifact\n(n=1/task, k=1)",
              f"judge mixed file\n(n=1-3/task, k=2)"]
    p1 = [good_verdict["judge_values"]["pass@1"], mv["pass@1"]]
    pk = [good_verdict["judge_values"]["pass@k"], mv["pass@k"]]
    x = range(len(labels))
    w = 0.36
    b1 = ax.bar([i - w / 2 for i in x], p1, w, label="pass@1", color=C_BLUE)
    b2 = ax.bar([i + w / 2 for i in x], pk, w, label="pass@k", color=C_ORANGE)
    for bars in (b1, b2):
        for b in bars:
            ax.annotate(f"{b.get_height():.4f}",
                        (b.get_x() + b.get_width() / 2, b.get_height()),
                        ha="center", va="bottom", fontsize=9)
    ax.axhline(1.0, color=C_GREEN, lw=1.5, ls="--",
               label="pass line (1.0 = all pass)")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("score")
    ax.set_title("llm-eval-harness judge — judged pass@1 / pass@k "
                 "(seed 42, exact-Fraction oracle)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(HERE / "result.png", dpi=200)
    plt.close(fig)

    # ============================== loop.png ================================
    fig, (axl, axr) = plt.subplots(1, 2, figsize=(11.0, 4.6),
                                   gridspec_kw={"width_ratios": [1.35, 1.0]})
    pt = good_verdict["per_task_c"]
    tids = sorted(int(t) for t in pt)
    axl.bar([str(t) for t in tids], [pt[str(t)] for t in tids], color=C_BLUE)
    axl.set_title(f"per-task passing samples — good artifact "
                  f"({sum(pt.values())}/{len(tids)})", fontsize=10)
    axl.set_xlabel("MBPP task_id")
    axl.set_ylabel("passing samples (n=1 per task)")
    axl.set_ylim(0, 1.35)
    axl.tick_params(axis="x", labelrotation=90, labelsize=7)
    axl.axhline(1.0, color=C_GREEN, lw=1.2, ls="--")

    names = ["good"] + mutants
    vals = [1] + [1 if k else 0 for k in killed]
    colors = [C_GREEN] + [C_ORANGE if k else C_RED for k in killed]
    axr.bar(range(len(names)), vals, color=colors)
    axr.set_xticks(range(len(names)))
    axr.set_xticklabels(names, rotation=45, ha="right", fontsize=8)
    axr.set_ylim(0, 1.15)
    axr.set_ylabel("passed all gates?")
    axr.set_title(f"self-test kill rate — {sum(killed)}/{len(mutants)} mutants "
                  f"killed ({100*sum(killed)//len(mutants)}%)", fontsize=10)
    for i, v in enumerate(vals):
        axr.annotate("PASS" if v else "KILLED", (i, v), ha="center",
                     va="bottom" if v else "top", fontsize=8)
    fig.tight_layout()
    fig.savefig(HERE / "loop.png", dpi=200)
    plt.close(fig)

    # ============================== demo.mp4 ================================
    frames = tmp / "frames"
    frames.mkdir(exist_ok=True)
    for src, cap in [
        ("result.png", "Judge verdict: pass@1 and pass@k on the good artifact "
                       "and the judge-built mixed file (seed 42, exact-Fraction oracle)"),
        ("loop.png", "the loop: every sample executed in isolation — 30/30 pass; "
                     "then the self-test: 5/5 known-bad mutants killed"),
    ]:
        fig = plt.figure(figsize=(12.8, 7.2))
        img = plt.imread(HERE / src)
        fig.figimage(img, xo=0, yo=(720 - img.shape[0] * 2) // 2 + 40)
        fig.text(0.06, 0.06, cap, fontsize=13, color="white",
                 va="center", ha="left",
                 bbox=dict(facecolor="#111111", alpha=0.85, pad=8))
        fig.savefig(frames / src, facecolor="#111111")
        plt.close(fig)
    master = HERE / "master" / "master.mp4"
    master.parent.mkdir(exist_ok=True)
    run(["ffmpeg", "-y", "-framerate", "1/14", "-i",
         str(frames / "%d.png"),
         "-c:v", "libx264", "-crf", "0", "-pix_fmt", "yuv420p", str(master)])
    run(["ffmpeg", "-y", "-i", str(master),
         "-c:v", "libx264", "-crf", "18", "-preset", "slow",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         str(HERE / "demo.mp4")])

    # =========================== MANIFEST.json =============================
    manifest = {
        "result.png": {
            "shows": "judged pass@1/pass@k for the good artifact and the "
                     "mixed file, with the pass line at 1.0",
            "command": "media/make_media.sh (grade.sh seed 42 -> result.png)",
            "source_data": "verdict JSON from judge/grade.sh examples/good "
                           "(generated from data/mbpp_subset.jsonl, sha256-pinned)",
            "sha256": _sha(HERE / "result.png"),
        },
        "loop.png": {
            "shows": "per-task passing samples (good artifact) and the "
                     "self-test kill-rate bars for good vs 5 known-bad mutants",
            "command": "media/make_media.sh (grade.sh + selftest.sh -> loop.png)",
            "source_data": "verdict JSONs from judge/grade.sh",
            "sha256": _sha(HERE / "loop.png"),
        },
        "demo.mp4": {
            "shows": "28 s step-through of result.png then loop.png with "
                     "captions (the harness is not time-dependent)",
            "command": "media/make_media.sh (ffmpeg from result.png/loop.png)",
            "source_data": "media/result.png, media/loop.png",
            "sha256": _sha(HERE / "demo.mp4"),
        },
    }
    with (HERE / "MANIFEST.json").open("w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")

    shutil.rmtree(tmp, ignore_errors=True)
    print("[media] done:", *[p.name for p in sorted(HERE.glob('*'))
                               if p.suffix in ('.png', '.mp4', '.json')])


def _sha(p):
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
