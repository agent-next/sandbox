#!/usr/bin/env python3
"""make_manifests.py — write media/result.json and media/MANIFEST.json.

Every number is read from the judge outputs under media/judge_runs/
(produced by make_judge_runs.sh — grade verdicts, the traced trajectory,
the mutant verdicts); nothing is hand-typed.  result.json is written via
cookbook/tools/result.py (write_result), so it is schema-checked
(agent-next/result@1) and every referenced path is verified to exist and
match its declared kind.  MANIFEST.json records, for each media file, what
it shows, the command that produced it, its source data and its sha256.

Usage: make_manifests.py [--seed N]      (default seed 42)
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)          # cookbook/physx-drop-test
REPO = os.path.dirname(DEMO)          # cookbook/
REPO = os.path.dirname(REPO)          # repo root
RUNS = os.path.join(MEDIA, "judge_runs")

sys.path.insert(0, os.path.join(REPO, "cookbook", "tools"))
import result as result_tool  # noqa: E402  (cookbook/tools/result.py)

# The README "Ask your agent" prompt (single source: README.md); kept in
# sync with it — the launch card and the README must say the same thing.
ASK_AGENT = (
    "Create a CPU sandbox. In it, clone "
    "https://github.com/agent-next/sandbox and run "
    "`bash cookbook/physx-drop-test/judge/setup.sh` to install the pinned "
    "PhysX toolchain. Then author a USD ASCII scene (`scene.usda`) against "
    "`cookbook/physx-drop-test/SPEC.md`: a static ground with its top at "
    "y = 0, a 0.2 m box of 4 kg dropped from 0.80 m and a 0.1 m-radius "
    "ball of 1 kg dropped from 1.20 m, gravity (0, −9.81, 0), friction "
    "0.60/0.40, restitution 0.50, everything at rest. Iterate with `bash "
    "cookbook/physx-drop-test/judge/grade.sh <your-scene>.usda --json "
    "/tmp/v.json` until every gate passes. Report the final verdict JSON "
    "and kill the sandbox when done."
)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    p = os.path.join(RUNS, path)
    if not os.path.exists(p):
        raise SystemExit(f"make_manifests: missing judge output {p} — "
                         "run media/make_media.sh first")
    return json.load(open(p))


def det(verdict, body, gate):
    return verdict["bodies"][body][gate]["detail"]


def ffprobe_fields(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries",
         "stream=width,height,codec_name,avg_frame_rate:format=duration",
         "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    s = json.loads(out)
    stream = s["streams"][0]
    num, den = stream["avg_frame_rate"].split("/")
    return {
        "width": stream["width"],
        "height": stream["height"],
        "duration_sec": round(float(s["format"]["duration"]), 1),
        "fps": round(float(num) / float(den)),
        "codec": stream["codec_name"],
    }


def build_result(seed, commit, killed, total):
    """The agent-next/result@1 manifest, every number from the verdicts."""
    v = load("verdicts/good.json")
    g2 = det(v, "Box", "G2_freefall")
    g2b = det(v, "Ball", "G2_freefall")
    g3b = det(v, "Box", "G3_contact_time")
    g3l = det(v, "Ball", "G3_contact_time")
    g4b = det(v, "Box", "G4_resting")
    g4l = det(v, "Ball", "G4_resting")
    g5 = det(v, "Ball", "G5_bounce_apex")
    g6b = det(v, "Box", "G6_energy")
    g6l = det(v, "Ball", "G6_energy")
    g7n = len(v["gates"]["G7_contract"]["detail"]["violations"])
    m_box = det(v, "Box", "G1_loads")["mass_kg"]
    m_ball = det(v, "Ball", "G1_loads")["mass_kg"]
    e_mm = max(g4b["error_mm"], g4l["error_mm"])
    grade_cmd = (f"judge/grade.sh examples/good/scene.usda --seed {seed} "
                 f"--json media/judge_runs/verdicts/good.json")
    selftest_cmd = "bash judge/selftest.sh (timed; log in media/judge_runs/selftest.log)"

    gates = [
        {"name": "G1 loads", "pass": v["gates"]["G1_loads"]["passed"],
         "measured": f"2400 steps sampled; masses {m_box:g}/{m_ball:g} kg read back",
         "threshold": "every step sampled; mass within 0.1 % of authored"},
        {"name": "G2 free fall", "pass": v["gates"]["G2_freefall"]["passed"],
         "measured": f"g_fit {g2['g_fit']:g} m/s², max residual "
                     f"{max(g2['max_abs_residual_m'], g2b['max_abs_residual_m']):.4f} m (both bodies)",
         "threshold": "|g_fit − 9.81| ≤ 1 %; residual ≤ 1 % + 0.5 mm"},
        {"name": "G3 contact time", "pass": v["gates"]["G3_contact_time"]["passed"],
         "measured": f"box {g3b['t_contact_sim_s']:.4f} s (Δ {g3b['delta_frames']:g} fr), "
                     f"ball {g3l['t_contact_sim_s']:.4f} s (Δ {g3l['delta_frames']:g} fr)",
         "threshold": "within 1 frame (4.17 ms) of √(2Δh/g)"},
        {"name": "G4 resting", "pass": v["gates"]["G4_resting"]["passed"],
         "measured": f"{g4b['y_final_m']:.3f} m box / {g4l['y_final_m']:.3f} m ball, "
                     f"max error {e_mm:g} mm",
         "threshold": "within 1 mm of the geometric 0.10 m"},
        {"name": "G5 bounce apex", "pass": v["gates"]["G5_bounce_apex"]["passed"],
         "measured": f"{g5['apex_sim_m']:.4f} m ({100 * g5['rel_error']:.2f} %)",
         "threshold": "within 10 % of y_rest + e²Δh = "
                      f"{g5['apex_analytic_m']:.3f} m"},
        {"name": "G6 energy", "pass": v["gates"]["G6_energy"]["passed"],
         "measured": f"max step gain {100 * g6b['max_step_gain_J'] / g6b['E0_J']:.3f} % E₀ (box), "
                     f"{100 * g6l['max_step_gain_J'] / g6l['E0_J']:.3f} % E₀ (ball)",
         "threshold": "no step gain > 0.5 % E₀; E_final ≤ E₀ + 0.5 %"},
        {"name": "G7 contract", "pass": v["gates"]["G7_contract"]["passed"],
         "measured": f"{g7n} violations",
         "threshold": "self-contained dynamic scene: no kinematic flags, "
                      "joints, composition arcs, drives or planted judge outputs"},
    ]
    numbers = [
        {"label": "box first contact", "value": g3b["t_contact_sim_s"],
         "unit": "s", "source": grade_cmd},
        {"label": "box contact error", "value": g3b["delta_frames"],
         "unit": "frames", "source": grade_cmd},
        {"label": "ball first contact", "value": g3l["t_contact_sim_s"],
         "unit": "s", "source": grade_cmd},
        {"label": "ball bounce apex", "value": g5["apex_sim_m"],
         "unit": "m", "source": grade_cmd},
        {"label": "bounce apex error", "value": round(100 * g5["rel_error"], 2),
         "unit": "%", "source": grade_cmd},
        {"label": "fitted gravity (both bodies)", "value": g2["g_fit"],
         "unit": "m/s²", "source": grade_cmd},
        {"label": "box max energy step gain",
         "value": round(100 * g6b["max_step_gain_J"] / g6b["E0_J"], 3),
         "unit": "% E₀", "source": grade_cmd},
        {"label": "mutant kill rate", "value": f"{killed}/{total} = "
         f"{round(100 * killed / total)} %", "unit": "",
         "source": selftest_cmd},
    ]
    headline = (
        f"A 4 kg box dropped from 0.80 m and a 1 kg ball from 1.20 m under "
        f"pinned PhysX land within {g3b['delta_frames']:g} frame of the "
        f"closed-form contact times, the ball rebounds to "
        f"{g5['apex_sim_m']:.4f} m of the analytic "
        f"{g5['apex_analytic_m']:.3f} m, both settle to the geometric "
        f"resting height within {e_mm:g} mm, and mechanical energy "
        f"never gains more than "
        f"{100 * g6b['max_step_gain_J'] / g6b['E0_J']:.3f} % of E₀: all "
        f"{len(v['gates'])} judge gates pass, {killed}/{total} mutants killed."
    )
    return {
        "demo": "physx-drop-test",
        "headline": headline,
        "verdict": "PASS" if v["all_gates_passed"] else "FAIL",
        "gates": gates,
        "numbers": numbers,
        "hero": {
            "kind": "image",
            "path": "media/result.png",
            "caption": "measured PhysX trajectory vs the analytic oracle, "
                       "pass lines drawn on",
        },
        "gallery": [
            {"kind": "image", "path": "media/loop.png",
             "caption": "agent-loop replay and the 11/11 mutant kill matrix"},
            {"kind": "video", "path": "media/demo.mp4",
             "poster": "media/result.png",
             "caption": "43 s: the drop, the bounce, a sped-up real "
                        "self-test run, the verdict"},
        ],
        "launch": {
            "command": "python3 cookbook/physx-drop-test/run.py",
            "ask_agent": ASK_AGENT,
        },
        "receipt": "RECEIPT.md",
        "sandbox_commit": commit,
        "schema": result_tool.SCHEMA_ID,
    }


def file_entry(path, what, command, sources):
    return {
        "what_it_shows": what,
        "command": command,
        "source_data": sources,
        "sha256": sha256(path),
        "size_bytes": os.path.getsize(path),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    commit = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True).stdout.strip()

    muts_desc = load("mutants/mutants/mutants.json")
    total, killed = 0, 0
    for name in muts_desc:
        mv = load(f"mutants/{name}.json")
        total += 1
        if any(not r.get("passed", False) for r in mv.get("gates", {}).values()):
            killed += 1
    if killed != total:
        raise SystemExit(f"make_manifests: {total - killed} mutant(s) "
                         "survived the judge — refusing to write manifests")

    doc = build_result(args.seed, commit, killed, total)
    out = os.path.join(MEDIA, "result.json")
    result_tool.write_result(out, root=DEMO, **doc)
    print(f"[manifests] wrote {out} (kill rate {killed}/{total})")

    grade_cmd = (f"judge/grade.sh examples/good/scene.usda --seed {args.seed} "
                 f"--json media/judge_runs/verdicts/good.json")
    traj_src = ["media/judge_runs/traces/good/traj.npz (judge/simulate.py, "
                "2400 steps at 1/240 s)",
                "media/judge_runs/traces/good/meta.json"]
    files = {
        "result.png": file_entry(
            os.path.join(MEDIA, "result.png"),
            "the measured trajectory against the analytic oracle with the "
            "judge's pass lines drawn on: (a) box free fall + first contact, "
            "(b) ball drop and bounce apex, (c) mechanical energy vs E₀",
            "media/make_figures.py (fig_result)",
            [f"media/judge_runs/verdicts/good.json ({grade_cmd})"] + traj_src),
        "loop.png": file_entry(
            os.path.join(MEDIA, "loop.png"),
            "the agent loop replayed (gates passed per authoring iteration "
            "until PASS) above the mutant × gate kill matrix "
            f"({killed}/{total} killed)",
            "media/make_figures.py (fig_loop)",
            [f"media/judge_runs/mutants/{n}.json (grade.sh, seed {args.seed})"
             for n in sorted(muts_desc)]
            + ["media/judge_runs/mutants/mutants/mutants.json",
               f"media/judge_runs/verdicts/good.json ({grade_cmd})"]),
        "demo.mp4": file_entry(
            os.path.join(MEDIA, "demo.mp4"),
            "the 43 s storyboard video (media/STORYBOARD.md): hook on the "
            "settled result, input→output, per-gate close-ups, a sped-up "
            "real self-test run, the verdict and kill matrix, end card",
            "media/make_video.py (frames → media/master/demo.mp4 crf 0 → "
            "demo.mp4 crf 18)",
            [f"media/judge_runs/verdicts/good.json ({grade_cmd})",
             "media/judge_runs/traces/good/traj.npz",
             "media/judge_runs/mutants/*.json",
             "media/judge_runs/selftest.log + selftest.time",
             "examples/good/scene.usda"]),
        "master/demo.mp4": file_entry(
            os.path.join(MEDIA, "master", "demo.mp4"),
            "the lossless (crf 0) master the web encode is cut from "
            "(git-ignored per DEMO-STANDARD.md; listed for provenance)",
            "media/make_video.py (ffmpeg -crf 0)",
            ["media/frames/ (the rendered frames)"]),
    }
    review = os.path.join(MEDIA, "REVIEW.json")
    if os.path.exists(review):
        files["REVIEW.json"] = file_entry(
            review,
            "the two blind review-panel verdicts on demo.mp4 "
            "(cookbook/tools/video_review_prompt.md) — recorded from the "
            "panel, not machine-regenerated",
            "two vision models, different families, judged demo.mp4 blind",
            ["media/demo.mp4"])

    manifest = {
        "demo": "physx-drop-test",
        "generated_by": "media/make_media.sh",
        "seed": args.seed,
        "sandbox_commit": commit,
        "files": files,
        "video": ffprobe_fields(os.path.join(MEDIA, "demo.mp4")),
        "commands": {
            "judge_setup": "bash judge/setup.sh",
            "selftest": "bash judge/selftest.sh",
            "grade_good": grade_cmd,
            "media": "bash media/make_media.sh",
            "video_gate": "python3 cookbook/tools/video_gate.py media/demo.mp4",
        },
        "environment": {
            "python": platform.python_version(),
            "matplotlib": os.popen(
                f'"{sys.executable}" -c "import matplotlib;'
                'print(matplotlib.__version__)"').read().strip(),
            "numpy": os.popen(
                f'"{sys.executable}" -c "import numpy;print(numpy.'
                '__version__)"').read().strip(),
            "ffmpeg": subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True
            ).stdout.split()[2],
        },
    }
    out = os.path.join(MEDIA, "MANIFEST.json")
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
        f.write("\n")
    print(f"[manifests] wrote {out}")


if __name__ == "__main__":
    main()
