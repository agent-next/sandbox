#!/usr/bin/env python3
"""Backfill cookbook/<demo>/media/result.json from committed numbers.

For every demo listed in DEMOS the script builds the manifest fields
declared in cookbook/tools/result.schema.json:

- numbers carry a (file, needle) citation — the script finds the first
  line of that file under the demo dir containing both the needle and
  the printed value, and records it as "<file>:<line>", so every number
  on the result card / gallery / storyboard traces to a committed
  receipt line;
- the ask_agent prompt is lifted verbatim from the README's "Ask your
  agent" blockquote (or inline "**Ask your agent:** \"...\"" form);
- sandbox_commit is the last commit that touched the demo's RECEIPT.md (the
  numbers' source), so regenerating is stable;
- hero is the committed media/result.png; the gallery adds media/loop.png
  and media/demo.mp4.

Every manifest is written via result.write_result(..., root=<demo dir>)
— so it must already satisfy schema, path-existence and magic-byte
checks — and then re-checked with result.check_manifest.

Usage: python3 cookbook/tools/backfill_results.py
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import result  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def ask_agent_prompt(demo_dir):
    """The README 'Ask your agent' prompt, verbatim."""
    lines = (demo_dir / "README.md").read_text().splitlines()
    start = next((i for i, l in enumerate(lines)
                  if "ask your agent" in l.lower()), None)
    if start is None:
        raise ValueError(f"{demo_dir}: README has no 'Ask your agent'")
    if '"' in lines[start]:
        rest = "\n".join(lines[start:])
        m = re.search(r'"(.*?)"', rest, re.S)
        if m:
            return m.group(1).strip()
    quote, started = [], False
    for line in lines[start + 1:]:
        s = line.strip()
        if s.startswith(">"):
            quote.append(s[1:].lstrip())
            started = True
        elif started:
            break
    if not quote:
        raise ValueError(f"{demo_dir}: no 'Ask your agent' quote found")
    return "\n".join(quote).strip()


def cite(demo_dir, fname, needle, value):
    """Return '<file>:<line>' for the first line containing both the
    needle and the printed value; raise if there is no such line."""
    text = (demo_dir / fname).read_text()
    for n, line in enumerate(text.splitlines(), 1):
        if needle in line and str(value) in line:
            return f"{fname}:{n}"
    raise ValueError(
        f"{demo_dir.name}: no line in {fname} contains both "
        f"{needle!r} and {value!r}")


def number(demo_dir, label, value, unit, fname, needle):
    return {"label": label, "value": value, "unit": unit,
            "source": cite(demo_dir, fname, needle, value)}


def demo_commit(demo_dir):
    out = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", str(demo_dir / "RECEIPT.md")],
        capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0 or not out.stdout.strip():
        raise ValueError(f"{demo_dir.name}: no commit found")
    return out.stdout.strip()


def gallery(captions):
    return [
        {"kind": "image", "path": "media/loop.png", "caption": captions[0]},
        {"kind": "video", "path": "media/demo.mp4",
         "poster": "media/result.png", "caption": captions[1]},
    ]


def build(demo_dir, spec):
    numbers = [number(demo_dir, n["label"], n["value"], n["unit"],
                      n["cite"][0], n["cite"][1]) for n in spec["numbers"]]
    return {
        "demo": demo_dir.name,
        "headline": spec["headline"],
        "verdict": spec.get("verdict", "PASS"),
        "gates": spec["gates"],
        "numbers": numbers,
        "hero": {"kind": "image", "path": "media/result.png",
                 "caption": spec["hero_caption"]},
        "gallery": gallery(spec["gallery_captions"]),
        "launch": {
            "command": f"python3 cookbook/{demo_dir.name}/run.py",
            "ask_agent": ask_agent_prompt(demo_dir),
        },
        "receipt": "RECEIPT.md",
        "sandbox_commit": demo_commit(demo_dir),
    }


DEMOS = {
    "cfd-openfoam": {
        "headline": "The agent's OpenFOAM cases reproduce the analytic "
                    "Poiseuille parabola to L2 = 0.0043 and Ghia's Re=100 "
                    "cavity data to 0.0033/0.0073 max error, with 10/10 "
                    "mutants killed.",
        "hero_caption": "Poiseuille centreline vs analytic parabola, cavity "
                        "centreline vs Ghia 1982, mesh convergence order, "
                        "and the cavity |U| field.",
        "gallery_captions": [
            "replayed agent loop + self-test kill rate (10/10)",
            "cavity flow developing over pseudo-time from a real icoFoam run",
        ],
        "gates": [
            {"name": "Mesh quality", "pass": True,
             "measured": "checkMesh exit 0; max non-orthogonality 0.0; "
                         "max skewness 1.78e-14",
             "threshold": "non-orthogonality <= 70 deg; skewness <= 4"},
            {"name": "Solver convergence", "pass": True,
             "measured": "final residuals Ux 1.86e-14, Uy 3.56e-12, "
                         "p 7.79e-07; continuity error 2.06e-11",
             "threshold": "initial residuals < 1e-5; continuity < 1e-8"},
            {"name": "Poiseuille accuracy", "pass": True,
             "measured": "L2 0.004253; Re 99.66; dp/dx rel err 0.0189",
             "threshold": "L2 <= 0.02; |Re-100|/100 <= 0.10; "
                          "dp/dx rel err <= 0.15"},
            {"name": "Poiseuille mesh convergence", "pass": True,
             "measured": "observed orders 2.15, 1.91 (avg 2.03)",
             "threshold": ">= 1.5 on both refinement steps"},
            {"name": "Cavity vs Ghia et al. 1982", "pass": True,
             "measured": "max u err 0.0033; max v err 0.0073",
             "threshold": "<= 0.02 (lid-speed units)"},
        ],
        "numbers": [
            {"label": "Poiseuille L2 profile error", "value": 0.004253,
             "unit": "", "cite": ("RECEIPT.md", "Poiseuille L2 profile error")},
            {"label": "Poiseuille dp/dx relative error", "value": 0.018916,
             "unit": "", "cite": ("RECEIPT.md", "Poiseuille dp/dx rel. err")},
            {"label": "Poiseuille Re measured", "value": 99.6646,
             "unit": "", "cite": ("RECEIPT.md", "Poiseuille Re measured")},
            {"label": "Mesh-convergence orders", "value": "2.153, 1.907",
             "unit": "", "cite": ("RECEIPT.md", "Mesh-convergence orders")},
            {"label": "Cavity max u error vs Ghia", "value": 0.003261,
             "unit": "", "cite": ("RECEIPT.md", "Cavity max u err vs Ghia")},
            {"label": "Cavity max v error vs Ghia", "value": 0.007316,
             "unit": "", "cite": ("RECEIPT.md", "Cavity max v err vs Ghia")},
            {"label": "mutant kill rate", "value": "10/10 (100%)",
             "unit": "", "cite": ("RECEIPT.md", "mutants killed")},
        ],
    },
    "fea-calculix": {
        "headline": "The agent's cantilever beam holds sigma 138.2 <= 166.7 "
                    "MPa and tip deflection 7.72 <= 10 mm at 5652 g while "
                    "matching Euler-Bernoulli within 3 %.",
        "hero_caption": "Deformed mesh coloured by von Mises (allowable on "
                        "the colour bar), mesh convergence, and the "
                        "Euler-Bernoulli comparison.",
        "gallery_captions": [
            "agent-loop replay and the mutant x gate self-test matrix",
            "the real displacement field ramped 0-1000 N, then each "
            "mutant's failing gate",
        ],
        "gates": [
            {"name": "verification", "pass": True,
             "measured": "reference beam vs Euler-Bernoulli: deflection "
                         "+0.41 %, stress -0.74 %",
             "threshold": "<= 3 %"},
            {"name": "convergence", "pass": True,
             "measured": "mesh 4 vs 2 mm: deflection 0.23 %, stress 0.50 %",
             "threshold": "<= 2 %"},
            {"name": "spec_limits", "pass": True,
             "measured": "sigma 138.2 MPa; tip deflection 7.72 mm",
             "threshold": "sigma <= 166.7 MPa; delta <= L/100 = 10 mm"},
        ],
        "numbers": [
            {"label": "sigma_wall", "value": 138.241, "unit": "MPa",
             "cite": ("RECEIPT.md", "sigma_wall")},
            {"label": "tip deflection", "value": 7.7221, "unit": "mm",
             "cite": ("RECEIPT.md", "tip deflection")},
            {"label": "mass", "value": 5652.0, "unit": "g",
             "cite": ("RECEIPT.md", "| mass |")},
            {"label": "EB deflection error (ref beam)", "value": "+0.41",
             "unit": "%", "cite": ("RECEIPT.md", "EB deflection error")},
            {"label": "EB stress error (ref beam)", "value": "-0.74",
             "unit": "%", "cite": ("RECEIPT.md", "EB stress error")},
            {"label": "mesh convergence (deflection / stress)",
             "value": "0.23 % / 0.50 %", "unit": "",
             "cite": ("RECEIPT.md", "mesh convergence")},
            {"label": "mutant kill rate", "value": "9/9 (100%)",
             "unit": "", "cite": ("RECEIPT.md", "kill rate")},
        ],
    },
    "spice-filter": {
        "headline": "The agent's 4th-order active low-pass filter meets "
                    "the mask with 0.096 dB ripple and -56.14 dB stopband, "
                    "and 100 % of the seeded Monte-Carlo runs pass.",
        "hero_caption": "Bode magnitude vs. spec mask.",
        "gallery_captions": [
            "agent-loop replay & self-test kill rate",
            "ideal and GBW-limited sweeps drawn against the mask",
        ],
        "gates": [
            {"name": "parse", "pass": True,
             "measured": "801 points on the 10 Hz-100 kHz grid",
             "threshold": ">= 100 points; op solves"},
            {"name": "sanity", "pass": True,
             "measured": "dc_gain -0.0 dB",
             "threshold": "op point solves; DC gain sane"},
            {"name": "mask", "pass": True,
             "measured": "ripple 0.096 dB; stopband max -56.14 dB",
             "threshold": "ripple <= 1.0 dB to 1 kHz; <= -40 dB from 10 kHz"},
            {"name": "analytic", "pass": True,
             "measured": "max deviation 0.0 dB; gbw deviation 0.15 dB",
             "threshold": "closed-form cross-check within tolerance"},
            {"name": "series", "pass": True,
             "measured": "off_series: []",
             "threshold": "every R on E24, every C on E12"},
            {"name": "montecarlo", "pass": True,
             "measured": "pass_fraction 1.0 over 100 runs (seed 20261014)",
             "threshold": ">= 0.90 under relaxed mask"},
        ],
        "numbers": [
            {"label": "passband ripple", "value": 0.096, "unit": "dB",
             "cite": ("RECEIPT.md", "ripple_db")},
            {"label": "stopband max", "value": -56.14, "unit": "dB",
             "cite": ("RECEIPT.md", "stopband_max_db")},
            {"label": "analytic max deviation", "value": 0.0, "unit": "dB",
             "cite": ("RECEIPT.md", "max_deviation_db")},
            {"label": "Monte-Carlo runs", "value": 100, "unit": "",
             "cite": ("RECEIPT.md", '"runs": 100')},
            {"label": "Monte-Carlo pass fraction", "value": 1.0, "unit": "",
             "cite": ("RECEIPT.md", "pass_fraction")},
            {"label": "Monte-Carlo worst ripple", "value": 0.757,
             "unit": "dB", "cite": ("RECEIPT.md", "worst_ripple_db")},
            {"label": "Monte-Carlo worst stopband", "value": -53.193,
             "unit": "dB", "cite": ("RECEIPT.md", "worst_stopband_db")},
            {"label": "mutant kill rate", "value": "9/9 = 100 %",
             "unit": "", "cite": ("RECEIPT.md", "kill rate")},
        ],
    },
    "firmware-qemu": {
        "headline": "The agent's bare-metal Cortex-M3 firmware boots in "
                    "QEMU and answers all 46 scripted UART shell commands "
                    "byte-exact: 8/8 gates, 14/14 mutants killed.",
        "hero_caption": "The judged session: the real UART transcript of "
                        "the good firmware in QEMU beside the 8-gate table "
                        "with measured values.",
        "gallery_captions": [
            "mutant x gate matrix: known-good plus 14 mutants against "
            "all 8 gates",
            "the real captured UART session, then the crc-poly mutant "
            "diverging from the oracle",
        ],
        "gates": [
            {"name": "build_clean", "pass": True,
             "measured": "make exit 0, no diagnostics",
             "threshold": "gcc -Wall -Werror exit 0 and stderr empty"},
            {"name": "elf_ok", "pass": True,
             "measured": "entry 0x205 is inside .text",
             "threshold": "e_machine ARM; ET_EXEC; entry within .text"},
            {"name": "maps_ok", "pass": True,
             "measured": ".text+.rodata = 2224 B",
             "threshold": "<= 8192 B"},
            {"name": "boot", "pass": True,
             "measured": "banner within 10 s",
             "threshold": "banner <= BOOT_S (10 s)"},
            {"name": "shell", "pass": True,
             "measured": "46/46 exact responses",
             "threshold": "every response byte-exact within SHELL_S (30 s)"},
            {"name": "crc_oracle", "pass": True,
             "measured": "15/15 match zlib.crc32",
             "threshold": "all 15 buffers match exactly"},
            {"name": "no_hardfault", "pass": True,
             "measured": "no fault strings in UART output",
             "threshold": "0 fault-string occurrences"},
            {"name": "judge_intact", "pass": True,
             "measured": "judge checksum unchanged",
             "threshold": "judge/ sha256 identical before and after"},
        ],
        "numbers": [
            {"label": "gates passed", "value": "8/8", "unit": "",
             "cite": ("RECEIPT.md", "PASS 8/8 gates")},
            {"label": "shell responses byte-exact", "value": "46/46",
             "unit": "", "cite": ("README.md", "46/46")},
            {"label": "CRC-32 buffers matching zlib.crc32",
             "value": "15/15", "unit": "", "cite": ("README.md", "15/15")},
            {"label": ".text+.rodata", "value": 2224, "unit": "B",
             "cite": ("README.md", "2224 B")},
            {"label": "mutants killed", "value": "14/14", "unit": "",
             "cite": ("RECEIPT.md", "mutants killed")},
            {"label": "behavioural kill rate", "value": 100, "unit": "%",
             "cite": ("RECEIPT.md", "behavioural kill rate")},
        ],
    },
    "plc-st": {
        "headline": "The agent's IEC 61131-3 tank controller keeps the "
                    "level inside its safe band through all 8 scenarios "
                    "and latches the emergency stop within one scan; 6/6 "
                    "mutants are killed.",
        "hero_caption": "Max/min level per scenario for the known-good "
                        "controller; design cap (94 cm), high switch "
                        "(85 cm) and dry band (15 cm) drawn as reference "
                        "lines.",
        "gallery_captions": [
            "which scenario catches each of the six single-edit mutants",
            "the level trace of the judged controller under fault scenarios",
        ],
        "gates": [
            {"name": "cycle", "pass": True,
             "measured": "level 15.0-85.0 cm over 12000 scans",
             "threshold": ">= 2 autocycles; level <= 94; no pump < 15"},
            {"name": "overflow_guard", "pass": True,
             "measured": "level 70.0-88.0 cm over 12000 scans",
             "threshold": "level <= 94 with high_ls forced 0"},
            {"name": "dry_run", "pass": True,
             "measured": "level 10.0-85.0 cm over 12000 scans",
             "threshold": "pump never on below 15"},
            {"name": "dry_interlock_fault", "pass": True,
             "measured": "level 15.0-85.0 cm over 12000 scans",
             "threshold": "no pump < 15 with low_ls forced 0"},
            {"name": "lowsw_false_trip", "pass": True,
             "measured": "level 62.5-85.0 cm over 12000 scans",
             "threshold": "pump off within 200 scans of the trip"},
            {"name": "estop", "pass": True,
             "measured": "level 40.0-48.0 cm over 12000 scans",
             "threshold": "all actuators off within 1 scan and latched"},
            {"name": "recovery", "pass": True,
             "measured": "level 15.0-85.0 cm over 12000 scans",
             "threshold": "idle during estop; resumes autocycle after"},
            {"name": "random_faults", "pass": True,
             "measured": "level 40.0-55.2 cm over 12000 scans",
             "threshold": "no pump < 15; never pump+inlet; level <= 94"},
        ],
        "numbers": [
            {"label": "scenarios passed", "value": "8/8", "unit": "",
             "cite": ("RECEIPT.md", "scenarios passed")},
            {"label": "max level over all scenarios", "value": 88.02,
             "unit": "cm",
             "cite": ("RECEIPT.md", "max level over all scenarios")},
            {"label": "min level over all scenarios", "value": 10.00,
             "unit": "cm",
             "cite": ("RECEIPT.md", "min level over all scenarios")},
            {"label": "mutants killed", "value": "6/6", "unit": "",
             "cite": ("RECEIPT.md", "known-bad (mutants)")},
            {"label": "kill rate", "value": 100, "unit": "%",
             "cite": ("RECEIPT.md", "| kill rate |")},
            {"label": "grade wall time", "value": 5, "unit": "s",
             "cite": ("RECEIPT.md", "grade wall")},
        ],
    },
    "gpu-kernel": {
        "headline": "The agent's fused Triton softmax passes all 10 "
                    "correctness cases against torch.softmax (worst error "
                    "1.19e-07, limit 1e-5) and compiles to sm_80 and sm_90 "
                    "cubins.",
        "hero_caption": "Correctness of the judged kernel across the case "
                        "grid, and the kernel-vs-eager timing on the GPU "
                        "slice.",
        "gallery_captions": [
            "agent loop and the 11-mutant self-test matrix",
            "the demo video built from report.json and the GPU run log",
        ],
        "gates": [
            {"name": "structure", "pass": True,
             "measured": "softmax/KERNEL/SIGNATURE/CONSTEXPRS contract; "
                         "no delegation names",
             "threshold": "<= 64 KiB, byte-compiles, contract exact"},
            {"name": "device-compile", "pass": True,
             "measured": "cubins produced for sm_80 and sm_90",
             "threshold": "both compiles succeed"},
            {"name": "correctness", "pass": True,
             "measured": "10/10 cases; worst max_abs 1.19e-07, rowsum "
                         "1.19e-07, shift 1.05e-06",
             "threshold": "max_abs <= 1e-5; rowsum <= 1e-4; shift <= 1e-5"},
            {"name": "judge_intact", "pass": True,
             "measured": "judge/ sha256 unchanged",
             "threshold": "identical before and after"},
        ],
        "numbers": [
            {"label": "correctness cases passed", "value": 10,
             "unit": "cases", "cite": ("RECEIPT.md", "all 10 cases")},
            {"label": "worst max-abs error vs torch.softmax",
             "value": 1.19e-07, "unit": "",
             "cite": ("RECEIPT.md", "worst max-abs error")},
            {"label": "worst row-sum error", "value": 1.19e-07, "unit": "",
             "cite": ("RECEIPT.md", "worst row-sum error")},
            {"label": "shift-invariance error", "value": 1.05e-06,
             "unit": "", "cite": ("RECEIPT.md", "1.05e-06")},
            {"label": "kernel time", "value": 0.075, "unit": "ms",
             "cite": ("RECEIPT.md", "kernel 0.075 ms")},
            {"label": "eager time", "value": 0.079, "unit": "ms",
             "cite": ("RECEIPT.md", "eager 0.079 ms")},
            {"label": "speedup vs eager", "value": "x1.05", "unit": "",
             "cite": ("RECEIPT.md", "speedup x1.05")},
            {"label": "mutant kill rate", "value": "11/11 = 100%",
             "unit": "", "cite": ("RECEIPT.md", "kill rate: 11/11")},
        ],
    },
    "sim-engine-arena": {
        "headline": "The agent's MuJoCo port lands all four scenarios on "
                    "the closed-form oracles — drop contact 0.4406 s, "
                    "slide accel +0.04 %, pendulum 2.0073 s — and matches "
                    "the reference port pointwise.",
        "hero_caption": "Measured drop/contact vs free fall, slide/stick "
                        "vs analytic displacement, pendulum vs the "
                        "SPEC-period guide, oracle error normalized to "
                        "each limit.",
        "gallery_captions": [
            "the agent loop to a passing port",
            "the simulator's own 3D render of the graded trajectories",
        ],
        "gates": [
            {"name": "structure", "pass": True,
             "measured": "sim.py contract; no oracle literals",
             "threshold": "<= 96 KiB, byte-compiles, no literal within "
                          "2 % of an oracle value"},
            {"name": "run", "pass": True,
             "measured": "all four CSVs written; exit 0",
             "threshold": "exit 0 within 900 s"},
            {"name": "csv-shape", "pass": True,
             "measured": "headers and row counts per spec for all "
                         "scenarios",
             "threshold": "columns exact; finite floats; t monotone"},
            {"name": "oracle: drop", "pass": True,
             "measured": "t_contact 0.4406 s (+0.11 %)",
             "threshold": "0.4401 s +/- 3 %"},
            {"name": "oracle: incline_stick", "pass": True,
             "measured": "travel 1.8 mm",
             "threshold": "< 20 mm (stick)"},
            {"name": "oracle: incline_slide", "pass": True,
             "measured": "accel 1.6082 m/s^2 (+0.04 %)",
             "threshold": "1.6088 m/s^2 +/- 5 %"},
            {"name": "oracle: pendulum", "pass": True,
             "measured": "period 2.0073 s (+0.00 %)",
             "threshold": "2.0073 s +/- 2 %"},
            {"name": "agreement", "pass": True,
             "measured": "max pointwise deviation 0.0 on all scenarios",
             "threshold": "<= 5 % of per-scenario scale"},
        ],
        "numbers": [
            {"label": "drop contact time", "value": 0.4406, "unit": "s",
             "cite": ("RECEIPT.md", "drop t_contact")},
            {"label": "incline_stick travel", "value": 1.8, "unit": "mm",
             "cite": ("RECEIPT.md", "incline_stick travel")},
            {"label": "incline_slide acceleration", "value": 1.6082,
             "unit": "m/s^2",
             "cite": ("RECEIPT.md", "incline_slide accel")},
            {"label": "pendulum period", "value": 2.0073, "unit": "s",
             "cite": ("RECEIPT.md", "pendulum period")},
            {"label": "mutant kill rate", "value": "8/8 = 100 %",
             "unit": "", "cite": ("RECEIPT.md", "kill rate")},
        ],
    },
}


def main():
    failures = []
    for name, spec in DEMOS.items():
        demo_dir = ROOT / "cookbook" / name
        try:
            fields = build(demo_dir, spec)
            out = demo_dir / "media" / "result.json"
            result.write_result(out, root=demo_dir, **fields)
            errors = result.check_manifest(out, root=demo_dir)
            if errors:
                failures.append((name, errors))
            else:
                print(f"wrote {out.relative_to(ROOT)}")
        except (OSError, ValueError) as e:
            failures.append((name, [str(e)]))
    for name, errors in failures:
        for e in errors:
            print(f"FAIL {name}: {e}", file=sys.stderr)
    if failures:
        return 1
    print(f"{len(DEMOS)} manifests written and checked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
