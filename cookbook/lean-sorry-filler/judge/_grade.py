#!/usr/bin/env python3
"""Grade a lean-sorry-filler artifact. See SPEC.md for the gates.

The artifact is a directory (the fixture's file set with proofs filled
in). We never run anything out of it in place: the file set is copied
into a fresh temp dir, `lake build` runs there, and the judge's own
JudgeCheck.lean is elaborated against the built library. sha256
checksums of judge/ are compared before and after.

Output: one JSON verdict on stdout (sorted keys); wall times only under
"timing". Exit 0 iff every gate passes.
"""

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

EXPECTED_FILES = ["Exercises.lean", "lakefile.toml", "lean-toolchain"] + \
    [f"Exercises/Ex{i:02d}.lean" for i in range(1, 11)]
MAX_FILE_KIB = 64
SORRY_RE = re.compile(r"(?:^|[^A-Za-z0-9_.'])(sorry|admit|sorryAx)"
                     r"(?![A-Za-z0-9_'])")
CHEAT_RE = re.compile(r"(?:^|[^A-Za-z0-9_.'])(native_decide|axiom)"
                      r"(?![A-Za-z0-9_'])")
BUILD_SORRY_RE = re.compile(r"declaration uses `sorry`")
# the frozen statement is everything from "theorem" up to ":=" on the
# theorem line; proofs may replace what follows the ":="
STATEMENT_RE = re.compile(
    r"^(theorem\s+([A-Za-z_][A-Za-z0-9_']*)[^\n]*?)\s*:=\s*by\s+sorry\s*$",
    re.M)
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
BUILD_TIMEOUT_S = 600
AXIOMS_TIMEOUT_S = 120


def strip_comments(text):
    """Remove Lean comments from a source, keeping everything else.

    Handles `--` line comments and `/- -/` block comments (which nest).
    A `--` or `/-` inside a string literal is not comment syntax; Lean
    string literals cannot span lines, so scan each line up to its
    newline, guarding `--` / `/-` that appear inside a literal. All
    newlines outside comments are preserved, so line anchors in the
    stripped text still line up with the original file.
    """
    out = []
    i, n = 0, len(text)
    in_block = 0  # nesting depth of /- -/ block comments
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_block:
            if c == "-" and nxt == "/":
                in_block -= 1
                i += 2
            elif c == "/" and nxt == "-":
                in_block += 1
                i += 2
            else:
                i += 1
        elif c == "/" and nxt == "-":
            in_block += 1
            i += 2
        elif c == "-" and nxt == "-":
            # line comment: skip to end of line, keep the newline
            j = text.find("\n", i)
            i = n if j < 0 else j
        else:
            out.append(c)
            i += 1
    return "".join(out)


def log(*a):
    print(*a, file=sys.stderr)


def sha256_tree(root):
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(root))] = hashlib.sha256(
                p.read_bytes()).hexdigest()
    return out


def elan_home():
    return Path(os.environ.get("ELAN_HOME", str(Path.home() / ".elan")))


def find_elan():
    c = elan_home() / "bin"
    if (c / "lean").exists():
        return c
    log("grade: no Lean toolchain found; run judge/setup.sh first")
    sys.exit(2)


def count_planted(fixture):
    n = 0
    for f in EXPECTED_FILES[3:]:
        n += len(SORRY_RE.findall(strip_comments(
            (fixture / f).read_text())))
    return n


def gate_structure(artifact, fixture, verdict):
    """Gate 1: file set, statement freeze, forbidden tokens, size."""
    g = {"pass": True, "problems": []}
    files = sorted(str(p.relative_to(artifact)) for p in
                   artifact.rglob("*") if p.is_file())
    expected = sorted(EXPECTED_FILES)
    if files != expected:
        g["pass"] = False
        g["problems"].append(
            f"file set differs: missing={set(expected) - set(files)} "
            f"extra={set(files) - set(expected)}")

    matched = 0
    for name in EXPECTED_FILES[3:]:
        sub = artifact / name
        if not sub.is_file():
            continue
        text = sub.read_text()
        if len(text.encode()) > MAX_FILE_KIB * 1024:
            g["pass"] = False
            g["problems"].append(f"{name}: {len(text.encode())} bytes > "
                                 f"{MAX_FILE_KIB} KiB")
        # comments are removed before every scan: a token or statement
        # parked in a comment (line or block) is not code
        code = strip_comments(text)
        for token in SORRY_RE.findall(code) + CHEAT_RE.findall(code):
            g["pass"] = False
            g["problems"].append(f"{name}: forbidden token {token!r}")
        # statement freeze: the fixture's theorem text up to ":=" must
        # be the head of the theorem with that same name in the
        # submission. Both texts are scanned with Lean comments
        # removed (block comments nest; line comments end at the
        # newline): the frozen text may never park inside a comment
        # while a weaker statement is proved under the same name.
        fx = strip_comments((fixture / name).read_text())
        m = STATEMENT_RE.search(fx)
        if m:
            frozen = m.group(1).strip()
            tname = m.group(2)
            line_re = re.compile(
                r"^theorem\s+" + re.escape(tname) +
                r"\b[^\n]*?([ \t]*:=)", re.M)
            lm = line_re.search(code)
            if lm is None:
                g["pass"] = False
                g["problems"].append(f"{name}: no theorem {tname!r} "
                                      "found")
                continue
            stmt = text[lm.start():lm.start(1)].rstrip()
            if stmt != frozen:
                g["pass"] = False
                g["problems"].append(f"{name}: theorem statement "
                                      "differs from the fixture")
                continue
            matched += 1
    if matched != 10:
        g["pass"] = False
        g["problems"].append(f"statements matched {matched}/10")
    g["statements_matched"] = matched
    verdict["structure"] = g


def gate_build(artifact, elan_bin, verdict):
    """Gate 2: lake build exits 0, zero sorry warnings in the log."""
    g = {"pass": False}
    t0 = time.monotonic()
    
    env = dict(PATH=f"{elan_bin}:{os.environ['PATH']}",
               ELAN_HOME=str(elan_home()))
    proc = subprocess.run(["lake", "build", "--no-cache"], cwd=artifact,
                          capture_output=True, text=True, timeout=BUILD_TIMEOUT_S,
                          env=env)
    g["build_exit"] = proc.returncode
    log_text = proc.stdout + proc.stderr
    g["sorry_warnings"] = len(BUILD_SORRY_RE.findall(log_text))
    g["build_log_lines"] = len(log_text.splitlines())
    if proc.returncode != 0:
        # diagnostics on stderr only; the verdict JSON stays deterministic
        log("grade: lake build failed; last lines:")
        log("\n".join(log_text.splitlines()[-12:]))
    if proc.returncode == 0 and g["sorry_warnings"] == 0:
        g["pass"] = True
    verdict["build"] = g
    verdict.setdefault("timing", {})["build_s"] = round(
        time.monotonic() - t0, 1)


def gate_axioms(artifact, elan_bin, judge_dir, verdict):
    """Gate 3: kernel audit of every exercise theorem's axiom set."""
    g = {"pass": True, "problems": [], "axioms": {}}
    check = judge_dir / "JudgeCheck.lean"
    t0 = time.monotonic()
    
    env = dict(PATH=f"{elan_bin}:{os.environ['PATH']}",
               ELAN_HOME=str(elan_home()))
    proc = subprocess.run(["lake", "env", "lean", str(check)],
                          cwd=artifact, capture_output=True, text=True,
                          timeout=AXIOMS_TIMEOUT_S, env=env)
    g["audit_exit"] = proc.returncode
    out = proc.stdout + proc.stderr
    for line in out.splitlines():
        m = re.match(r"'([A-Za-z0-9_'.]+)'.*(does not depend on any axioms"
                     r"|depends on axioms: \[.*\])", line)
        if m:
            name, dep = m.groups()
            if "does not depend" in dep:
                axioms = []
            else:
                axioms = sorted(re.findall(r"[A-Za-z0-9_'.]+",
                                           dep.split("[", 1)[1]))
            g["axioms"][name] = axioms
            extra = set(axioms) - ALLOWED_AXIOMS
            if extra:
                g["pass"] = False
                g["problems"].append(f"{name}: non-standard axioms "
                                      f"{sorted(extra)}")
    if len(g["axioms"]) != 10:
        g["pass"] = False
        g["problems"].append(f"audited {len(g['axioms'])}/10 theorems")
    verdict["axioms"] = g
    verdict.setdefault("timing", {})["axioms_s"] = round(
        time.monotonic() - t0, 1)


def gate_closure(artifact, fixture, verdict):
    """Gate 4: >= 60% of planted sorries closed in the submitted text."""
    g = {}
    planted = count_planted(fixture)
    remaining = 0
    per_file = {}
    for name in EXPECTED_FILES[3:]:
        sub = artifact / name
        if sub.is_file():
            n = len(SORRY_RE.findall(strip_comments(sub.read_text())))
            per_file[name] = n
            remaining += n
        else:
            per_file[name] = None
            remaining += 1  # a missing file closes nothing
    closed = planted - remaining
    rate = (closed / planted) if planted else 0.0
    g.update(planted=planted, remaining=remaining, closed=closed,
             closed_rate=round(rate, 3),
             per_file=per_file,
             **{"pass": rate >= 0.60})
    verdict["closure"] = g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", metavar="OUT")
    ap.add_argument("--judge-dir")
    args = ap.parse_args()
    judge_dir = Path(args.judge_dir or Path(__file__).resolve().parent)
    fixture = judge_dir / "fixture"
    artifact = Path(args.artifact).resolve()
    if not artifact.is_dir():
        log(f"grade: artifact {artifact} is not a directory")
        sys.exit(2)

    before = sha256_tree(judge_dir)
    elan_bin = find_elan()
    verdict = {"artifact": str(artifact), "seed": args.seed}
    t_all = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="lsf-grade-") as tmp:
        tmp = Path(tmp)
        work = tmp / "pkg"
        work.mkdir()
        for name in EXPECTED_FILES:
            dst = work / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            src = artifact / name
            if src.is_file():
                shutil.copy(src, dst)
            else:
                dst.write_text("")
        gate_structure(work, fixture, verdict)
        gate_build(work, elan_bin, verdict)
        gate_axioms(work, elan_bin, judge_dir, verdict)
        gate_closure(work, fixture, verdict)

    after = sha256_tree(judge_dir)
    verdict["judge_intact"] = before == after
    verdict.setdefault("timing", {})["total_s"] = round(
        time.monotonic() - t_all, 1)
    ok = all(g.get("pass") for k, g in verdict.items()
             if isinstance(g, dict) and k not in ("timing",)) \
        and verdict["judge_intact"]
    verdict["pass"] = ok
    out = json.dumps(verdict, indent=2, sort_keys=True, default=str)
    if args.json:
        Path(args.json).write_text(out)
    print(out)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
