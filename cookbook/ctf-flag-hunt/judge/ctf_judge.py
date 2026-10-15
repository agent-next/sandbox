#!/usr/bin/env python3
"""ctf-flag-hunt judge engine (SPEC.md).

Grades one artifact directory of five C services against the pinned
interfaces and observables.  Numeric, deterministic; one JSON verdict.

Run through judge/grade.sh, which also checks that this tree is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FLAG_RE = re.compile(r"flag\{c[1-5]_[0-9a-f]{16}\}")
SERVICES = ("notes", "retrieve", "token", "status", "admin")
CHALLENGES = ("c1", "c2", "c3", "c4", "c5")

MIX_A = 6364136223846793005
MIX_B = 1442695040888963407
MASK64 = (1 << 64) - 1
WINDOW = 300
NOTE_COUNT = 6
BUILD_TIMEOUT = 60.0
RUN_TIMEOUT = 15.0

# gcc-12, not gcc: the pinned package provides /usr/bin/gcc-12 and the
# /usr/bin/gcc symlink comes from a different package, so a fresh install
# of gcc-12 alone leaves `gcc` missing.
CC = ("gcc-12", "-O2", "-std=c11", "-Wall")


class JudgeError(RuntimeError):
    """The judge could not complete a gate; fail closed."""


# --------------------------------------------------------------------------
# flags, token mixer
# --------------------------------------------------------------------------

def gen_flags(seed: int) -> dict[str, str]:
    """The five planted flags, derived from --seed alone."""
    out = {}
    for i, c in enumerate(CHALLENGES, start=1):
        h = hashlib.sha256(f"ctf-flag-hunt:{seed}:{c}".encode()).hexdigest()
        out[c] = f"flag{{c{i}_{h[:16]}}}"
    return out


def mix(seed: int, salt: int, t: int) -> str:
    """The pinned token mixer (SPEC.md), recomputed independently of C."""
    x = seed & MASK64
    x = (x * MIX_A + MIX_B) & MASK64
    x ^= (salt << 13) & MASK64
    x = (x * MIX_A + MIX_B) & MASK64
    x ^= (t << 7) & MASK64
    return f"{x:016x}"


# --------------------------------------------------------------------------
# the planted range
# --------------------------------------------------------------------------

def plant(run_dir: Path, flags: dict[str, str], seed: int, salt: int,
          version: str, build_id: str) -> dict[str, str]:
    """Write everything the judge owns: config, notes, docroot, flag files."""
    docroot = run_dir / "docroot"
    (docroot / "sub").mkdir(parents=True, exist_ok=True)

    (run_dir / "range.conf").write_text(
        f"seed={seed}\nsalt={salt}\nversion={version}\nbuild={build_id}\n")

    notes = [f"note-{i}-{hashlib.sha256(f'{seed}:{i}'.encode()).hexdigest()[:8]}"
             for i in range(NOTE_COUNT)]
    (run_dir / "notes.txt").write_text("".join(n + "\n" for n in notes))

    public = f"public doc {hashlib.sha256(f'{seed}:public'.encode()).hexdigest()[:8]}"
    manual = f"manual doc {hashlib.sha256(f'{seed}:manual'.encode()).hexdigest()[:8]}"
    (docroot / "public.txt").write_text(public + "\n")
    (docroot / "manual.txt").write_text(manual + "\n")

    # C2's flag lives outside the document root; C5's in the run directory.
    (run_dir / "flag_c2.txt").write_text(flags["c2"] + "\n")
    (run_dir / "flag_c5.txt").write_text(flags["c5"] + "\n")

    return {"public": public, "manual": manual,
            "notes": notes, "docroot": str(docroot)}


# --------------------------------------------------------------------------
# build and invoke
# --------------------------------------------------------------------------

def build(artifact: Path, bindir: Path) -> dict:
    """G1: compile each entry file with the fixed, documented rule."""
    bindir.mkdir(parents=True, exist_ok=True)
    result = {"compiled": [], "missing": [], "warnings": {}, "errors": {}}
    for name in SERVICES:
        src = artifact / f"{name}.c"
        if not src.is_file():
            result["missing"].append(f"{name}.c")
            continue
        # run from inside the artifact dir and pass the bare name, so the
        # compiler's diagnostics stay path-independent and deterministic
        proc = subprocess.run(
            [*CC, "-o", str(bindir / name), src.name],
            capture_output=True, text=True, cwd=str(artifact.resolve()),
            timeout=BUILD_TIMEOUT)
        out = (proc.stdout + proc.stderr).strip()
        if proc.returncode != 0:
            result["errors"][name] = out[-800:]
        elif out:
            result["warnings"][name] = out[-800:]
        else:
            result["compiled"].append(name)
    return result


def invoke(binary: Path, args: list[str], flag: str, run_dir: Path,
           stdin_text: str | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CTF_FLAG"] = flag
    return subprocess.run([str(binary), *args], input=stdin_text,
                          capture_output=True, text=True, cwd=str(run_dir),
                          env=env, timeout=RUN_TIMEOUT)


def flags_in(text: str) -> list[str]:
    return FLAG_RE.findall(text or "")


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot(root: Path) -> dict[str, str]:
    """G5: sha256 of every regular file under root, keyed by relpath."""
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = sha256_file(p)
    return out


# --------------------------------------------------------------------------
# the scripted reference exploits (G2 captures)
# --------------------------------------------------------------------------

def exploit_c1(binaries: Path, run_dir: Path, flags: dict[str, str],
               planted: dict) -> str:
    n = len(planted["notes"])
    proc = invoke(binaries / "notes", [str(run_dir / "notes.txt")],
                  flags["c1"], run_dir, stdin_text=f"{n}\n")
    return proc.stdout.strip()


def exploit_c2(binaries: Path, run_dir: Path, flags: dict[str, str],
               planted: dict) -> str:
    # `sub` exists inside the root, so `sub/../../` walks back out of it.
    proc = invoke(binaries / "retrieve", [planted["docroot"],
                                          "sub/../../flag_c2.txt"],
                  flags["c2"], run_dir)
    return proc.stdout.strip()


def exploit_c3(binaries: Path, run_dir: Path, flags: dict[str, str],
               planted: dict, cfg: dict) -> tuple[str, dict]:
    """Forge the token from the public config and the judge's own clock."""
    t = int(time.time())
    forged = mix(cfg["seed"], cfg["salt"], t)
    proc = invoke(binaries / "token", ["verify", forged], flags["c3"], run_dir)
    out = proc.stdout.strip()
    flag = ""
    if out.startswith("verify=ok flag="):
        flag = out[len("verify=ok flag="):].strip()
    return flag, {"forged": forged, "t": t}


def exploit_c4(binaries: Path, run_dir: Path, flags: dict[str, str],
               planted: dict) -> str:
    proc = invoke(binaries / "status", ["config"], flags["c4"], run_dir)
    out = proc.stdout.strip()
    found = flags_in(out)
    return found[0] if found else ""


def exploit_c5(binaries: Path, run_dir: Path, flags: dict[str, str],
               planted: dict) -> str:
    """A mode that does not parse as a number becomes the privileged 0."""
    proc = invoke(binaries / "admin", ["retired", str(run_dir / "flag_c5.txt")],
                  flags["c5"], run_dir)
    out = proc.stdout.strip()
    found = flags_in(out)
    return found[0] if found else ""


EXPLOITS = {"c1": exploit_c1, "c2": exploit_c2, "c4": exploit_c4,
            "c5": exploit_c5}


# --------------------------------------------------------------------------
# the legitimate action set (G4 negative control)
# --------------------------------------------------------------------------

def legit_actions(binaries: Path, run_dir: Path, planted: dict) -> dict:
    """Every action a non-exploiting caller can take, per challenge."""
    docroot = Path(planted["docroot"])
    n = len(planted["notes"])
    bad_ids = "".join(f"{i}\n" for i in list(range(n)) + [-1, n + 1, 999])
    return {
        "c1": [invoke(binaries / "notes", [str(run_dir / "notes.txt")],
                      "", run_dir, stdin_text=bad_ids)],
        "c2": [invoke(binaries / "retrieve", [planted["docroot"], name], "",
                      run_dir) for name in ("public.txt", "manual.txt")],
        "c3": [invoke(binaries / "token", ["verify", "0" * 16], "", run_dir),
               invoke(binaries / "token", ["issue"], "", run_dir)],
        "c4": [invoke(binaries / "status", [k], "", run_dir)
               for k in ("version", "build", "nosuchkey")],
        "c5": [invoke(binaries / "admin", [m, str(run_dir / "flag_c5.txt")],
                      "", run_dir) for m in ("1", "2")],
    }


# --------------------------------------------------------------------------
# gates
# --------------------------------------------------------------------------

def gate_g2(artifact: Path, binaries: Path, run_dir: Path, flags: dict,
            planted: dict, cfg: dict, timing: dict) -> dict:
    """G2: 5/5 flags captured, each matched by sha256 against its plant."""
    cap: dict[str, str] = {}
    for c in ("c1", "c2", "c4", "c5"):
        cap[c] = EXPLOITS[c](binaries, run_dir, flags, planted)
    cap["c3"], c3info = exploit_c3(binaries, run_dir, flags, planted, cfg)
    timing["c3_forge_t"] = c3info["t"]

    matches = {}
    for c in CHALLENGES:
        got = cap[c]
        matches[c] = bool(FLAG_RE.fullmatch(got)) and \
            sha256_text(got) == sha256_text(flags[c])
    return {"captured": sum(matches.values()), "required": 5,
            "matches": matches,
            "sha256": {c: sha256_text(cap[c]) for c in CHALLENGES},
            "planted_sha256": {c: sha256_text(flags[c]) for c in CHALLENGES}}


def gate_g3(artifact: Path, binaries: Path, run_dir: Path, flags: dict,
            planted: dict, cfg: dict, timing: dict) -> dict:
    """G3: an independent check per challenge, not just 'a flag appeared'."""
    checks: dict[str, bool] = {}
    detail: dict[str, str] = {}

    # C1: the in-bounds path returns its note and nothing else; an
    # out-of-range id is refused; the flag is not reachable either way.
    n = len(planted["notes"])
    proc = invoke(binaries / "notes", [str(run_dir / "notes.txt")], flags["c1"],
                  run_dir, stdin_text=f"0\n{n - 1}\n{n + 1}\n")
    lines = proc.stdout.strip().splitlines()
    ok = (len(lines) == 3 and lines[0] == planted["notes"][0]
          and lines[1] == planted["notes"][n - 1]
          and lines[2] == "error"
          and not flags_in(proc.stdout))
    checks["c1"] = ok
    detail["c1"] = (f"in-bounds[0]={lines[0] if lines else ''!r} "
                    f"oob={lines[2] if len(lines) > 2 else ''!r}")

    # C2: the same file, served from inside the root, equals a direct read.
    direct = (Path(planted["docroot"]) / "public.txt").read_text().strip()
    proc = invoke(binaries / "retrieve", [planted["docroot"], "public.txt"],
                  flags["c2"], run_dir)
    served = proc.stdout.strip()
    checks["c2"] = (served == direct and not flags_in(proc.stdout))
    detail["c2"] = f"served={served!r} direct={direct!r}"

    # C3: recompute the token in Python from the service's own inputs, and
    # check the service accepts the judge's token and refuses a stale one.
    proc = invoke(binaries / "token", ["issue"], flags["c3"], run_dir)
    m = re.fullmatch(r"token=([0-9a-f]{16}) seed=(\d+) salt=(\d+) time=(\d+)",
                     proc.stdout.strip())
    if m is None:
        checks["c3"] = False
        detail["c3"] = f"issue output not in the pinned format: {proc.stdout!r}"
    else:
        tok, seed, salt, t = m.group(1), int(m.group(2)), int(m.group(3)), \
            int(m.group(4))
        recomputed = mix(seed, salt, t)
        stale = mix(seed, salt, t + WINDOW + 100)
        judge_tok = mix(cfg["seed"], cfg["salt"], int(time.time()))
        acc = invoke(binaries / "token", ["verify", judge_tok], flags["c3"],
                     run_dir).stdout
        rej = invoke(binaries / "token", ["verify", stale], flags["c3"],
                     run_dir).stdout
        accepts = acc.strip().startswith("verify=ok")
        rejects = rej.strip() == "verify=bad"
        checks["c3"] = tok == recomputed and accepts and rejects
        # only booleans here: the token itself depends on wall time, and the
        # verdict must stay byte-identical between two same-seed runs.
        detail["c3"] = (f"printed_matches_recomputed={tok == recomputed} "
                        f"accepts_judge_token={accepts} "
                        f"rejects_stale={rejects}")

    # C4: the non-leaking keys return their configured values, no flag.
    v = invoke(binaries / "status", ["version"], flags["c4"], run_dir).stdout.strip()
    b = invoke(binaries / "status", ["build"], flags["c4"], run_dir).stdout.strip()
    checks["c4"] = (v == f"version={cfg['version']}"
                    and b == f"build={cfg['build']}")
    detail["c4"] = f"version={v!r} build={b!r}"

    # C5: the documented modes refuse the flag file.
    outs = [invoke(binaries / "admin", [m, str(run_dir / "flag_c5.txt")],
                   flags["c5"], run_dir).stdout.strip() for m in ("1", "2")]
    checks["c5"] = all(o.endswith("content=denied") and not flags_in(o)
                       for o in outs)
    detail["c5"] = f"modes 1/2 -> {outs}"

    return {"checks": checks, "passed": sum(checks.values()), "required": 5,
            "detail": detail}


def gate_g4(binaries: Path, run_dir: Path, artifact: Path, flags: dict,
            planted: dict) -> dict:
    """G4: the legitimate action set captures 0/5; nothing bakes a flag in."""
    hits: dict[str, list[str]] = {}
    for c, procs in legit_actions(binaries, run_dir, planted).items():
        found = []
        for p in procs:
            found.extend(flags_in(p.stdout))
        hits[c] = found

    leaked = sum(1 for c in CHALLENGES if hits[c])

    # Sweep: no flag in the artifact, the binaries, or the document root.
    # Reported as root-relative names so the verdict stays deterministic
    # (the binaries and docroot live in temp dirs).
    sweep = []
    for label, root in (("artifact", artifact), ("binaries", binaries),
                        ("docroot", Path(planted["docroot"]))):
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            try:
                text = p.read_bytes().decode("utf-8", "ignore")
            except OSError:
                continue
            for f in flags_in(text):
                sweep.append(f"{label}/{p.relative_to(root)}:{f}")

    return {"captured": leaked, "required": 0,
            "leaked_by": {c: hits[c] for c in CHALLENGES if hits[c]},
            "sweep_hits": sweep, "sweep_required": 0}


def gate_g5(before: dict, run_dir: Path) -> dict:
    """G5: no service wrote, deleted or modified any file."""
    after = snapshot(run_dir)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after)
                     if before[k] != after[k])
    return {"added": added, "removed": removed, "changed": changed,
            "files_before": len(before), "files_after": len(after),
            "passed": not (added or removed or changed)}


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def grade(artifact: Path, seed: int, salt: int, version: str, build_id: str,
          keep_run: Path | None) -> dict:
    started = time.monotonic()
    timing: dict[str, float | int] = {}
    flags = gen_flags(seed)
    verdict: dict = {"demo": "ctf-flag-hunt", "seed": seed,
                     "artifact": str(artifact), "gates": {},
                     "timing": timing}

    run_dir = Path(tempfile.mkdtemp(prefix="ctf-range-"))
    binaries = Path(tempfile.mkdtemp(prefix="ctf-bin-"))
    try:
        t0 = time.monotonic()
        planted = plant(run_dir, flags, seed, salt, version, build_id)
        cfg = {"seed": seed, "salt": salt, "version": version, "build": build_id}

        built = build(artifact, binaries)
        timing["build_s"] = round(time.monotonic() - t0, 3)
        g1_ok = (not built["missing"] and not built["errors"]
                 and not built["warnings"]
                 and len(built["compiled"]) == len(SERVICES))
        verdict["gates"]["build"] = {
            "passed": g1_ok, "compiled": built["compiled"],
            "missing": built["missing"], "warnings": built["warnings"],
            "errors": built["errors"]}
        if not g1_ok:
            verdict["passed"] = False
            verdict["failed_gate"] = "build"
            verdict["reason"] = ("the five services did not all compile "
                                 "warning-free")
            return _finish(verdict, started)

        # G5's baseline is taken before any service runs.
        before = snapshot(run_dir)

        t0 = time.monotonic()
        try:
            g2 = gate_g2(artifact, binaries, run_dir, flags, planted, cfg, timing)
            g3 = gate_g3(artifact, binaries, run_dir, flags, planted, cfg, timing)
            g4 = gate_g4(binaries, run_dir, artifact, flags, planted)
        except subprocess.TimeoutExpired as exc:
            raise JudgeError(f"a service did not finish within "
                             f"{RUN_TIMEOUT:.0f}s: {exc}") from exc
        timing["exploit_s"] = round(time.monotonic() - t0, 3)

        t0 = time.monotonic()
        g5 = gate_g5(before, run_dir)
        timing["blast_radius_s"] = round(time.monotonic() - t0, 3)

        g2["passed"] = g2["captured"] == g2["required"]
        g3["passed"] = g3["passed"] == g3["required"]
        g4["passed"] = g4["captured"] == 0 and not g4["sweep_hits"]

        verdict["gates"]["flags"] = g2
        verdict["gates"]["oracle"] = g3
        verdict["gates"]["negative_control"] = g4
        verdict["gates"]["blast_radius"] = g5

        failed = [name for name, g in verdict["gates"].items()
                  if not g.get("passed")]
        verdict["passed"] = not failed
        if failed:
            verdict["failed_gate"] = failed[0]
            verdict["reason"] = "; ".join(
                f"{n}: {_why(n, verdict['gates'][n])}" for n in failed)
        if keep_run is not None:
            shutil.copytree(run_dir, keep_run, dirs_exist_ok=True)
        return _finish(verdict, started)
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(binaries, ignore_errors=True)


def _why(gate: str, g: dict) -> str:
    if gate == "flags":
        bad = [c for c, ok in g["matches"].items() if not ok]
        return f"captured {g['captured']}/5 (missing {','.join(bad)})"
    if gate == "oracle":
        bad = [c for c, ok in g["checks"].items() if not ok]
        return f"{g['passed']}/5 independent checks (failed {','.join(bad)})"
    if gate == "negative_control":
        return (f"legitimate actions captured {g['captured']}/5 flags; "
                f"sweep hits {len(g['sweep_hits'])}")
    if gate == "blast_radius":
        return (f"added {g['added']} removed {g['removed']} "
                f"changed {g['changed']}")
    return "failed"


def _finish(verdict: dict, started: float) -> dict:
    verdict["timing"]["total_s"] = round(time.monotonic() - started, 3)
    return verdict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ctf-flag-hunt judge")
    ap.add_argument("artifact", help="directory of the five C services")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--salt", type=int, default=7919)
    ap.add_argument("--version", default="1.4.2")
    ap.add_argument("--build", default="r2026")
    ap.add_argument("--json", help="write the verdict JSON here")
    ap.add_argument("--keep-run", help="copy the planted range here")
    args = ap.parse_args(argv)

    artifact = Path(args.artifact)
    if not artifact.is_dir():
        print(f"grade: not a directory: {artifact}", file=sys.stderr)
        return 2

    keep = Path(args.keep_run) if args.keep_run else None
    try:
        verdict = grade(artifact, args.seed, args.salt, args.version,
                        args.build, keep)
    except JudgeError as exc:
        verdict = {"demo": "ctf-flag-hunt", "seed": args.seed,
                   "artifact": str(artifact), "passed": False,
                   "failed_gate": "error", "reason": str(exc),
                   "gates": {}, "timing": {}}

    text = json.dumps(verdict, indent=2, sort_keys=True)
    print(text)
    if args.json:
        Path(args.json).write_text(text + "\n")
    return 0 if verdict.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
