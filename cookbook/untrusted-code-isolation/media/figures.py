#!/usr/bin/env python3
"""Draw the untrusted-code-isolation media from real judge outputs.

Inputs (all produced by run.py --artifacts + the repo):
  verdict.json   the judge's verdict for the known-good runner
  selftest.log   the judge self-test (mutant kill list, kill rate)
  ../judge/policy.json  the runtime policy (bounds)

Outputs (written next to this script):
  result.png  measured containment vs the judge's numeric bounds
  loop.png    self-test kill rate per mutant + the gate pass vector
  master/frame_%06d.png  lossless video frames (gitignored)
  MANIFEST.json  what each file shows, its command, source data, sha256

Figures show measured numbers only; every value plotted is read from the
verdict JSON or the self-test log of a real run.
"""

import hashlib
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))

# Okabe-Ito colour-blind-safe palette.
BLUE, SKY, GREEN, VERMILLION, YELLOW = ("#0072B2", "#56B4E9", "#009E73",
                                        "#D55E00", "#E69F00")
INK = "#222222"

GATE_ORDER = ("fork_bomb", "memory_balloon", "infinite_loop", "disk_filler",
              "huge_stdout", "sleep_forever")
EFFECT_ORDER = ("read_shadow", "write_outside", "outbound_socket",
                "background_daemon")
GATE_LABEL = {
    "fork_bomb": "fork bomb", "memory_balloon": "memory balloon",
    "infinite_loop": "CPU spinner", "disk_filler": "disk filler",
    "huge_stdout": "stdout flood", "sleep_forever": "eternal sleep",
    "read_shadow": "/etc/shadow read", "write_outside": "write outside",
    "outbound_socket": "outbound socket", "background_daemon": "background daemon",
}
EFFECT_TEXT = {
    "read_shadow": "no shadow entry in stdout",
    "write_outside": "canary byte-identical",
    "outbound_socket": "no connection reached the probe",
    "background_daemon": "no process survived the run",
}


def die(msg):
    sys.stderr.write("figures.py: %s\n" % msg)
    raise SystemExit(1)


def load(artifacts):
    with open(os.path.join(artifacts, "verdict.json")) as fh:
        verdict = json.load(fh)
    with open(os.path.join(HERE, "..", "judge", "policy.json")) as fh:
        policy = json.load(fh)
    log_path = os.path.join(artifacts, "selftest.log")
    if not os.path.isfile(log_path):
        die("no selftest.log in %s (run run.py --artifacts %s)"
            % (artifacts, artifacts))
    with open(log_path) as fh:
        selftest = fh.read()
    return verdict, policy, selftest


def numeric_rows(verdict, policy):
    """(label, measured, bound, unit text) for the numerically bounded gates."""
    runs, measured = verdict.get("runs", {}), verdict.get("measured", {})
    effects = verdict.get("gates", {}).get("containment", {}).get("effects", {})
    wall = float(policy["wall_s"])
    rows = [
        ("fork bomb",
         measured.get("fork_bomb_peak_proc_delta"),
         2.0 * float(policy["nproc"]), "processes above baseline"),
        ("memory balloon",
         (measured.get("memory_balloon_maxrss_kb") or 0) / 1024.0,
         512.0, "peak RSS, MiB"),
        ("CPU spinner",
         measured.get("infinite_loop_judge_wall_s"),
         0.85 * wall, "judge-measured wall, s"),
        ("disk filler",
         (effects.get("largest_file_bytes")
          or runs.get("disk_filler", {}).get("largest_file_bytes") or 0)
         / (1024.0 * 1024.0),
         1.10 * float(policy["fsize_bytes"]) / (1024.0 * 1024.0),
         "largest file left, MiB"),
        ("stdout flood",
         (runs.get("huge_stdout", {}).get("stdout_bytes") or 0)
         / (1024.0 * 1024.0),
         1.05 * float(policy["output_cap_bytes"]) / (1024.0 * 1024.0),
         "stdout captured, MiB"),
        ("eternal sleep",
         measured.get("sleep_forever_runner_wall_s"),
         2.5 * wall, "runner wall, s"),
    ]
    out = []
    for label, got, bound, unit in rows:
        if got is None:
            die("verdict JSON lacks the measured value for %r; regenerate "
                "from a run of the current judge" % label)
        out.append((label, float(got), float(bound), unit))
    return out


def parse_selftest(text):
    """(good_pass, [(mutant, killed, gate)...], kill_rate_str) from the log."""
    good = re.search(r"selftest: known-good: PASS", text) is not None
    mutants = []
    for match in re.finditer(
            r"selftest: mutant ([\w-]+): (killed|SURVIVED)(?: \(gate: ([\w,./-]+)\))?",
            text):
        mutants.append((match.group(1), match.group(2) == "killed",
                        match.group(3) or "-"))
    rate = re.search(r"selftest: kill rate: (\d+/\d+ = \d+%)", text)
    return good, mutants, (rate.group(1) if rate else "?")


def draw_result(fig, verdict, policy, rows, stage=1.0, show_effects=True):
    """The containment figure. `stage` animates bar growth (0..1)."""
    fig.clf()
    grid = fig.add_gridspec(1, 5)
    ax = fig.add_subplot(grid[0, :3])
    labels = [r[0] for r in rows][::-1]
    ratios = [min(r[1] / r[2], 1.6) * stage for r in rows][::-1]
    ys = range(len(rows))
    passed = [r[1] <= r[2] for r in rows][::-1]
    ax.barh(list(ys), ratios, height=0.62,
            color=[BLUE if p else VERMILLION for p in passed])
    ax.axvline(1.0, color=VERMILLION, lw=2.5, ls="--")
    ax.text(1.0, len(rows) - 0.28, " judge bound", color=VERMILLION,
            fontsize=15, va="center", weight="bold")
    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels, fontsize=17)
    ax.set_xlim(0, 1.6)
    ax.set_xticks([0, 0.5, 1.0, 1.5])
    ax.set_xlabel("measured effect / judge bound  (pass at ≤ 1.0)",
                  fontsize=15, color=INK)
    for y, (label, got, bound, unit), r, p in zip(ys, rows[::-1], ratios,
                                                  passed):
        ax.text(min(r + 0.03, 1.58), y,
                "%.2g / %.2g %s" % (got, bound, unit), fontsize=12.5,
                va="center", color=INK,
                ha="right" if r > 1.45 else "left")
    ax.set_title("Hostile snippets: measured containment vs the judge's bounds",
                 fontsize=19, color=INK, weight="bold", loc="left", pad=14)
    ax.tick_params(colors=INK)

    ax2 = fig.add_subplot(grid[0, 3:])
    ax2.axis("off")
    if show_effects:
        rows_txt = []
        for name in EFFECT_ORDER:
            run = verdict.get("runs", {}).get(name, {})
            ok = bool(run.get("pass"))
            rows_txt.append("%-20s %-7s %-10s %s"
                            % (GATE_LABEL[name], run.get("verdict", "?"),
                               run.get("reason", "?"),
                               "pass" if ok else "FAIL"))
        body = "\n".join(rows_txt)
        ax2.text(0.0, 0.97, "Effect gates (binary)", fontsize=17,
                 weight="bold", color=INK, va="top")
        ax2.text(0.0, 0.90, "snippet             verdict reason     effect",
                 fontsize=12.5, color="#666666", va="top", family="monospace")
        ax2.text(0.0, 0.83, body, fontsize=13.5, color=INK, va="top",
                 family="monospace", linespacing=1.75)
        for i, name in enumerate(EFFECT_ORDER):
            ok = bool(verdict.get("runs", {}).get(name, {}).get("pass"))
            ax2.text(-0.06, 0.83 - 0.062 * i, "✔" if ok else "✘",
                     fontsize=15, color=GREEN if ok else VERMILLION,
                     va="top", weight="bold", transform=ax2.transAxes,
                     clip_on=False)
        ax2.text(0.0, 0.30, "\n".join(EFFECT_TEXT[name] for name in
                                      EFFECT_ORDER),
                 fontsize=11.5, color="#666666", va="top", style="italic",
                 linespacing=1.9)
    return fig


def draw_loop(fig, verdict, good, mutants, rate, stage=1.0):
    fig.clf()
    grid = fig.add_gridspec(1, 2, width_ratios=[3, 2])
    ax = fig.add_subplot(grid[0, 0])
    names = [m[0].replace("_", "\n") for m in mutants]
    vals = [(1.0 if m[1] else 0.0) * stage for m in mutants]
    ax.bar(range(len(mutants)), vals, color=[BLUE if m[1] else VERMILLION
                                             for m in mutants])
    ax.axhline(0.9, color=VERMILLION, lw=2.5, ls="--")
    ax.text(len(mutants) - 0.4, 0.935, "required kill rate ≥ 90%",
            color=VERMILLION, fontsize=14, ha="right", weight="bold")
    ax.set_xticks(range(len(mutants)))
    ax.set_xticklabels(names, fontsize=9.5, rotation=55, ha="right")
    ax.set_ylim(0, 1.12)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["survived", "killed"], fontsize=13)
    ax.set_title("Self-test: single-edit mutants of the good runner "
                 "(kill rate %s)" % rate, fontsize=16, color=INK,
                 weight="bold", loc="left", pad=10)
    ax.tick_params(colors=INK)

    ax2 = fig.add_subplot(grid[0, 1])
    ax2.axis("off")
    gates = sorted(verdict.get("gates", {}).items())
    ax2.text(0.0, 0.97, "Judge gates, known-good runner",
             fontsize=16, weight="bold", color=INK, va="top")
    for i, (name, g) in enumerate(gates):
        ok = bool(g.get("pass")) and stage >= 1.0
        ax2.text(0.02, 0.86 - 0.115 * i, "✔" if ok else "✘",
                 fontsize=18, color=GREEN if ok else VERMILLION, va="top",
                 weight="bold")
        ax2.text(0.14, 0.865 - 0.115 * i, name, fontsize=16, color=INK,
                 va="top", family="monospace")
        note = ""
        if name == "containment" and g.get("total"):
            note = "%d/%d contained" % (g.get("contained", 0), g.get("total"))
        if name == "benign" and g.get("total"):
            note = "%d/%d exact" % (g.get("matched", 0), g.get("total"))
        if note:
            ax2.text(0.62, 0.865 - 0.115 * i, note, fontsize=13,
                     color="#666666", va="top")
    ax2.text(0.0, 0.13, "known-good: %s" % ("PASS" if good else "FAIL"),
             fontsize=14, color=INK, va="top", family="monospace")
    return fig


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def write_manifest(artifacts, extra):
    files = {
        "result.png": {
            "shows": "Measured containment of the 6 numerically bounded "
                     "hostile snippets against the judge's bounds (pass "
                     "line at 1.0), plus the 4 binary effect gates.",
            "command": "media/make_media.sh %s" % artifacts,
            "source_data": ["verdict.json (runs, measured, "
                            "gates.containment.effects)",
                            "judge/policy.json (bounds)"],
            "sha256": sha256_file(os.path.join(HERE, "result.png"))},
        "loop.png": {
            "shows": "Self-test kill results for the 10 single-edit mutants "
                     "with the required 90% kill-rate line, and the five "
                     "gate results for the known-good runner.",
            "command": "media/make_media.sh %s" % artifacts,
            "source_data": ["selftest.log (mutant kill lines, kill rate)",
                            "verdict.json (gates)"],
            "sha256": sha256_file(os.path.join(HERE, "loop.png"))},
        "demo.mp4": {
            "shows": "Step-through: containment bars growing to their "
                     "measured ratios against the pass line, the effect "
                     "gates, the mutant kill rate and the final verdict.",
            "command": "media/make_media.sh %s" % artifacts,
            "source_data": ["verdict.json", "selftest.log",
                            "judge/policy.json"],
            "sha256": sha256_file(os.path.join(HERE, "demo.mp4"))},
    }
    files.update(extra)
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as fh:
        json.dump({"demo": "untrusted-code-isolation",
                   "generated_by": "media/make_media.sh",
                   "artifacts_from": artifacts,
                   "files": files}, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main():
    artifacts = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "stills"
    verdict, policy, selftest = load(artifacts)
    rows = numeric_rows(verdict, policy)
    good, mutants, rate = parse_selftest(selftest)

    fig = plt.figure(figsize=(9.6, 5.4))
    if mode == "stills":
        draw_result(fig, verdict, policy, rows)
        fig.savefig(os.path.join(HERE, "result.png"), dpi=200,
                    facecolor="white")
        draw_loop(fig, verdict, good, mutants, rate)
        fig.savefig(os.path.join(HERE, "loop.png"), dpi=200,
                    facecolor="white")
        plt.close(fig)
    elif mode == "manifest":
        write_manifest(artifacts, {})
    elif mode == "frames":
        master = os.path.join(HERE, "master")
        os.makedirs(master, exist_ok=True)
        fps = 30
        scenes = [("title", 3.5 * fps), ("bars", 7 * fps),
                  ("effects", 6 * fps), ("kill", 8 * fps), ("verdict",
                                                            5 * fps)]
        n = 0
        for scene, frames in scenes:
            for i in range(int(frames)):
                t = i / float(frames)
                fig.clf()
                if scene == "title":
                    fig.text(0.5, 0.60, "Untrusted code isolation",
                             ha="center", fontsize=34, weight="bold",
                             color=INK)
                    fig.text(0.5, 0.47, "10 hostile snippets · one "
                             "runner · a judge that reads the process "
                             "table", ha="center", fontsize=17, color=INK)
                    fig.text(0.5, 0.36, "run.py --ref sbx/demo-"
                             "untrusted-code-isolation", ha="center",
                             fontsize=13, color="#666666", family="monospace")
                    ease = min(1.0, t * 3)
                    fig.text(0.5, 0.22, "measured on a real agent-next "
                             "sandbox" + "." * int(3 * ease),
                             ha="center", fontsize=12, color="#999999")
                elif scene == "bars":
                    draw_result(fig, verdict, policy, rows, stage=t,
                                show_effects=t > 0.7)
                elif scene == "effects":
                    draw_result(fig, verdict, policy, rows, stage=1.0,
                                show_effects=True)
                elif scene == "kill":
                    draw_loop(fig, verdict, good, mutants, rate,
                              stage=min(1.0, t * 2.2))
                else:
                    ok = all(g.get("pass")
                             for g in verdict.get("gates", {}).values())
                    fig.text(0.5, 0.62, "VERDICT: " + ("PASS" if ok
                                                        else "FAIL"),
                             ha="center", fontsize=44, weight="bold",
                             color=GREEN if ok else VERMILLION)
                    fig.text(0.5, 0.48, "kill rate %s · %d/%d hostile "
                             "contained · %d/%d benign exact"
                             % (rate,
                                verdict["gates"]["containment"]["contained"],
                                verdict["gates"]["containment"]["total"],
                                verdict["gates"]["benign"]["matched"],
                                verdict["gates"]["benign"]["total"]),
                             ha="center", fontsize=18, color=INK)
                    fig.text(0.5, 0.38, "judge/ checksums unchanged: %s"
                             % verdict.get("judge_intact"), ha="center",
                             fontsize=15, color="#666666")
                n += 1
                fig.savefig(os.path.join(master, "frame_%06d.png" % n),
                            dpi=200, facecolor="white")
        plt.close(fig)
        print("frames: %d" % n)
    else:
        die("unknown mode %r (stills|frames)" % mode)


if __name__ == "__main__":
    main()
