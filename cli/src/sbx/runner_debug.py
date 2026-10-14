"""Persistent, account-scoped index of failed runner snapshots."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .cli import SbxError


def state_directory(key: str, endpoint: str) -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    account = hashlib.sha256(f"{endpoint}\0{key}".encode()).hexdigest()[:24]
    return root / "sbx" / "failed-runners" / account


def job_reference(value: str) -> tuple[int, str | None]:
    if re.fullmatch(r"[1-9]\d*", value):
        return int(value), None
    match = re.fullmatch(
        r"https://github\.com/([^/]+/[^/]+)/actions/runs/\d+/(?:job|jobs)/([1-9]\d*)/?", value
    )
    if match:
        return int(match[2]), match[1]
    raise SbxError("debug: give a numeric job id or a GitHub Actions job URL")


class FailedJobs:
    def __init__(self, directory: Path, sandbox_cls):
        self.directory, self.sandbox_cls = Path(directory), sandbox_cls
        self.index = self.directory / "jobs.json"

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.directory / "jobs.lock", os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _read(self) -> list[dict]:
        if not self.index.exists():
            return []
        records = json.loads(self.index.read_text())
        if not isinstance(records, list) or any(
            not isinstance(r, dict) or not {"job_id", "repo", "snapshot_id", "created_at"} <= r.keys()
            for r in records
        ):
            raise SbxError("invalid failed runner index")
        return records

    def _write(self, records: list[dict]) -> None:
        fd, name = tempfile.mkstemp(dir=self.directory, prefix=".jobs-")
        try:
            with os.fdopen(fd, "w") as out:
                json.dump(records, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.index)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def list(self) -> list[dict]:
        with self._locked():
            return sorted(self._read(), key=lambda r: r["created_at"])

    def _find(self, records: list[dict], reference: str) -> dict:
        jid, repo = job_reference(reference)
        matches = [r for r in records if r["job_id"] == jid and (repo is None or r["repo"] == repo)]
        if len(matches) != 1:
            raise SbxError(f"no retained snapshot for job {jid}")
        return matches[0]

    def find(self, reference: str) -> dict:
        with self._locked():
            return self._find(self._read(), reference)

    def delete(self, reference: str) -> dict:
        with self._locked():
            records = self._read()
            record = self._find(records, reference)
            self.sandbox_cls.delete_snapshot(record["snapshot_id"])
            records.remove(record)
            self._write(records)
            return record

    def keep(self, sbx, job: dict, runner: str, *, maximum: int) -> None:
        from .runners import emit

        record = {
            "job_id": job["id"], "job_url": job["html_url"], "repo": job["repo"],
            "sha": job["head_sha"], "runner": runner, "sandbox_id": sbx.sandbox_id,
        }
        with self._locked():
            records = self._read()
            snap = sbx.create_snapshot()
            sid = getattr(snap, "snapshot_id", None) or getattr(snap, "id", None) or str(snap)
            record.update(snapshot_id=sid, created_at=time.time())
            records.append(record)
            try:
                self._write(records)
            except Exception:
                # The snapshot cannot be discovered without the index. Never silently leak it.
                try:
                    self.sandbox_cls.delete_snapshot(sid)
                except Exception as exc:
                    emit("snapshot_cleanup_error", snapshot_id=sid, error=str(exc)[:200])
                raise
            emit("kept_failed", **record)
            records.sort(key=lambda r: r["created_at"])
            while len(records) > maximum:
                oldest = records[0]
                self.sandbox_cls.delete_snapshot(oldest["snapshot_id"])
                records.pop(0)
                self._write(records)
                emit("failed_evicted", **oldest)
