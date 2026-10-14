#!/usr/bin/env python3
"""spice-filter judge engine (stdlib only), called by judge/grade.sh.

Gates per SPEC.md:
  G1 parse      ngspice solves the artifact and an AC sweep of 10 Hz..100 kHz
                at node `out` comes back with data.
  G2 mask       ripple <= 1.0 dB to 1 kHz, <= -40.0 dB for all f >= 10 kHz
                (dB relative to the 10 Hz gain).
  G3 montecarlo >= 50 seeded runs, R +-5 % / C +-10 % uniform; >= 90 % of
                runs must meet the relaxed mask (3.0 dB / -34.0 dB).
  G4 series     every R on E24, every C on E12 (any decade, 0.5 % window).
  G5 sanity     DC gain within 0.1 dB of unity; `out` != `in`.
  oracle        Sallen-Key cascade shape: ngspice must agree with the
                closed-form stage equations within 0.05 dB (ideal-buffer
                H(f), which the netlist's own `E` sources realize exactly),
                AND within 0.5 dB of the same equations when the ideal
                buffers are replaced by a finite-GBW (1 MHz) one-pole
                op-amp macro-model -- so the comparison is not trivially
                exact.  An unrecognized topology FAILS this gate (fail
                closed) unless --allow-unverified is given, in which case
                the verdict carries "unverified": true.

The artifact is graded from a temp copy with the judge's own analysis deck;
the artifact's `.control` block is never executed.
"""

from __future__ import annotations

import json
import math
import re
import random
import subprocess
import sys
import tempfile
from pathlib import Path

FMIN, FMAX = 10.0, 100_000.0
PTS_PER_DECADE = 200
RIPPLE_MAX = 1.0        # dB, passband |dev| to 1 kHz
STOP_MAX = -40.0        # dB, all f >= 10 kHz
MC_RUNS = 100           # >= 50 per spec
MC_R_TOL = 0.05
MC_C_TOL = 0.10
MC_PASS_FRAC = 0.90
MC_RIPPLE_MAX = 3.0
MC_STOP_MAX = -34.0
DC_GAIN_TOL = 0.1       # dB
ORACLE_MAX_DEV = 0.05   # dB, ngspice vs closed form
GBW_MAX_DEV = 0.5       # dB, finite-GBW macro-model vs closed form
GBW_HZ = 1.0e6          # op-amp gain-bandwidth product of the macro-model
GBW_R = 1.0e3           # macro-model internal feedback resistor
SERIES_TOL = 0.005      # 0.5 % window around series values

E24 = [100, 110, 120, 130, 150, 160, 180, 200, 220, 240, 270, 300, 330,
       360, 390, 430, 470, 510, 560, 620, 680, 750, 820, 910]
E12 = [100, 120, 150, 180, 220, 270, 330, 390, 470, 560, 680, 820]

SUFFIX = {"t": 1e12, "g": 1e9, "k": 1e3, "m": 1e-3, "u": 1e-6,
          "n": 1e-9, "p": 1e-12, "f": 1e-15, "meg": 1e6}

FORBIDDEN_DIRECTIVES = (".include", ".inc", ".lib", ".model")
NG_ERROR = re.compile(r"singular matrix|no convergence|couldn't find|"
                      r"syntax error|Error:|ERROR", re.IGNORECASE)


class GateFail(Exception):
    def __init__(self, gate: str, message: str):
        super().__init__(message)
        self.gate, self.message = gate, message


def db(x: float) -> float:
    return 20.0 * math.log10(abs(x)) if abs(x) > 0 else float("-inf")


def spice_value(tok: str) -> float | None:
    """Parse a SPICE value token like 750, 4.7k, 120n, 1meg, 1e-9, 100E-9."""
    m = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)"
                     r"(meg|[tgkmunpf])?", tok, re.IGNORECASE)
    if not m:
        return None
    val = float(m.group(1))
    suf = m.group(2)
    if suf:
        val *= SUFFIX[suf.lower()]
    return val


def parse_netlist(text: str) -> tuple[list[dict], list[str], str]:
    """Return (elements, control_lines, error).

    elements: dicts with type/name/nodes/value for R, C, E, V cards.
    control_lines: the artifact's own .control/.endc body plus .ac cards.
    """
    lines = text.splitlines()
    if not lines or not lines[0].startswith("*"):
        raise GateFail("parse", "first line must be a '*' title comment")
    elements, control, in_control = [], [], False
    for ln in lines[1:]:
        card = ln.split(";")[0].split("$")[0].strip()
        if not card:
            continue
        low = card.lower()
        if card.startswith("+"):
            continue  # continuation of a comment never occurs here
        if low.startswith(".control"):
            in_control = True
            continue
        if low.startswith(".endc"):
            in_control = False
            continue
        if in_control:
            control.append(card)
            continue
        if low.startswith(".end"):
            continue
        if low.startswith(FORBIDDEN_DIRECTIVES):
            raise GateFail("parse", f"forbidden directive {card.split()[0]!r} "
                                    "(judge grades a single offline file)")
        if low.startswith("."):
            continue  # other dot-cards are inert here; judge adds its own deck
        toks = card.split()
        kind = toks[0][0].upper()
        if kind in "RC":
            if len(toks) != 4:
                raise GateFail("parse", f"{toks[0]}: R/C cards must be "
                                        "'<name> <node> <node> <value>'")
            value = spice_value(toks[3])
            if value is None or value <= 0:
                raise GateFail("parse", f"{toks[0]}: unparseable value "
                                        f"{toks[3]!r}")
            elements.append({"kind": kind, "name": toks[0],
                             "nodes": toks[1:3], "value": value})
        elif kind == "E":
            if len(toks) != 6:
                raise GateFail("parse", f"{toks[0]}: E cards must be "
                                        "'<name> <out+> <out-> <in+> <in-> <gain>'")
            gain = spice_value(toks[5])
            if gain is None:
                raise GateFail("parse", f"{toks[0]}: unparseable gain {toks[5]!r}")
            elements.append({"kind": kind, "name": toks[0],
                             "nodes": toks[1:5], "value": gain})
        elif kind == "V":
            has_ac = "ac" in (t.lower() for t in toks[3:])
            elements.append({"kind": kind, "name": toks[0],
                             "nodes": toks[1:3], "value": 1.0,
                             "has_ac": has_ac})
        # other element kinds (L, I, X, ...) are left to ngspice; the mask
        # and series gates still apply to every R and C.
    return elements, control, ""


def build_deck(source_lines: list[str], raw_name: str) -> str:
    """Copy of the artifact with the judge's analysis deck appended."""
    keep = []
    in_control = False
    for ln in source_lines:
        card = ln.strip().lower()
        if card.startswith(".control"):
            in_control = True
            continue
        if card.startswith(".endc"):
            in_control = False
            continue
        if in_control or card.startswith(".end") or card.startswith(".ac"):
            continue
        keep.append(ln)
    return "\n".join(keep) + f"""
.control
set filetype=ascii
op
ac dec {PTS_PER_DECADE} {FMIN:g} {FMAX:g}
write {raw_name} v(out)
quit
.endc
.end
"""


def run_ngspice(deck: str, workdir: Path, raw_name: str = "out.raw") -> tuple[dict, str]:
    """Run ngspice -b on deck; return ({freq: complex}, combined output)."""
    deck_path = workdir / "deck.cir"
    raw_path = workdir / raw_name
    deck_path.write_text(deck)
    try:
        proc = subprocess.run(["ngspice", "-b", str(deck_path)],
                              cwd=workdir, capture_output=True, text=True,
                              timeout=180)
    except FileNotFoundError:
        raise GateFail("parse", "ngspice not on PATH; run judge/setup.sh")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise GateFail("parse", f"ngspice exited {proc.returncode}: "
                                f"{out.strip().splitlines()[-1] if out.strip() else 'no output'}")
    if NG_ERROR.search(out):
        raise GateFail("parse", "ngspice reported: " +
                       NG_ERROR.search(out).group(0))
    return parse_raw(raw_path), out


def parse_raw(path: Path) -> dict:
    """Parse an ngspice ASCII raw file -> {freq_hz: complex}."""
    lines = path.read_text().splitlines()
    nvars = int(next(l.split(":")[1] for l in lines
                     if l.startswith("No. Variables")))
    i = lines.index("Values:")
    nums = []
    for ln in lines[i + 1:]:
        for tok in ln.split():
            nums.extend(float(x) for x in tok.split(","))
    per = 1 + 2 * nvars
    data = {}
    for k in range(0, len(nums), per):
        rec = nums[k:k + per]
        if len(rec) < per:
            break
        freq = rec[1]
        data[freq] = complex(rec[-2], rec[-1])  # v(out) is the last variable
    if len(data) < 100:
        raise GateFail("parse", f"AC sweep returned {len(data)} points "
                                "(need >= 100)")
    return data


def mask_metrics(sweep: dict) -> tuple[float, float, float]:
    """(gain at 10 Hz in dB, max passband deviation dB, max stopband gain dB)."""
    ref = db(sweep[FMIN])
    ripple = max(abs(db(v) - ref) for f, v in sweep.items() if f <= 1000.0)
    stop = max(db(v) for f, v in sweep.items() if f >= 10_000.0)
    return ref, ripple, stop


def extract_stages(elements: list[dict]) -> list[dict] | None:
    """Extract the Sallen-Key cascade stage table, or None if the shape
    does not match (then the analytic oracle is skipped with a warning)."""
    vsources = [e for e in elements if e["kind"] == "V"]
    esources = [e for e in elements if e["kind"] == "E"]
    if len(vsources) != 1 or len(esources) != 2:
        return None
    v = vsources[0]
    if sorted(v["nodes"]) != ["0", "in"] or not v.get("has_ac"):
        return None
    stages = []
    for e in esources:
        out_node, out_gnd, p, p_gnd = e["nodes"]
        gain = e["value"]
        if out_gnd != "0" or p_gnd != "0" or gain != 1:
            return None
        cg = [c for c in elements if c["kind"] == "C"
              and sorted(c["nodes"]) == sorted([p, "0"])]
        rb = [r for r in elements if r["kind"] == "R"
              and p in r["nodes"]]
        if len(cg) != 1 or len(rb) != 1:
            return None
        rb = rb[0]
        q = rb["nodes"][0] if rb["nodes"][1] == p else rb["nodes"][1]
        cf = [c for c in elements if c["kind"] == "C"
              and sorted(c["nodes"]) == sorted([q, out_node])]
        ra = [r for r in elements if r["kind"] == "R"
              and q in r["nodes"] and r is not rb]
        if len(cf) != 1 or len(ra) != 1:
            return None
        ra = ra[0]
        r_in = ra["nodes"][0] if ra["nodes"][1] == q else ra["nodes"][1]
        stages.append({"in": r_in, "out": out_node, "p": p,
                       "ename": e["name"],
                       "Ra": ra["value"], "Rb": rb["value"],
                       "Cf": cf[0]["value"], "Cg": cg[0]["value"]})
    # chain them: in -> ... -> out
    first = [s for s in stages if s["in"] == "in"]
    if len(first) != 1:
        return None
    a = first[0]
    b = [s for s in stages if s is not a][0]
    if b["in"] != a["out"] or b["out"] != "out":
        return None
    return [a, b]


def analytic_db(stages: list[dict], f: float) -> float:
    h = 1.0 + 0j
    for s in stages:
        w = 2j * math.pi * f
        h /= (w * w * s["Ra"] * s["Rb"] * s["Cf"] * s["Cg"]
              + w * s["Cg"] * (s["Ra"] + s["Rb"]) + 1.0)
    return db(h)


def run_gbw_macromodel(source_lines: list[str], stages: list[dict],
                       elements: list[dict]) -> dict:
    """Re-simulate the netlist with every ideal buffer (`E` source) replaced
    by a one-pole finite-GBW op-amp macro-model: a VCCS integrating the
    buffer input onto an internal RC node (R=GBW_R, C set so that
    R*C*GBW_HZ gives pole = GBW_HZ) buffered by a unity VCVS.  Returns the
    AC sweep at node `out` (same grid as the nominal sweep).  For the
    good Sallen-Key cascade the response then sits ~0.15 dB off the ideal
    closed form at the band edges -- the comparison is no longer trivially
    exact while still checking the same math.
    """
    enames = {s["ename"] for s in stages}
    cb = 1.0 / (2.0 * math.pi * GBW_HZ * GBW_R)
    keep, in_control = [], False
    for ln in source_lines:
        card = ln.strip().lower()
        if card.startswith(".control"):
            in_control = True
            continue
        if card.startswith(".endc"):
            in_control = False
            continue
        if in_control or card.startswith(".end") or card.startswith(".ac"):
            continue
        # match element names case-sensitively as written (they were
        # extracted from the same lines)
        if ln.split() and ln.split()[0] in enames:
            continue  # the ideal buffer is replaced below
        keep.append(ln)
    deck = "\n".join(keep) + "\n"
    for i, s in enumerate(stages, 1):
        # VCCS + RC set the GBW pole; VCCS control-node order (0, p) gives
        # the non-inverting sign of the unity buffer it replaces.
        deck += (f"Gx{i} mx{i} 0 0 {s['p']} {1.0 / GBW_R!r}\n"
                 f"Rxd{i} mx{i} 0 {GBW_R:g}\n"
                 f"Cxd{i} mx{i} 0 {cb!r}\n"
                 f"Exd{i} {s['out']} 0 mx{i} 0 1\n")
    deck += (f".control\nset filetype=ascii\nop\n"
             f"ac dec {PTS_PER_DECADE} {FMIN:g} {FMAX:g}\n"
             f"write gbw.raw v(out)\nquit\n.endc\n.end\n")
    with tempfile.TemporaryDirectory(prefix="spicefilter-gbw-") as td:
        return run_ngspice(deck, Path(td), "gbw.raw")[0]


def perturbed_source(source_lines: list[str], elements: list[dict],
                     rng: random.Random) -> list[str]:
    """Rewrite every R/C value token with a tolerance-scaled float."""
    factors = {}
    for e in elements:
        if e["kind"] in "RC":
            tol = MC_R_TOL if e["kind"] == "R" else MC_C_TOL
            factors[e["name"]] = e["value"] * rng.uniform(1 - tol, 1 + tol)
    out = []
    in_control = False
    for ln in source_lines:
        card = ln.strip()
        low = card.lower()
        if low.startswith(".control"):
            in_control = True
        elif low.startswith(".endc"):
            in_control = False
        if not in_control and card and not card.startswith(("*", ".", "+")):
            toks = card.split()
            if toks[0] in factors:
                new = list(toks)
                new[3] = repr(factors[toks[0]])
                ln = " ".join(new)
        out.append(ln)
    return out


def grade(artifact: Path, seed: int, allow_unverified: bool = False) -> dict:
    """Run every gate; on failure the verdict keeps the gates already run."""
    gates: dict = {}
    try:
        _grade(artifact, seed, gates, allow_unverified)
    except GateFail as exc:
        return {"artifact": str(artifact), "passed": False,
                "failed_gate": exc.gate, "reason": exc.message,
                "gates": gates}
    verdict = {"artifact": str(artifact), "seed": seed, "passed": True,
               "gates": gates}
    if gates.get("analytic", {}).get("unverified"):
        # --allow-unverified opt-in: the other gates passed, but the
        # closed-form oracle did not run -- mark it so this can never be
        # presented as a verified pass.
        verdict["unverified"] = True
    return verdict


def _grade(artifact: Path, seed: int, gates: dict,
           allow_unverified: bool = False) -> None:
    source = artifact.read_text()
    if len(source) > 64 * 1024:
        raise GateFail("parse", "artifact larger than 64 KiB")

    elements, control_lines, _ = parse_netlist(source)

    # -- G1 parse/DC ------------------------------------------------------
    ac_ok = False
    for card in control_lines:
        toks = card.lower().split()
        if toks and toks[0] in ("ac", ".ac"):
            if len(toks) < 5:
                continue
            mode, pts, f1, f2 = toks[1], int(float(toks[2])), \
                spice_value(toks[3]), spice_value(toks[4])
            span_ok = f1 <= FMIN and f2 >= FMAX
            density_ok = (mode == "dec" and pts >= 20) or \
                         (mode == "oct" and pts >= 60) or \
                         (mode == "lin" and pts >= 400)
            ac_ok = span_ok and density_ok
    if not ac_ok:
        raise GateFail("parse", "artifact has no 'ac dec >=20 10 100k' "
                                "analysis of its own")
    source_lines = source.splitlines()
    with tempfile.TemporaryDirectory(prefix="spicefilter-") as td:
        workdir = Path(td)
        # artifact graded from a copy: everything below runs in the tempdir
        sweep, simlog = run_ngspice(build_deck(source_lines, "out.raw"),
                                    workdir)
    ref, ripple, stop = mask_metrics(sweep)
    gates["parse"] = {"passed": True,
                      "points": len(sweep),
                      "f_grid": f"{FMIN:g}..{FMAX:g} {PTS_PER_DECADE}/dec"}

    # -- G5 sanity ---------------------------------------------------------
    names = {n for e in elements for n in e["nodes"]}
    if abs(ref) > DC_GAIN_TOL:
        raise GateFail("sanity", f"gain at 10 Hz is {ref:.3f} dB; expected "
                                 f"0 +- {DC_GAIN_TOL} dB")
    if not {"out", "in", "0"} <= names:
        raise GateFail("sanity", "nodes 'in', 'out' and '0' must all appear")
    if "out" == "in":
        raise GateFail("sanity", "'out' and 'in' are the same node")
    gates["sanity"] = {"passed": True, "dc_gain_db": round(ref, 4)}

    # -- G2 mask -----------------------------------------------------------
    mask_ok = ripple <= RIPPLE_MAX and stop <= STOP_MAX
    gates["mask"] = {"passed": mask_ok,
                     "ripple_db": round(ripple, 3),
                     "rule": f"ripple <= {RIPPLE_MAX} dB to 1 kHz",
                     "stopband_max_db": round(stop, 3),
                     "rule2": f"gain <= {STOP_MAX} dB for f >= 10 kHz"}
    if not mask_ok:
        raise GateFail("mask", f"ripple {ripple:.3f} dB / stopband "
                               f"{stop:.3f} dB violate the mask "
                               f"({RIPPLE_MAX} dB / {STOP_MAX} dB)")

    # -- oracle: closed form vs simulation --------------------------------
    # Fail closed: a topology the judge cannot verify against independent
    # math is not accepted as passed.  --allow-unverified downgrades the
    # failure to a marked UNVERIFIED verdict (still pass=false).
    stages = extract_stages(elements)
    if stages is None:
        if allow_unverified:
            gates["analytic"] = {
                "passed": False, "unverified": True,
                "note": "topology not recognised by the closed-form "
                        "oracle; graded on the other gates only because "
                        "--allow-unverified was given",
            }
        else:
            raise GateFail("analytic",
                           "topology not recognised by the closed-form "
                           "oracle; the judge refuses to pass a design it "
                           "cannot verify against independent math "
                           "(re-run with --allow-unverified to grade it "
                           "on the other gates only)")
    else:
        dev = max(abs(db(v) - analytic_db(stages, f))
                  for f, v in sweep.items())
        # Second, non-ideal case: rebuild the same netlist with the ideal
        # buffers replaced by a 1 MHz-GBW one-pole op-amp macro-model and
        # check it still tracks the closed form (within a looser bound) --
        # an oracle comparison that is trivially exact proves nothing.
        gbw_sweep = run_gbw_macromodel(source_lines, stages, elements)
        gbw_dev = max(abs(db(v) - analytic_db(stages, f))
                      for f, v in gbw_sweep.items())
        ok = dev <= ORACLE_MAX_DEV and gbw_dev <= GBW_MAX_DEV
        gates["analytic"] = {
            "passed": ok,
            "max_deviation_db": round(dev, 5),
            "rule": f"ideal op-amp: <= {ORACLE_MAX_DEV} dB everywhere",
            "gbw_deviation_db": round(gbw_dev, 5),
            "rule2": f"1 MHz-GBW macro-model: <= {GBW_MAX_DEV} dB everywhere",
            "gbw_hz": GBW_HZ,
        }
        if not ok:
            bad = (f"ideal {dev:.3f} dB (limit {ORACLE_MAX_DEV})"
                   if dev > ORACLE_MAX_DEV else
                   f"1 MHz-GBW macro-model {gbw_dev:.3f} dB "
                   f"(limit {GBW_MAX_DEV})")
            raise GateFail("analytic", f"simulation differs from the "
                                       f"closed-form response by {bad}")

    # -- G4 series ---------------------------------------------------------
    off = []
    for e in elements:
        if e["kind"] not in "RC":
            continue
        series = E24 if e["kind"] == "R" else E12
        # normalize into [100, 1000): the E-series mantissa decade
        m = e["value"] / 10 ** (math.floor(math.log10(e["value"])) - 2)
        best = min(series, key=lambda s: abs(s - m) / s)
        if abs(best - m) / best > SERIES_TOL:
            off.append({"name": e["name"], "value": e["value"],
                        "nearest": best})
    gates["series"] = {"passed": not off, "off_series": off,
                       "rule": "R on E24, C on E12 (0.5 % window)"}
    if off:
        raise GateFail("series", "values not on series: " +
                               ", ".join(f"{o['name']}={o['value']:g} "
                                         f"(nearest {o['nearest']})"
                                         for o in off))

    # -- G3 Monte-Carlo ------------------------------------------------------
    rng = random.Random(seed)
    passed_runs, results = 0, []
    with tempfile.TemporaryDirectory(prefix="spicefilter-mc-") as td:
        workdir = Path(td)
        for i in range(MC_RUNS):
            lines = perturbed_source(source_lines, elements, rng)
            sweep_i, _ = run_ngspice(build_deck(lines, f"mc{i}.raw"),
                                     workdir, f"mc{i}.raw")
            _, rip, stp = mask_metrics(sweep_i)
            ok = rip <= MC_RIPPLE_MAX and stp <= MC_STOP_MAX
            results.append({"run": i, "ripple_db": round(rip, 3),
                            "stopband_db": round(stp, 3), "ok": ok})
            passed_runs += ok
    frac = passed_runs / MC_RUNS
    gates["montecarlo"] = {
        "passed": frac >= MC_PASS_FRAC,
        "runs": MC_RUNS, "seed": seed,
        "tolerances": f"R +-{MC_R_TOL:.0%} / C +-{MC_C_TOL:.0%} uniform",
        "pass_fraction": round(frac, 3),
        "rule": f">= {MC_PASS_FRAC:.0%} meet {MC_RIPPLE_MAX} dB / "
                f"{MC_STOP_MAX} dB relaxed mask",
        "worst_ripple_db": round(max(r["ripple_db"] for r in results), 3),
        "worst_stopband_db": round(max(r["stopband_db"] for r in results), 3),
    }
    if frac < MC_PASS_FRAC:
        raise GateFail("montecarlo", f"only {passed_runs}/{MC_RUNS} runs "
                                     f"met the relaxed mask")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", type=Path)
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--allow-unverified", action="store_true",
                    help="grade an unrecognized topology on the other gates "
                         "only; the verdict is still marked UNVERIFIED and "
                         "pass=false unless it fails elsewhere")
    args = ap.parse_args()
    try:
        verdict = grade(args.artifact, args.seed, args.allow_unverified)
        rc = 0 if verdict["passed"] else 1
    except OSError as exc:
        verdict = {"artifact": str(args.artifact), "passed": False,
                   "failed_gate": "io", "reason": str(exc)}
        rc = 1
    text = json.dumps(verdict, indent=2)
    if args.json:
        args.json.write_text(text)
    print(text)
    return rc


if __name__ == "__main__":
    sys.exit(main())
