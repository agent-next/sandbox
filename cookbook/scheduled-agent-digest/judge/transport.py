"""Replaceable sandbox lifecycle transport for the nightly digest run.

The demo's point is the *lifecycle* — wake on a timer, work, pause, pay
nothing while idle — not a particular sandbox API.  So `resume`/`pause` (and
the state read between fires) sit behind one small interface, and the judge
grades the lifecycle through it:

* `PausedSleepTransport` (the default) simulates the pause by sleeping and
  tracks the sandbox state itself.  The demo then grades the whole cycle —
  including state transitions — with no cloud sandbox, no API key and no
  bill, in a couple of seconds on 2 vCPU.
* `sbx_resume` / `sbx_pause` are thin shims that adapt an `sbx`-shaped client
  (anything with `connect(id)` and `pause(id)`) to the same interface.  The
  judge drives them with a fake client, so the wiring is proven too.  A real
  run wires them to the `sbx` CLI exactly as `run.py` does.

A transport is an object with `resume()`, `pause()`, `state()` and
`wait_for_fire(when)`.  Nothing else in the demo knows which one is in use.
"""

from __future__ import annotations

import time
from pathlib import Path

RUNNING = "running"
PAUSED = "paused"

# how long `wait_for_fire` actually sleeps; the whole point of the demo is
# that this wait costs nothing on the sandbox
PAUSE_SLEEP_SECONDS = 0.05


class TransportError(RuntimeError):
    pass


class PausedSleepTransport:
    """Local transport: the sandbox "pauses" by sleeping instead of running.

    It records every transition with the wall clock, so the judge can check
    the *order* of states (running during a fire, paused between fires) as
    well as the states themselves.
    """

    def __init__(self, *, sandbox_id="local-sandbox",
                 pause_seconds=PAUSE_SLEEP_SECONDS, clock=time.monotonic):
        self._state = PAUSED
        self.sandbox_id = sandbox_id
        self.pause_seconds = pause_seconds
        self._clock = clock
        self.history: list[tuple[str, float, str]] = []

    def wait_for_fire(self, when: str) -> None:
        """The host-side timer fires; nothing runs in the sandbox while it
        waits, which is exactly what the pause is for."""
        self._record("timer", f"scheduled {when}")

    def resume(self) -> None:
        if self._state == RUNNING:
            raise TransportError("resume() on an already running sandbox")
        self._state = RUNNING
        self._record(RUNNING, "resumed for the fire")

    def pause(self) -> None:
        if self._state == PAUSED:
            raise TransportError("pause() on an already paused sandbox")
        self._state = PAUSED
        self._record(PAUSED, f"paused for {self.pause_seconds:g}s")
        if self.pause_seconds:
            time.sleep(self.pause_seconds)

    def state(self) -> str:
        return self._state

    def _record(self, state: str, note: str) -> None:
        self.history.append((state, self._clock(), note))


def sbx_resume(client, sandbox_id: str) -> None:
    """Bring an `sbx` sandbox back: connect to it again (the SDK resumes a
    paused sandbox on the next call) and report what it now is."""
    client.connect(sandbox_id)
    client.pause(sandbox_id, resume=True)
    return None


def sbx_pause(client, sandbox_id: str) -> None:
    """Pause an `sbx` sandbox so it stops costing anything until the next fire."""
    client.pause(sandbox_id)
    return None


class FakeSbxClient:
    """A recording stand-in for the `sbx`-shaped client, used by the judge's
    lifecycle gate to prove the shims above drive a real client contract."""

    def __init__(self):
        self.paused = True
        self.calls: list[str] = []
        self.connected = 0

    def connect(self, sandbox_id: str):
        # connecting to a paused sandbox is what resumes it
        self.paused = False
        self.connected += 1
        self.calls.append(f"connect {sandbox_id}")
        return None

    def pause(self, sandbox_id: str, resume: bool = False) -> None:
        self.paused = not resume
        self.calls.append(f"{'resume' if resume else 'pause'} {sandbox_id}")
        return None


def write_state(path: Path, state: str, **extra) -> dict:
    """Write `state.json` — the state file the judge reads between fires."""
    import json

    record = {"state": state, **extra}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True) + "\n")
    return record


def read_state(path: Path) -> str:
    import json

    path = Path(path)
    if not path.is_file():
        raise TransportError(f"no state file at {path}")
    try:
        return json.loads(path.read_text())["state"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TransportError(f"{path} is not a state file: {exc}") from exc
