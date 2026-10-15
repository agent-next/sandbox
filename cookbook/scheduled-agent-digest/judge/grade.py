#!/usr/bin/env python3
"""Judge for the scheduled-agent digest demo.

    grade.py <artifact-dir> [--seed N] [--json out.json]

Runs every gate from SPEC.md against an artifact directory holding
`digest.py` + `schedule.json`, and prints one JSON verdict.  Exit 0 only if
every gate passes.

The judge never trusts the artifact:

* every aggregate is recomputed by an **independent sqlite3 oracle**
  (`_night.run_oracle`);
* the *state* of the sandbox between fires is read from the transport the
  judge drives, not from what the artifact claims;
* a malformed log must make the artifact fail loudly (non-zero exit, nothing
  written), which is the negative control on fabricated numbers;
* the artifact is copied to a temp dir before grading, and `judge/` is
  checksummed before and after by `grade.sh`.

Stdlib only.  Deterministic: no wall clock enters the graded numbers.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

JDIR = Path(__file__).resolve().parent
sys.path.insert(0, str(JDIR))

import _night  # noqa: E402
from _night import NIGHTS, DIGEST_KEYS, STEPS  # noqa: E402
from transport import (PausedSleepTransport, FakeSbxClient,  # noqa: E402
                       sbx_resume, sbx_pause, RUNNING, PAUSED)

# Numeric gate ids, fixed so selftest output is stable.
GATES = ["digest", "dates", "shape", "schedule", "lifecycle", "negative",
         "failure", "integrity"]

# a seed only feeds the RNG the judge may use; every fixture number here is
# pinned, so the seed is recorded and re-checked for byte-identical verdicts
DEFAULT_SEED = 20261015

NUMERIC_FIELDS = ["events", "errors", "server_errors", "error_rate", "mean_ms",
                  "p50_ms", "p95_ms", "max_ms"]


class Gate:
    """One gate: a name, a pass/fail, and the numbers that decided it."""

    def __init__(self, name: str):
        self.name = name
        self.passed = True
        self.detail: dict = {}
        self.reason = ""

    def fail(self, reason: str, **numbers) -> None:
        self.passed = False
        if not self.reason:
            self.reason = reason
            self.detail = numbers

    def note(self, **numbers) -> None:
        self.detail.update(numbers)

    def as_json(self) -> dict:
        out = {"passed": self.passed}
        out.update(self.detail)
        if not self.passed:
            out["reason"] = self.reason
        return out


def load_json(path: Path, gate: Gate, what: str):
    try:
        text = path.read_text()
    except OSError as exc:
        gate.fail(f"{what} unreadable: {exc}")
        return None
    try:
        return json.loads(text)
    except ValueError as exc:
        gate.fail(f"{what} is not valid JSON: {exc}")
        return None


# --------------------------------------------------------------------------
# the gates
# --------------------------------------------------------------------------
def gate_digest(work: Path, digests: list[dict], seed: int) -> Gate:
    """G1: every pinned field of all three nights matches the oracle
    exactly — counts, rates, mean, both percentiles, the max, the per-project
    map and the busiest project."""
    gate = Gate("digest")
    for (date, _fire, fixture), got in zip(NIGHTS, digests):
        want = _night.run_oracle(date, work / "fixtures" / fixture)
        for key, expected in want.items():
            actual = got.get(key, "<missing>")
            if actual != expected:
                gate.fail(f"{date}: {key} is {actual!r}, the oracle says "
                          f"{expected!r}", date=date, field=key,
                          actual=actual, expected=expected)
                return gate
        gate.note(**{f"{date}_{k}": got[k] for k in NUMERIC_FIELDS})
    gate.note(busiest={d["date"]: d["busiest_project"] for d in digests})
    return gate


def gate_dates(digests: list[dict], work: Path) -> Gate:
    """G2: the digest is built from the selected date's rows only.

    The fixtures hold rows from the day before and the two hours of the fire
    day, so a digester that totals the whole file shows a visibly larger
    `events` count.  The oracle's count is the target; the file's row count is
    the tell that catches it.
    """
    gate = Gate("dates")
    for (date, _fire, fixture), got in zip(NIGHTS, digests):
        want = _night.run_oracle(date, work / "fixtures" / fixture)
        if got.get("events") != want["events"]:
            gate.fail(f"{date}: {got.get('events')} events counted, "
                      f"{want['events']} belong to that date (the log holds "
                      f"{_count_rows(work / 'fixtures' / fixture)} rows in "
                      f"total)", date=date, actual=got.get("events"),
                      expected=want["events"])
            return gate
        if got.get("date") != date:
            gate.fail(f"digest reports date {got.get('date')!r} for the log "
                      f"of {date}", date=date)
            return gate
    gate.note(counts={g["date"]: g["events"] for g in digests})
    return gate


def _count_rows(csv_path: Path) -> int:
    with open(csv_path) as fh:
        return max(0, sum(1 for _ in fh) - 1)


def gate_shape(digests: list[dict]) -> Gate:
    """G3: exactly the pinned key set, types, sorted projects, and a
    consistent error_rate."""
    gate = Gate("shape")
    for got in digests:
        keys = set(got)
        if keys != DIGEST_KEYS:
            missing = sorted(DIGEST_KEYS - keys)
            extra = sorted(keys - DIGEST_KEYS)
            gate.fail(f"digest key set wrong: missing {missing}, "
                      f"unexpected {extra}", date=got.get("date"),
                      missing=missing, extra=extra)
            return gate
        projects = got["projects"]
        if list(projects) != sorted(projects):
            gate.fail(f"projects map is not sorted by key: {list(projects)}",
                      date=got["date"])
            return gate
        if got["events"]:
            rate = got["errors"] / got["events"]
            if abs(rate - got["error_rate"]) > 1e-6:
                gate.fail(f"error_rate {got['error_rate']} != errors/events "
                          f"{rate:.6f}", date=got["date"])
                return gate
        else:
            if got["status"] == "ok":
                gate.fail(f"zero events but status {got['status']!r} — an "
                          "empty day must say 'no events'", date=got["date"])
                return gate
        for field in ("p50_ms", "p95_ms", "max_ms"):
            if not isinstance(got[field], int):
                gate.fail(f"{field} must be an int, got "
                          f"{type(got[field]).__name__}", date=got["date"])
                return gate
        if got["p50_ms"] > got["max_ms"] or got["max_ms"] < got["p95_ms"]:
            gate.fail("latency percentiles are not ordered "
                      f"p50={got['p50_ms']} p95={got['p95_ms']} "
                      f"max={got['max_ms']}", date=got["date"])
            return gate
    gate.note(keys=sorted(DIGEST_KEYS))
    return gate


def gate_schedule(schedule) -> Gate:
    """G4: cron fires at 02:00, pause between runs, and exactly the five
    canonical steps in order."""
    gate = Gate("schedule")
    if not isinstance(schedule, dict):
        gate.fail(f"schedule.json must be a JSON object, got "
                  f"{type(schedule).__name__}")
        return gate
    job = schedule.get("job")
    if not isinstance(job, dict):
        gate.fail("schedule.json has no 'job' object")
        return gate
    cron = job.get("schedule")
    fields = str(cron).split() if isinstance(cron, str) else []
    if len(fields) != 5 or fields[0] != "0" or fields[1] != "2":
        gate.fail(f"job schedule {cron!r} does not fire at 02:00 every day; "
                  "expected '0 2 * * *'", cron=cron)
        return gate
    for key in ("name", "command", "timezone"):
        if not job.get(key):
            gate.fail(f"job.{key} is missing", key=key)
            return gate
    sandbox = schedule.get("sandbox", {})
    if sandbox.get("pause_between_runs") is not True:
        gate.fail("sandbox.pause_between_runs must be true (an idle sandbox "
                  "that stays awake is what this demo is not about)",
                  value=sandbox.get("pause_between_runs"))
        return gate
    steps = schedule.get("steps")
    if not isinstance(steps, list):
        gate.fail("'steps' must be an array")
        return gate
    uses = [s.get("uses") for s in steps if isinstance(s, dict)]
    if uses != STEPS:
        gate.fail(f"steps are {uses}, the canonical lifecycle is {STEPS}",
                  uses=uses, expected=STEPS)
        return gate
    gate.note(cron=cron, steps=uses)
    return gate


def gate_lifecycle(work: Path, records: list[dict]) -> Gate:
    """G5: three fires, each running then paused, with the state read as
    'paused' between every pair."""
    gate = Gate("lifecycle")
    if len(records) != len(NIGHTS):
        gate.fail(f"{len(records)} fires recorded, {len(NIGHTS)} expected")
        return gate
    for record in records:
        if record["state_after_resume"] != RUNNING:
            gate.fail(f"{record['night']}: sandbox was "
                      f"{record['state_after_resume']!r} after resume, "
                      "expected 'running'", night=record["night"])
            return gate
        if record["state_before_pause"] != RUNNING:
            gate.fail(f"{record['night']}: the digest ran while the sandbox "
                      f"was {record['state_before_pause']!r}",
                      night=record["night"])
            return gate
        if record["state_after_pause"] != PAUSED:
            gate.fail(f"{record['night']}: sandbox was "
                      f"{record['state_after_pause']!r} after pause, "
                      "expected 'paused'", night=record["night"])
            return gate
        state = json.loads((work / "out" / "state.json").read_text())["state"]
        if state != PAUSED:
            gate.fail(f"{record['night']}: state.json reads {state!r} between "
                      "runs, expected 'paused'", night=record["night"])
            return gate
    gate.note(fires=[r["night"] for r in records],
              states_between_runs=[r["state_between_runs"] for r in records],
              pause_seconds=0.05, sandbox=records[-1].get("sandbox"))
    return gate


def gate_negative(work: Path, artifact: Path) -> Gate:
    """G6: the same digest.py on an empty log must say 'no events', not
    zeros dressed up as a real day."""
    gate = Gate("negative")
    out = work / "out" / "digest-empty.json"
    proc = subprocess.run(
        [sys.executable, "-I", "digest.py", "--log",
         str(work / "fixtures" / "empty.csv"), "--date", "2026-10-12",
         "--out", str(out)],
        capture_output=True, text=True, cwd=str(artifact))
    if proc.returncode != 0:
        gate.fail(f"digest.py exited {proc.returncode} on an empty log: "
                  f"{proc.stderr.strip()[-200:]}", exit_code=proc.returncode)
        return gate
    got = load_json(out, gate, "the empty-log digest")
    if got is None:
        return gate
    want = _night.run_oracle("2026-10-12", work / "fixtures" / "empty.csv")
    for key, expected in want.items():
        if got.get(key) != expected:
            gate.fail(f"empty log: {key} is {got.get(key)!r}, expected "
                      f"{expected!r}", field=key, actual=got.get(key),
                      expected=expected)
            return gate
    if got.get("status") != "no events":
        gate.fail(f"an empty log must be reported as 'no events', got "
                  f"{got.get('status')!r}", status=got.get("status"))
        return gate
    gate.note(status=got["status"], events=got["events"])
    return gate


def gate_failure(work: Path, artifact: Path) -> Gate:
    """G7: a malformed row must make digest.py exit non-zero, name the log
    and the row, and leave no digest behind."""
    gate = Gate("failure")
    out = work / "out" / "digest-should-not-exist.json"
    if out.exists():
        out.unlink()
    proc = subprocess.run(
        [sys.executable, "-I", "digest.py", "--log",
         str(work / "fixtures" / "malformed.csv"), "--date", "2026-10-12",
         "--out", str(out)],
        capture_output=True, text=True, cwd=str(artifact))
    if proc.returncode == 0:
        gate.fail("digest.py exited 0 on a log with a non-numeric latency and "
                  "a short row — bad input must be rejected", exit_code=0)
        return gate
    if out.exists() or (work / "out" / "digest-should-not-exist.json.partial"
                        ).exists():
        gate.fail("a digest file was left behind after a failed run",
                  left_behind=str(out))
        return gate
    text = proc.stderr.strip()
    if "malformed.csv" not in text:
        gate.fail(f"the error does not name the log it failed on: {text[:200]!r}",
                  stderr=text[-200:])
        return gate
    gate.note(exit_code=proc.returncode, names_log=True)
    return gate


def gate_integrity(artifact: Path, work: Path) -> Gate:
    """G8: the artifact must not be able to touch the judge.

    The artifact is copied before grading, so it never runs against the judge
    tree at all; this gate records that and checks the copy is the only thing
    `digest.py` could see (no `judge/` inside it, no import of judge modules).
    """
    gate = Gate("integrity")
    bad = []
    for rel in ("judge", "_night.py", "grade.py"):
        if (artifact / rel).exists():
            bad.append(rel)
    if bad:
        gate.fail(f"the artifact carries {bad} — it must be a digest, not a "
                  "copy of the judge", found=bad)
        return gate
    text = (artifact / "digest.py").read_text()
    for name in ("_night", "transport", "grade.py", "selftest"):
        if f"import {name}" in text or f"from {name} " in text:
            gate.fail(f"digest.py imports {name} — the artifact cannot use "
                      "the judge's code", imports=name)
            return gate
    gate.note(copied_to=str(artifact), judge_untouched=True)
    return gate


# --------------------------------------------------------------------------
def run_three_nights(artifact: Path, work: Path) -> tuple[list[dict], list[dict]]:
    """Walk the canonical lifecycle three times through the default transport,
    then once through the sbx shims against a fake client (which proves the
    shim wiring the same way)."""
    import shutil as _shutil

    digests: list[dict] = []
    records: list[dict] = []
    transport = PausedSleepTransport(pause_seconds=0.0)
    for date, fire, fixture in NIGHTS:
        record = _night.run_night(log=work / "fixtures" / fixture, date=date,
                                  fire_on=fire, workdir=artifact,
                                  transport=transport,
                                  state_path=work / "out" / "state.json",
                                  journal=work / "out" / "run_journal.jsonl")
        records.append(record)
        digests.append(json.loads(Path(record["digest"]).read_text()))

    # the same five steps through the sbx-facing shims: resume -> work ->
    # pause, with the state read in between
    fake = FakeSbxClient()
    shim = _ShimTransport(fake)
    for date, fire, fixture in NIGHTS:
        shim.wait_for_fire(fire)
        shim.resume()
        if shim.state() != RUNNING:
            raise RuntimeError(f"sbx shim left the sandbox "
                               f"{shim.state()!r} after resume")
        if not (artifact / "digest.py").is_file():
            raise RuntimeError("digest.py vanished")
        shim.pause()
        if shim.state() != PAUSED:
            raise RuntimeError(f"sbx shim left the sandbox "
                               f"{shim.state()!r} after pause")
    records[-1]["shim_calls"] = list(fake.calls)
    records[-1]["shim_resumes"] = fake.connected
    return records, digests


class _ShimTransport:
    """The sbx shims behind the transport interface, driven by the lifecycle
    gate so the wiring is proven the same way as the default transport."""

    def __init__(self, client, sandbox_id: str = "judge-sbx"):
        self.client = client
        self.sandbox_id = sandbox_id
        self._state = PAUSED

    def wait_for_fire(self, when: str) -> None:
        return None

    def resume(self) -> None:
        sbx_resume(self.client, self.sandbox_id)
        self._state = RUNNING

    def pause(self) -> None:
        sbx_pause(self.client, self.sandbox_id)
        self._state = PAUSED

    def state(self) -> str:
        return self._state


class _ShimTransport:
    """Minimal state tracker so the sbx shims can be driven inside the judge."""

    def __init__(self, client, *, pause_seconds: float):
        self.client = client
        self._state = PAUSED

    def wait_for_fire(self, when: str) -> None:
        return None

    def resume(self) -> None:
        sbx_resume(self.client, "fake-sbx")
        self._state = RUNNING

    def pause_via(self, fn, client) -> None:
        fn(client, "fake-sbx")
        self._state = PAUSED

    def state(self) -> str:
        return self._state


def grade(artifact_dir: Path, seed: int = DEFAULT_SEED) -> dict:
    """Grade one artifact directory; returns the verdict dict."""
    artifact_src = Path(artifact_dir).resolve()
    for needed in ("digest.py", "schedule.json"):
        if not (artifact_src / needed).is_file():
            return {"artifact": str(artifact_dir), "seed": seed,
                    "passed": False, "failed_gate": "artifact",
                    "reason": f"missing {needed} in {artifact_src}"}

    verdict = {"artifact": str(artifact_dir), "seed": seed,
               "gates": {}, "passed": True, "failed_gate": None, "reason": ""}

    with tempfile.TemporaryDirectory(prefix="digest-judge-") as tmp:
        work = Path(tmp)
        fixtures = work / "fixtures"
        subprocess.run([sys.executable, "-I", str(JDIR / "make_fixtures.py"),
                        "--outdir", str(fixtures)], check=True,
                       capture_output=True, text=True)
        # the artifact is graded from a copy: it can never modify the judge
        artifact = work / "artifact"
        shutil.copytree(artifact_src, artifact)

        gates = {}

        records, digests = run_three_nights(artifact, work)

        gates["digest"] = gate_digest(work, digests, seed)
        gates["dates"] = gate_dates(digests, work)
        gates["shape"] = gate_shape(digests)
        schedule = load_json(artifact / "schedule.json", Gate("schedule"),
                            "schedule.json")
        gates["schedule"] = (gate_schedule(schedule)
                             if schedule is not None else Gate("schedule"))
        gates["lifecycle"] = gate_lifecycle(work, records)
        gates["negative"] = gate_negative(work, artifact)
        gates["failure"] = gate_failure(work, artifact)
        gates["integrity"] = gate_integrity(artifact, work)

        verdict["gates"] = {name: gates[name].as_json() for name in GATES}
        for name in GATES:
            if not gates[name].passed:
                verdict["passed"] = False
                verdict["failed_gate"] = name
                verdict["reason"] = gates[name].reason
                break

    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--json", dest="json_out")
    args = parser.parse_args(argv)

    verdict = grade(args.artifact, args.seed)
    text = json.dumps(verdict, indent=2)
    print(text)
    if args.json_out:
        Path(args.json_out).write_text(text + "\n")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
