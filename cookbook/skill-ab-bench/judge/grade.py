#!/usr/bin/env python3
"""Grade one skill-ab-bench experiment record against the SPEC.md gates.

    grade.py <dir> [--seed N] [--json out.json] [--arms skill,noskill[,placebo]]
             [--bootstrap N] [--judge-dir DIR]

`<dir>` holds exactly one experiment record, `results.json` (SPEC.md).  The
judge does not take the record's word for anything:

  * it copies the artifact to a temp dir and reads it there;
  * it re-runs every task's own verifier on the recorded answer string
    (G3) -- a `passed` flag it cannot reproduce fails the grade;
  * it holds its own reference answers and recomputes their verdicts (G4),
    so a verifier that passes everything fails the grade;
  * it recomputes the pass counts, the exact binomial test and the bootstrap
    CI from the counts it verified, never from the record's numbers.

Prints one JSON verdict on stdout and exits 0 only if every gate passes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
import time
from pathlib import Path

JDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(JDIR))

import stats   # noqa: E402
import verify  # noqa: E402

SCHEMA = "skill-ab-bench/1"
DEFAULT_SEED = 20261014
DEFAULT_BOOTSTRAP = 10000
N_TASKS = 16
REQUIRED_ARMS = ("skill", "noskill")

# Numeric gate thresholds (SPEC.md).
G5_MAX_P = 0.05
G6_MIN_DELTA_PTS = 25.0
G7_MAX_PLACEBO_PTS = 10.0


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def is_finite_number(value) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def tree_digest(root: Path) -> str:
    """sha256 over every file in `root`, path and content, order-independent."""
    h = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(str(path.relative_to(root)).encode())
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def single_edit_mutations(answer: str) -> list[str]:
    """Deterministic single-edit near-misses of `answer`, all != answer.

    These are the "known-bad" reference answers G4 feeds to the task's own
    verifier: a verifier that cannot reject a one-character edit of the right
    answer is not a verifier, and the task is ungradeable.
    """
    cands = []
    if len(answer) >= 1:
        cands.append(answer[:-1])
        cands.append(answer[1:])
    cands.append(answer + " ")
    cands.append(" " + answer)
    cands.append(answer.upper())
    cands.append(answer.lower())
    cands.append(answer + "\n")
    cands.append("\t" + answer)
    if len(answer) >= 2:
        cands.append(answer[1] + answer[0] + answer[2:])
    for i, ch in enumerate(answer):
        if ch.isdigit():
            other = "0" if ch != "0" else "1"
            cands.append(answer[:i] + other + answer[i + 1:])
            break
    seen, out = set(), []
    for c in cands:
        if c and c != answer and c not in seen:
            seen.add(c)
            out.append(c)
    return sorted(out)


# ---------------------------------------------------------------------------
# G1 -- record shape
# ---------------------------------------------------------------------------

def gate_g1(record, tasks_by_id: dict, arms_wanted: list[str]) -> dict:
    problems: list[str] = []
    if not isinstance(record, dict):
        return {"pass": False, "problems": ["results.json is not a JSON object"]}
    if record.get("schema") != SCHEMA:
        problems.append(f"schema is {record.get('schema')!r}, want {SCHEMA!r}")
    seed = record.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        problems.append(f"seed is {seed!r}, want an int")

    arms = record.get("arms")
    if not isinstance(arms, dict):
        problems.append(f"arms is {type(arms).__name__}, want an object")
        arms = {}
    labels: dict[str, str] = {}
    for arm in REQUIRED_ARMS + (("placebo",) if "placebo" in arms_wanted else ()):
        label = arms.get(arm)
        if not isinstance(label, str) or not label.strip():
            problems.append(f"arms[{arm!r}] is {label!r}, want a non-empty label")
        else:
            labels[arm] = label

    tasks = record.get("tasks")
    if not isinstance(tasks, list):
        return {"pass": False, "problems": problems + [
            f"tasks is {type(tasks).__name__}, want a list"]}
    if len(tasks) != N_TASKS:
        problems.append(f"tasks has {len(tasks)} entries, want {N_TASKS}")

    seen_ids: list[str] = []
    for idx, task in enumerate(tasks):
        where = f"tasks[{idx}]"
        if not isinstance(task, dict):
            problems.append(f"{where} is not an object")
            continue
        tid = task.get("task_id")
        if tid not in tasks_by_id:
            problems.append(f"{where}.task_id is {tid!r}, not a known task id")
            continue
        if tid in seen_ids:
            problems.append(f"{where}.task_id {tid!r} is repeated")
        seen_ids.append(tid)

        flag = task.get("placebo_flag")
        if not isinstance(flag, bool):
            problems.append(f"{where}.placebo_flag is {flag!r}, want a bool")
            flag = False
        want_arms = list(REQUIRED_ARMS)
        if "placebo" in arms_wanted:
            if flag and "placebo" not in task:
                problems.append(f"{where}.placebo_flag is true but there is "
                                f"no placebo arm")
            if not flag and "placebo" in task:
                problems.append(f"{where}.placebo_flag is false but a placebo "
                                f"arm is present")
            if flag:
                want_arms.append("placebo")
        elif "placebo" in task:
            problems.append(f"{where} has a placebo arm but it was not "
                            f"requested with --arms")

        for arm in want_arms:
            block = task.get(arm)
            if not isinstance(block, dict):
                problems.append(f"{where}.{arm} is {type(block).__name__}, "
                                f"want an object")
                continue
            if not isinstance(block.get("passed"), bool):
                problems.append(f"{where}.{arm}.passed is "
                                f"{block.get('passed')!r}, want a bool")
            if not isinstance(block.get("answer"), str):
                problems.append(f"{where}.{arm}.answer is not a string")
            if not is_finite_number(block.get("ms")) or block.get("ms", -1) < 0:
                problems.append(f"{where}.{arm}.ms is {block.get('ms')!r}, "
                                f"want a finite number >= 0")
            if not isinstance(block.get("policy"), str) or not block.get("policy"):
                problems.append(f"{where}.{arm}.policy is "
                                f"{block.get('policy')!r}, want a string")
            elif arm in labels and block["policy"] != labels[arm]:
                problems.append(f"{where}.{arm}.policy is "
                                f"{block['policy']!r}, want {labels[arm]!r}")

    missing = sorted(set(tasks_by_id) - set(seen_ids))
    if missing:
        problems.append(f"tasks missing: {', '.join(missing)}")

    return {"pass": not problems, "problems": problems,
            "tasks": len(tasks), "task_ids": sorted(set(seen_ids))}


# ---------------------------------------------------------------------------
# G2 -- arm isolation
# ---------------------------------------------------------------------------

def gate_g2(record, tasks_by_id: dict, arms_wanted: list[str]) -> dict:
    problems: list[str] = []
    arms = record.get("arms") or {}
    if isinstance(arms, dict) and arms.get("skill") == arms.get("noskill"):
        problems.append(f"the skill and noskill policies share the label "
                        f"{arms.get('skill')!r}")

    shared = 0
    for task in record.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        skill, noskill = task.get("skill"), task.get("noskill")
        if not isinstance(skill, dict) or not isinstance(noskill, dict):
            continue
        if (skill.get("answer") == noskill.get("answer")
                and skill.get("passed") != noskill.get("passed")):
            shared += 1
            problems.append(
                f"{task.get('task_id')}: the two arms recorded the same "
                f"answer {skill.get('answer')!r} with different verdicts "
                f"({skill.get('passed')} vs {noskill.get('passed')})")
    return {"pass": not problems, "problems": problems,
            "tasks_with_shared_answers": shared}


# ---------------------------------------------------------------------------
# G3 -- verifier replay (independent oracle)
# ---------------------------------------------------------------------------

def gate_g3(record, tasks_by_id: dict, arms_wanted: list[str]) -> dict:
    problems: list[str] = []
    replayed = 0
    for task in record.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        tid = task.get("task_id")
        spec = tasks_by_id.get(tid)
        if spec is None:
            continue
        for arm in arms_wanted:
            block = task.get(arm)
            if not isinstance(block, dict):
                continue
            answer = block.get("answer")
            claimed = block.get("passed")
            if not isinstance(answer, str) or not isinstance(claimed, bool):
                continue
            try:
                truth = verify.verify(spec, answer)
            except Exception as exc:                    # fail closed
                problems.append(f"{tid}/{arm}: oracle raised "
                                f"{type(exc).__name__}: {exc}")
                continue
            replayed += 1
            if truth != claimed:
                problems.append(
                    f"{tid}/{arm}: recorded passed={claimed} but the oracle "
                    f"says {truth} for answer {answer!r}")
    return {"pass": not problems, "problems": problems, "replayed": replayed}


# ---------------------------------------------------------------------------
# G4 -- task identifiability (two-sided oracle)
# ---------------------------------------------------------------------------

def gate_g4(tasks_by_id: dict, reference: dict) -> dict:
    """Every task must separate the reference answer from single-edit misses.

    The judge computes the reference answer itself and compares it with the
    committed one (drift check), then feeds both the reference and every
    single-edit mutant of it to the task's verifier.  A task whose verifier
    cannot tell them apart is ungradeable and fails the grade.
    """
    problems: list[str] = []
    checked = 0
    ref_tasks = reference.get("tasks") if isinstance(reference, dict) else None
    if not isinstance(ref_tasks, dict):
        return {"pass": False, "problems": ["reference.json has no tasks object"]}

    for tid, spec in sorted(tasks_by_id.items()):
        entry = ref_tasks.get(tid)
        if not isinstance(entry, dict) or not isinstance(entry.get("expected"), str):
            problems.append(f"{tid}: reference.json has no expected answer")
            continue
        try:
            mine = verify.expected_answer(spec)
        except Exception as exc:
            problems.append(f"{tid}: oracle raised {type(exc).__name__}: {exc}")
            continue
        if mine != entry["expected"]:
            problems.append(f"{tid}: the judge's oracle says {mine!r} but "
                            f"reference.json says {entry['expected']!r}")
            continue
        if not verify.verify(spec, entry["expected"]):
            problems.append(f"{tid}: the verifier rejects its own reference "
                            f"answer {entry['expected']!r}")
            continue
        bad = [b for b in entry.get("bad", []) if isinstance(b, str)]
        if len(bad) < 3:
            problems.append(f"{tid}: only {len(bad)} single-edit bad answers "
                            f"in reference.json, want >= 3")
            continue
        accepted = [b for b in bad if verify.verify(spec, b)]
        if accepted:
            problems.append(f"{tid}: the verifier accepts {len(accepted)} "
                            f"single-edit wrong answer(s), e.g. {accepted[0]!r}")
            continue
        checked += 1
    return {"pass": not problems, "problems": problems, "tasks_checked": checked}


# ---------------------------------------------------------------------------
# G5-G7 -- the statistics
# ---------------------------------------------------------------------------

def _counts(record, arms_wanted: list[str]) -> dict[str, list[bool]]:
    out: dict[str, list[bool]] = {a: [] for a in arms_wanted}
    for task in record.get("tasks") or []:
        for arm in arms_wanted:
            block = task.get(arm)
            if isinstance(block, dict) and isinstance(block.get("passed"), bool):
                out[arm].append(block["passed"])
    return out


def gate_g5(counts: dict, n: int) -> dict:
    a, b = counts["skill"], counts["noskill"]
    na, nb = sum(a), sum(b)
    p = stats.fisher_exact_2x2(na, n - na, nb, n - nb)
    ok = p < G5_MAX_P
    return {"pass": ok, "fisher_p": p, "threshold_p": G5_MAX_P,
            "skill_passes": na, "noskill_passes": nb, "n": n,
            "problems": [] if ok else [
                f"Fisher's exact p = {p:.6g} is not < {G5_MAX_P} "
                f"({na}/{n} vs {nb}/{n}): the difference is not significant"]}


def gate_g6(counts: dict, n: int, seed: int, resamples: int) -> dict:
    a, b = counts["skill"], counts["noskill"]
    na, nb = sum(a), sum(b)
    delta_pts = 100.0 * (na - nb) / n
    ci = stats.bootstrap_delta_ci(a, b, seed=seed, resamples=resamples)
    problems = []
    if delta_pts < G6_MIN_DELTA_PTS:
        problems.append(f"delta {delta_pts:.1f} pts is below the "
                        f"{G6_MIN_DELTA_PTS} pts bar")
    if not ci["lo"] > 0:
        problems.append(f"the bootstrap CI lower bound {ci['lo']:.4f} is not "
                        f"> 0: the delta could be zero")
    return {"pass": not problems, "problems": problems,
            "delta_pts": delta_pts, "min_delta_pts": G6_MIN_DELTA_PTS,
            "ci": ci,
            "skill_passes": na, "noskill_passes": nb, "n": n}


def gate_g7(counts: dict, n: int, seed: int, resamples: int,
            placebo_wanted: bool) -> dict:
    if not placebo_wanted or "placebo" not in counts:
        return {"pass": True, "skipped": True,
                "note": "no placebo arm requested; the control was not run"}
    a, b = counts["noskill"], counts["placebo"]
    na, nb = sum(a), sum(b)
    delta_pts = 100.0 * (na - nb) / n
    ci = stats.bootstrap_delta_ci(a, b, seed=seed, resamples=resamples)
    problems = []
    if abs(delta_pts) >= G7_MAX_PLACEBO_PTS:
        problems.append(f"the placebo arm moves the pass rate by "
                        f"{delta_pts:+.1f} pts (|delta| must be < "
                        f"{G7_MAX_PLACEBO_PTS})")
    if not (ci["lo"] <= 0.0 <= ci["hi"]):
        problems.append(f"the placebo CI [{ci['lo']:.4f}, {ci['hi']:.4f}] does "
                        f"not contain 0")
    return {"pass": not problems, "problems": problems,
            "delta_pts": delta_pts, "max_abs_delta_pts": G7_MAX_PLACEBO_PTS,
            "ci": ci, "noskill_passes": na, "placebo_passes": nb, "n": n}


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--arms", default="skill,noskill,placebo")
    ap.add_argument("--bootstrap", type=int, default=DEFAULT_BOOTSTRAP)
    ap.add_argument("--judge-dir", default=str(JDIR))
    args = ap.parse_args()

    t0 = time.perf_counter()
    judge_dir = Path(args.judge_dir).resolve()
    arms_wanted = [a.strip() for a in args.arms.split(",") if a.strip()]
    for arm in arms_wanted:
        if arm not in ("skill", "noskill", "placebo"):
            raise SystemExit(f"grade: unknown arm {arm!r}")
    for arm in REQUIRED_ARMS:
        if arm not in arms_wanted:
            raise SystemExit(f"grade: arm {arm!r} cannot be dropped")

    judge_before = tree_digest(judge_dir)

    with open(judge_dir / "tasks.json", encoding="utf-8") as fh:
        task_list = json.load(fh)["tasks"]
    tasks_by_id = {t["task_id"]: t for t in task_list}
    with open(judge_dir / "reference.json", encoding="utf-8") as fh:
        reference = json.load(fh)

    artifact = Path(args.artifact)
    gates: dict[str, dict] = {}
    failed_gate = None
    record = None
    artifact_error = None

    if not artifact.is_dir():
        artifact_error = f"artifact {artifact} is not a directory"
    elif not (artifact / "results.json").is_file():
        artifact_error = f"artifact {artifact} has no results.json"

    if artifact_error is None:
        # Grade a copy: the artifact never executes judge code, and never
        # touches the judge's own tree.
        with tempfile.TemporaryDirectory(prefix="skill-ab-bench-") as tmp:
            work = Path(tmp) / "artifact"
            shutil.copytree(artifact, work)
            try:
                with open(work / "results.json", encoding="utf-8") as fh:
                    record = json.load(fh)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                artifact_error = f"results.json is not valid JSON: {exc}"

    if artifact_error is None:
        # Gates run in order; the first failure stops grading, so a record
        # that is structurally wrong never reaches the statistics.
        for name, fn in (
            ("G1_record_shape", lambda: gate_g1(record, tasks_by_id, arms_wanted)),
            ("G2_arm_isolation", lambda: gate_g2(record, tasks_by_id, arms_wanted)),
            ("G3_verifier_replay", lambda: gate_g3(record, tasks_by_id, arms_wanted)),
            ("G4_task_identifiability", lambda: gate_g4(tasks_by_id, reference)),
        ):
            gates[name] = fn()
            if not gates[name]["pass"]:
                failed_gate = name
                break

    if artifact_error is None and failed_gate is None:
        counts = _counts(record, arms_wanted)
        n = min(len(v) for v in counts.values())
        for name, fn in (
            ("G5_power", lambda: gate_g5(counts, n)),
            ("G6_effect_size", lambda: gate_g6(counts, n, args.seed, args.bootstrap)),
            ("G7_placebo_control", lambda: gate_g7(counts, n, args.seed,
                                                   args.bootstrap,
                                                   "placebo" in arms_wanted)),
        ):
            gates[name] = fn()
            if not gates[name]["pass"]:
                failed_gate = name
                break

    judge_after = tree_digest(judge_dir)
    judge_intact = judge_before == judge_after
    gates["G8_judge_integrity"] = {
        "pass": judge_intact,
        "problems": [] if judge_intact else [
            "the judge tree changed while grading; failing closed"],
        "judge_sha256": judge_before,
        "graded_from_copy": artifact_error is None,
    }
    if not judge_intact and failed_gate is None:
        failed_gate = "G8_judge_integrity"

    all_pass = bool(gates) and all(g["pass"] for g in gates.values()) \
        and artifact_error is None and len(gates) == 8

    verdict = {
        "schema": SCHEMA,
        "verdict": "pass" if all_pass else "fail",
        "failed_gate": failed_gate,
        "artifact_error": artifact_error,
        "seed": args.seed,
        "bootstrap_resamples": args.bootstrap,
        "arms": arms_wanted,
        "gates": gates,
        "timing": {"wall_s": round(time.perf_counter() - t0, 3)},
    }
    text = json.dumps(verdict, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
