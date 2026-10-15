"""A GPU VRAM-slice lease over the agent-next REST API, standard library only.

A lease is a disposable RTX 5090 slice: `POST /sandboxes` with an `accel`
body returns a `gl-...` id, `POST /sandboxes/{id}/exec` runs Python whose
`report` dict comes back in the reply, files under `~` persist between exec
calls, and `DELETE` ends it (confirmed gone by a `GET` that answers 404 or
`phase == "dead"`). There is no network inside the lease, so everything a job
needs is uploaded through exec payloads, base64 in the `code` string.

    lease = Lease(vram_gb=4)
    try:
        lease.upload_dir("wheelhouse", "~/wheelhouse")
        report = lease.exec(JOB, timeout_s=600)["report"]
    finally:
        lease.close()
"""

import base64
import io
import json
import os
import tarfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = "https://api.sbx.agent-next.com"


class LeaseError(RuntimeError):
    """The API refused, the job failed, or cleanup could not be confirmed."""


def _valid_sid(sid):
    return isinstance(sid, str) and sid.startswith("gl-") and all(
        c.isascii() and (c.isalnum() or c == "-") for c in sid
    )


class Lease:
    """One owned lease. `close()` is mandatory; use try/finally."""

    def __init__(self, key=None, vram_gb=4, api=API, retries=5, retry_wait_s=15):
        self.key = key or os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
        if not self.key:
            raise LeaseError("export SBX_API_KEY (a key with GPU access)")
        self.api = api
        # 409 is what a contended or capacity-limited GPU pool answers, and it
        # clears on its own; 5xx is a gateway still coming up. Neither is fatal,
        # and a caller that gave up on either would never have a lease at all.
        status, created = 0, None
        for attempt in range(retries + 1):
            status, created = self._request("POST", "/sandboxes", {
                "accel": {"vram_gb": int(vram_gb), "reserve": "exec"},
            })
            if status == 201 and isinstance(created, dict):
                break
            if status not in (409, 429) and status < 500:
                break
            if attempt < retries:
                time.sleep(retry_wait_s)
        if status != 201 or not isinstance(created, dict):
            raise LeaseError(f"GPU create: HTTP {status} after {retries + 1} attempts; "
                             "check GPU access, credit and capacity")
        self.sid = created.get("sandboxID")
        if not _valid_sid(self.sid):
            raise LeaseError(f"GPU create returned an invalid lease id {self.sid!r}; "
                             "it was not destroyed automatically")
        self.closed = False

    def _request(self, method, path, body=None, timeout=900):
        data = None if body is None else json.dumps(body).encode()
        req = Request(self.api + path, data=data, method=method, headers={
            "X-API-Key": self.key, "Content-Type": "application/json",
        })
        try:
            with urlopen(req, timeout=timeout) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except HTTPError as exc:
            return exc.code, None
        except URLError as exc:
            raise LeaseError(f"API unreachable: {exc.reason}") from exc

    def exec(self, code, timeout_s=600, retries=4):
        """Run Python on the lease; returns the `result` dict (report/stdout/stderr/ok).

        A 409/429/5xx from the gateway (a lease still resuming, a transient drop,
        contention on the exec slot) is retried; an `ok: False` in the result is
        a job failure, not retried.
        """
        if self.closed:
            raise LeaseError("lease is closed")
        for attempt in range(retries + 1):
            status, executed = self._request("POST", f"/sandboxes/{self.sid}/exec", {
                "code": code, "timeout_s": int(timeout_s),
            })
            if status == 200 and isinstance(executed, dict):
                result = executed.get("result") or {}
                result.setdefault("ok", False)
                return result
            if status not in (409, 429) and status < 500:
                raise LeaseError(f"GPU exec: HTTP {status}")
            if attempt == retries:
                raise LeaseError(f"GPU exec: HTTP {status} after {retries + 1} attempts")
            time.sleep(min(5 * (attempt + 1), 30))
        raise LeaseError("unreachable")

    def upload_tar(self, tar_bytes, dest="~/payload", chunk_bytes=4 * 1024 * 1024):
        """Upload a .tar.gz payload in base64 chunks, extract to `dest` on the lease.

        Each exec call decodes one chunk and appends it to a staging file; a
        final exec untars. Returns (chunk_count, seconds).
        """
        t0 = time.monotonic()
        b64 = base64.b64encode(tar_bytes).decode()
        chunks = max(1, (len(b64) + chunk_bytes - 1) // chunk_bytes)
        for i in range(chunks):
            piece = b64[i * chunk_bytes:(i + 1) * chunk_bytes]
            code = (
                "import base64, os\n"
                "os.makedirs(os.path.expanduser('~/.uploads'), exist_ok=True)\n"
                f"with open(os.path.expanduser('~/.uploads/payload.b64'), {'w' if i == 0 else 'a'!r}) as f:\n"
                f"    f.write({piece!r})\n"
                f"report['chunk'] = {i}\n"
            )
            r = self.exec(code, timeout_s=600)
            if not r.get("ok"):
                raise LeaseError(f"upload chunk {i}/{chunks} failed: {r.get('stderr', '')[-300:]}")
        code = (
            "import base64, os, tarfile\n"
            "dest = os.path.expanduser(%r)\n"
            "os.makedirs(dest, exist_ok=True)\n"
            "with open(os.path.expanduser('~/.uploads/payload.b64'), 'rb') as f:\n"
            "    tarfile.open(fileobj=__import__('io').BytesIO(base64.b64decode(f.read())), mode='r:gz').extractall(dest)\n"
            "os.remove(os.path.expanduser('~/.uploads/payload.b64'))\n"
            "report['dest'] = dest\n"
            "report['files'] = sorted(os.listdir(dest))[:50]\n" % dest
        )
        r = self.exec(code, timeout_s=600)
        if not r.get("ok"):
            raise LeaseError(f"untar failed: {r.get('stderr', '')[-300:]}")
        return chunks, time.monotonic() - t0

    def upload_dir(self, local_dir, dest, chunk_bytes=4 * 1024 * 1024):
        """Tar.gz `local_dir`'s *contents* and upload to `dest` on the lease."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            for name in sorted(os.listdir(local_dir)):
                tf.add(os.path.join(local_dir, name), arcname=name)
        return self.upload_tar(buf.getvalue(), dest=dest, chunk_bytes=chunk_bytes)

    def close(self, confirm_wait_s=60):
        """DELETE the lease and confirm it is gone. Idempotent."""
        if self.closed:
            return
        self.closed = True
        try:
            self._request("DELETE", f"/sandboxes/{self.sid}")
        except Exception:
            pass  # a lost destroy reply may still mean the lease was released
        deadline = time.monotonic() + confirm_wait_s
        last = None
        while True:
            status, remaining = self._request("GET", f"/sandboxes/{self.sid}")
            if status == 404 or (
                status == 200 and isinstance(remaining, dict) and remaining.get("phase") == "dead"
            ):
                return True
            last = status
            if time.monotonic() >= deadline:
                raise LeaseError(f"cleanup unconfirmed for {self.sid}: HTTP {last}")
            time.sleep(2)
