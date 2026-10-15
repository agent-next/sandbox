"""The canonical nightly run and its independent aggregate oracle.

Two things live here, deliberately kept apart:

* `run_oracle(date, csv_path)` — the judge's own answer, computed by a
  *sqlite3* pass (a text query handed to the pinned sqlite3 CLI, parsed back
  out) over a table imported from the fixture.  It shares no code with
  `digest.py`, so a digester bug cannot hide in the oracle.
* `run_night(...)` — the canonical
  `sleep_until_fire -> resume -> digest -> collect -> pause` sequence the
  artifact's `schedule.json` must agree with.  `resume`/`pause` go through the
  replaceable transport in `transport.py`, so the lifecycle — including the
  sandbox state the judge reads between fires — is exercised without any
  cloud sandbox or bill.

Stdlib only.  Deterministic: no clocks are read for any graded number.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transport import write_state  # noqa: E402  (judge-local helper)

# The exact digest key set the artifact must produce (SPEC "Artifact").
DIGEST_KEYS = {
    "date", "status", "events", "errors", "server_errors", "error_rate",
    "mean_ms", "p50_ms", "p95_ms", "max_ms", "projects", "busiest_project",
}

# Pinned fixture nights: (log date, fire date, fixture file).
NIGHTS = [
    ("2026-10-12", "2026-10-13", "night1.csv"),
    ("2026-10-13", "2026-10-14", "night2.csv"),
    ("2026-10-14", "2026-10-15", "night3.csv"),
]

# The canonical lifecycle steps, in order.
STEPS = ["sleep_until_fire", "resume", "digest", "collect", "pause"]


class OracleError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# the oracle
# --------------------------------------------------------------------------
def _nearest_rank_offset(q: float, n: int) -> int:
    """0-based SQL `OFFSET` of the nearest-rank percentile: ceil(q*n) - 1."""
    if n <= 0:
        return 0
    return max(0, math.ceil(q * n) - 1)


def sqlite3_binary() -> str:
    """The sqlite3 CLI the oracle runs: the copy `judge/setup.sh` pinned into
    `$HOME`, else whatever is on PATH."""
    pinned = Path.home() / ".scheduled-agent-digest" / "bin" / "sqlite3"
    if pinned.is_file() and os.access(pinned, os.X_OK):
        return str(pinned)
    return "sqlite3"


def run_oracle(date: str, csv_path: Path, sqlite3: str | None = None) -> dict:
    """The judge's independent digest for one (date, log) pair.

    Computed by importing the CSV into an in-memory sqlite3 table with the
    pinned sqlite3 CLI; the aggregates, the per-project grouping and both
    percentiles are SQL expressions.  Nothing here is shared with the
    artifact's `digest.py`.
    """
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise OracleError(f"fixture log missing: {csv_path}")
    if sqlite3 is None:
        sqlite3 = sqlite3_binary()
    n = _count_day_rows(date, csv_path, sqlite3)
    offsets = {"p50_ms": _nearest_rank_offset(0.50, n),
               "p95_ms": _nearest_rank_offset(0.95, n)}
    where = f"substr(ts,1,10) = '{date}'"
    script = "\n".join([
        "CREATE TABLE e(ts TEXT, project TEXT, ms INTEGER, code INTEGER);",
        ".mode csv",
        f".import --skip 1 {csv_path} e",
        ".mode list",
        ".separator |",
        "SELECT 'day', COUNT(*), SUM(CASE WHEN code >= 400 THEN 1 ELSE 0 END),",
        "       SUM(CASE WHEN code >= 500 THEN 1 ELSE 0 END),",
        f"       printf('%.3f', AVG(ms)),",
        f"       (SELECT ms FROM e WHERE {where} ORDER BY ms LIMIT 1 OFFSET {offsets['p50_ms']}),",
        f"       (SELECT ms FROM e WHERE {where} ORDER BY ms LIMIT 1 OFFSET {offsets['p95_ms']}),",
        f"       MAX(ms) FROM e WHERE {where};",
        f"SELECT project, COUNT(*), SUM(CASE WHEN code >= 400 THEN 1 ELSE 0 END)",
        f"  FROM e WHERE {where} GROUP BY project ORDER BY project;",
    ])
    out = _sqlite3(sqlite3, script)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    if not lines:
        raise OracleError(f"sqlite3 returned no rows for {csv_path}")
    head = lines[0].split("|")
    if len(head) != 8 or head[0] != "day":
        raise OracleError(f"sqlite3 day row malformed: {lines[0]!r}")
    projects = {}
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) != 3:
            raise OracleError(f"sqlite3 project row malformed: {line!r}")
        projects[parts[0]] = {"events": int(parts[1]), "errors": int(parts[2])}
    events = int(head[1])
    busiest = min(projects.items(), key=lambda kv: (-kv[1]["events"], kv[0]))[0] \
        if projects else ""
    def num(text: str) -> int:
        """SUM() over zero rows is NULL in sqlite — read it as 0."""
        return 0 if text in ("", "NULL") else int(text)

    errors = num(head[2])
    return {
        "date": date,
        "status": "ok" if events else "no events",
        "events": events,
        "errors": errors,
        "server_errors": num(head[3]),
        # error_rate = errors / events, computed here rather than in SQL so
        # the artifact's rounded value is compared to a rounded ratio
        "error_rate": round(errors / events, 6) if events else 0.0,
        "mean_ms": float(head[4]) if events else 0.0,
        "p50_ms": num(head[5]),
        "p95_ms": num(head[6]),
        "max_ms": num(head[7]),
        "projects": projects,
        "busiest_project": busiest,
    }


def _count_day_rows(date: str, csv_path: Path, sqlite3: str = "sqlite3") -> int:
    """Row count for `date` — a separate, cheap SQL count."""
    script = "\n".join([
        "CREATE TABLE e(ts TEXT, project TEXT, ms INTEGER, code INTEGER);",
        ".mode csv",
        f".import --skip 1 {Path(csv_path)} e",
        "SELECT COUNT(*) FROM e WHERE substr(ts,1,10) = "
        f"'{date}';",
    ])
    out = _sqlite3(sqlite3, script).strip()
    try:
        return int(out)
    except ValueError as exc:
        raise OracleError(f"sqlite3 count not a number: {out!r}") from exc


def _sqlite3(binary: str, script: str) -> str:
    proc = subprocess.run([binary, ":memory:"], input=script, text=True,
                          capture_output=True)
    if proc.returncode != 0:
        raise OracleError(f"sqlite3 failed (exit {proc.returncode}): "
                          f"{proc.stderr.strip()[:400]}")
    return proc.stdout


# --------------------------------------------------------------------------
# the canonical run
# --------------------------------------------------------------------------
def run_night(*, log: Path, date: str, fire_on: str, workdir: Path,
              transport, python: str = sys.executable,
              poster=None, journal: Path | None = None,
              state_path: Path | None = None) -> dict:
    """Run one night: sleep, resume, digest, collect, pause.

    `transport` supplies `resume()`, `pause()` and `state()`; the caller owns
    what those mean (a local sleep, or an sbx shim).  Returns the record the
    judge grades, appends it to `journal` when given, and keeps `state_path`
    — the state file read between fires — current.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    record = {"night": date, "fire_on": fire_on, "log": str(log)}

    # sleep_until_fire: the host-side timer.  Deterministic in the grader —
    # the real wait is the transport's business.
    transport.wait_for_fire(fire_on)
    record["fired_at"] = fire_on

    transport.resume()
    record["state_after_resume"] = transport.state()

    digest_path = workdir / f"digest-{date}.json"
    proc = subprocess.run(
        [python, "-I", "digest.py", "--log", str(log), "--date", date,
         "--out", str(digest_path)],
        capture_output=True, text=True, cwd=str(workdir))
    record["exit_code"] = proc.returncode
    record["stderr"] = proc.stderr.strip()[-400:]
    if proc.returncode != 0:
        raise OracleError(f"digest.py failed for {log} (exit "
                          f"{proc.returncode}): {record['stderr']}")
    record["digest"] = str(digest_path)
    record["digest_sha256"] = _sha(digest_path)

    record["state_before_pause"] = transport.state()
    if poster is not None:
        record["posted"] = poster(digest_path)

    transport.pause()
    record["state_after_pause"] = transport.state()
    # the state a human (or the judge) would see between two fires
    record["state_between_runs"] = transport.state()
    if state_path is not None:
        record["state_file"] = str(state_path)
        write_state(state_path, transport.state(), night=date,
                    fire_on=fire_on, sandbox=transport.sandbox_id)

    if journal is not None:
        journal = Path(journal)
        journal.parent.mkdir(parents=True, exist_ok=True)
        with open(journal, "a") as fh:
            fh.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
