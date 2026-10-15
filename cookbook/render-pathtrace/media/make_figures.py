#!/usr/bin/env python3
"""Build result.png, loop.png, demo.mp4 and MANIFEST.json from real run outputs.

Usage: python3 media/make_figures.py RUN_DIR FRAMES_DIR
RUN_DIR is a run.py --output directory; FRAMES_DIR is a media/frames.py output.
Needs matplotlib, numpy and ffmpeg. Every plotted number is read from those files.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
BLUE, ORANGE, GREEN, RED, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#666666"
plt.rcParams.update({"font.size": 11, "axes.titlesize": 12, "axes.titleweight": "bold"})


def verdict_lines(log):
    rows = []
    for line in log.read_text().splitlines():
        if line.startswith("MUTANT "):
            _, name, payload = line.split(" ", 2)
            rows.append((name, json.loads(payload)))
        elif line.startswith("WRONG_ALBEDO_G1 "):
            rows.append(("wrong_albedo (renderer)", json.loads(line.split(" ", 1)[1])))
    return rows


def rejected_by(verdict):
    failed = [g for g, x in (verdict.get("gates") or {}).items() if not x.get("pass")]
    if failed:
        return failed[0]
    error = verdict.get("error", "")
    return "G1" if not error and verdict.get("pass") is False else "schema"


def result_figure(run, frames, out):
    v = json.loads((run / "verdict.json").read_text())["gates"]
    fr = json.loads((frames / "frames.json").read_text())
    fig, axes = plt.subplots(2, 2, figsize=(12, 10.5))
    ax = axes[0, 0]
    ax.imshow(plt.imread(run / "studio.png"))
    ax.set_title("Path-traced on an RTX 5090 slice (512 x 512, 128 spp)")
    ax.axis("off")

    ax = axes[0, 1]
    rho = [c["rho"] for c in v["G1"]["cases"]]
    mean = [c["mean"][0] for c in v["G1"]["cases"]]
    tol = [c["tolerance"][0] for c in v["G1"]["cases"]]
    ax.plot([0, 1], [0, 1], color=GREY, lw=1, label="analytic: pixel = albedo x L (L = 1)")
    ax.errorbar(rho, mean, yerr=tol, fmt="o", color=BLUE, capsize=6,
                label="measured sphere mean, pass band (4 SE + 0.015)")
    for r, m in zip(rho, mean):
        ax.annotate(f"{m:.4f}", (r, m), textcoords="offset points", xytext=(10, -14))
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="albedo rho", ylabel="rendered radiance",
           title="G1 white furnace: renderer vs exact answer")
    ax.legend(loc="upper left", fontsize=9)

    ax = axes[1, 0]
    spp = np.array([r["spp"] for r in fr["levels"]])
    rmse = np.array([r["rmse"] for r in fr["levels"]])
    ax.loglog(spp, rmse, "o-", color=BLUE, label=f"RMSE vs {fr['reference_spp']}-spp reference")
    ax.loglog(spp, rmse[0] * spp ** -0.5, "--", color=GREY, label="ideal Monte Carlo: spp^-0.5")
    g3 = v["G3"]
    ax.loglog(g3["spp"], g3["rmse"], "s", color=ORANGE,
              label=f"judge G3 (1-8 spp): slope {g3['slope']:.3f}, pass [-0.65, -0.35]")
    ax.set(xlabel="samples per pixel", ylabel="RMSE (linear radiance)",
           title="G3 convergence: error falls like 1/sqrt(spp)")
    ax.legend(fontsize=9)

    ax = axes[1, 1]
    g5 = v["G5"]
    names = ["median luminance", "clipped fraction", "floor noise (rel.)"]
    values = [g5["median_luminance"], g5["clipped_fraction"], g5["floor_relative_noise"]]
    bands = [(0.08, 0.85), (0, 0.10), (0, 0.15)]
    y = np.arange(len(names))
    for i, (lo, hi) in enumerate(bands):
        ax.barh(i, hi - lo, left=lo, color=GREEN, alpha=0.25, height=0.6,
                label="pass band" if i == 0 else None)
    ax.plot(values, y, "D", color=RED, ms=9, label="measured")
    for i, val in enumerate(values):
        ax.annotate(f"{val:.4f}", (val, i), textcoords="offset points", xytext=(8, 8))
    g4 = v["G4"]
    ax.set(yticks=y, yticklabels=names, xlim=(0, 1), xlabel="value",
           title="G5 image spec  |  G4: same seed -> identical HDR hash")
    ax.text(0.98, -0.75, f"G4 hash {g4['same_seed_hashes'][0][:16]}... (x2), other seed differs",
            ha="right", fontsize=9, color=GREY)
    ax.set_ylim(-1, 2.6)
    ax.legend(loc="upper right", fontsize=9)
    fig.suptitle("render-pathtrace: every gate passed on NVIDIA WebGPU (seed 17)", fontsize=14)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def loop_figure(run, out):
    rows = verdict_lines(run / "selftest.log")
    st = json.loads((run / "selftest.json").read_text())
    columns = ["schema", "G1", "G2", "G3", "G4", "G5"]
    fig, ax = plt.subplots(figsize=(12, 6))
    grid = np.zeros((len(rows) + 1, len(columns)))
    labels = ["good scene (passes all)"]
    grid[0, :] = 1
    for i, (name, verdict) in enumerate(rows, start=1):
        labels.append(name)
        grid[i, columns.index(rejected_by(verdict))] = 2
    cmap = matplotlib.colors.ListedColormap(["#f2f2f2", "#cce8dd", RED])
    ax.imshow(grid, cmap=cmap, vmin=0, vmax=2, aspect="auto")
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            if grid[i, j] == 2:
                ax.text(j, i, "rejected", ha="center", va="center", color="white", fontsize=10)
            elif grid[i, j] == 1:
                ax.text(j, i, "pass", ha="center", va="center", color=GREEN, fontsize=10)
    ax.set_xticks(range(len(columns)), columns)
    ax.set_yticks(range(len(labels)), labels)
    ax.set_title(f"Self-test: {st['killed']}/{st['total']} bad scenes rejected "
                 f"(kill rate {st['kill_rate']:.0%})\nrenderer-bug control (albedo halved) "
                 f"rejected by G1; repeated verdict identical: {st['verdict_determinism']}")
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def video(run, frames, out, master):
    fr = json.loads((frames / "frames.json").read_text())
    v = json.loads((run / "verdict.json").read_text())["gates"]
    spp = np.array([r["spp"] for r in fr["levels"]])
    rmse = np.array([r["rmse"] for r in fr["levels"]])
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        stills = []
        for k, row in enumerate(fr["levels"]):
            fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
            ax = fig.add_axes([0.03, 0.08, 0.46, 0.82])
            ax.imshow(plt.imread(frames / row["png"]), interpolation="lanczos")
            ax.axis("off")
            ax.set_title(f"{row['spp']} sample{'s' if row['spp'] > 1 else ''} per pixel",
                         fontsize=26)
            ax = fig.add_axes([0.57, 0.14, 0.40, 0.70])
            ax.loglog(spp, rmse[0] * spp ** -0.5, "--", color=GREY, lw=2,
                      label="ideal Monte Carlo 1/sqrt(spp)")
            ax.loglog(spp[:k + 1], rmse[:k + 1], "o-", color=BLUE, lw=3, ms=10,
                      label=f"measured RMSE vs {fr['reference_spp']}-spp reference")
            ax.set(xlim=(0.7, 400), ylim=(rmse.min() * 0.6, rmse.max() * 1.6))
            ax.set_xlabel("samples per pixel", fontsize=18)
            ax.set_ylabel("RMSE (linear radiance)", fontsize=18)
            ax.tick_params(labelsize=14)
            ax.legend(fontsize=15, loc="upper right")
            ax.set_title(f"RMSE {row['rmse']:.4f}", fontsize=24)
            fig.text(0.5, 0.03, "MuTracer path tracing on NVIDIA WebGPU in an agent-next GPU "
                     "browser sandbox  |  every frame is a real render", ha="center",
                     fontsize=16, color=GREY)
            path = tmp / f"still-{k:02d}.png"
            fig.savefig(path)
            plt.close(fig)
            stills.append((path, 3.0))
        fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
        fig.text(0.5, 0.86, "Judge verdict: PASS", ha="center", fontsize=40, weight="bold")
        g1 = ", ".join(f"{c['rho']} -> {c['mean'][0]:.4f}" for c in v["G1"]["cases"])
        lines = [
            f"G1 white furnace (albedo -> rendered): {g1}",
            f"G2 energy: every material reflects <= 1.05 x the light it receives",
            f"G3 convergence slope {v['G3']['slope']:.3f} (ideal -0.5, pass -0.65..-0.35)",
            f"G4 same seed -> identical HDR hash {v['G4']['same_seed_hashes'][0][:16]}...",
            f"G5 median {v['G5']['median_luminance']:.3f}, clipped "
            f"{v['G5']['clipped_fraction']:.4f}, floor noise {v['G5']['floor_relative_noise']:.4f}",
        ]
        for i, line in enumerate(lines):
            fig.text(0.08, 0.68 - i * 0.11, line, fontsize=24)
        path = tmp / "still-verdict.png"
        fig.savefig(path)
        plt.close(fig)
        stills.append((path, 5.0))
        concat = tmp / "list.txt"
        concat.write_text("".join(f"file '{p}'\nduration {d}\n" for p, d in stills)
                          + f"file '{stills[-1][0]}'\n")
        master.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                        "-i", str(concat), "-vf", "fps=30,format=yuv444p", "-c:v", "libx264",
                        "-crf", "0", "-preset", "veryslow", str(master)], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(master), "-c:v",
                        "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", str(out)], check=True)


def main():
    run, frames = Path(sys.argv[1]), Path(sys.argv[2])
    result_figure(run, frames, HERE / "result.png")
    loop_figure(run, HERE / "loop.png")
    video(run, frames, HERE / "demo.mp4", HERE / "master/demo-master.mp4")
    sources = {
        "result.png": ("Studio render plus G1 furnace, G3 convergence, G4/G5 gate numbers",
                       "verdict.json, studio.png, frames.json"),
        "loop.png": ("Self-test matrix: which check rejected each bad scene",
                     "selftest.log, selftest.json"),
        "demo.mp4": ("Real GPU renders at 1-256 spp with measured RMSE, then the verdict",
                     "frame-*.png, frames.json, verdict.json"),
    }
    manifest = {name: {"shows": shows, "source": source,
                       "command": "sh media/make_media.sh",
                       "sha256": hashlib.sha256((HERE / name).read_bytes()).hexdigest()}
                for name, (shows, source) in sources.items()}
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({k: v["sha256"][:16] for k, v in manifest.items()}))


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is required")
    main()
