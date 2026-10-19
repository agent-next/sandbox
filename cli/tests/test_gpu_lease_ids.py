"""A CPU-plane verb given a GPU lease id must redirect, not misreport (G1).

On the live service (2026-10-19 launch test, finding G1) `sbx cp` and
`sbx exec` against a lease that `sbx gpu list` showed running answered
"cp: Paused sandbox gl-334c38-34 not found" and "exec: sandbox gl-334c38-34
not found (it was killed, expired, or the id is wrong)" — the first commands
a new user types after `sbx gpu create`, because the CPU quickstart taught
them `sbx exec "$id" ...`. Lease ids (gl-..., the namespace `sbx gpu
create` prints) live on the lease plane, so exec and cp must say so instead
of reporting a live lease as a missing CPU sandbox.
"""

import enum
import sys
import time
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

from sbx import cli

REPO = Path(__file__).resolve().parents[2]
README = REPO / "cli/README.md"

LEASE = "gl-334c38-34"  # the live lease id from the finding


class _NotFound(Exception):
    pass


class FileType(enum.Enum):
    FILE = "file"
    DIR = "dir"


@pytest.fixture
def cpu_plane(monkeypatch):
    """A CPU plane that, asked for a lease id, answers the way the live
    service answered in the finding — while recording that it was asked."""
    asked = []

    class Sandbox:
        @classmethod
        def connect(cls, sid):
            asked.append(sid)
            raise _NotFound(f"Paused sandbox {sid} not found")

    monkeypatch.setitem(sys.modules, "e2b", types.SimpleNamespace(
        Sandbox=Sandbox, SandboxNotFoundException=_NotFound,
        NotFoundException=_NotFound, TimeoutException=type("Timeout", (Exception,), {}),
        InvalidArgumentException=type("InvalidArgument", (Exception,), {}),
        CommandExitException=type("CommandExit", (Exception,), {}), FileType=FileType,
    ))
    monkeypatch.setenv("E2B_API_KEY", "k-lease-redirect-secret")
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.delenv("E2B_DOMAIN", raising=False)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return asked


def test_exec_on_a_lease_id_redirects_to_gpu_exec(cpu_plane, capsys):
    assert cli.main(["exec", LEASE, "echo hi"]) == 2
    err = capsys.readouterr().err
    assert LEASE in err
    assert "GPU lease" in err
    assert "sbx gpu exec" in err
    # A live lease must not be reported as a missing CPU sandbox.
    assert "not found" not in err
    assert cpu_plane == []


def test_cp_upload_to_a_lease_id_redirects_to_gpu_exec(cpu_plane, tmp_path, capsys):
    local = tmp_path / "up.txt"
    local.write_bytes(b"data")

    assert cli.main(["cp", str(local), f"{LEASE}:/tmp/up.txt"]) == 2
    err = capsys.readouterr().err
    assert LEASE in err
    assert "GPU lease" in err
    assert "sbx gpu exec" in err
    assert "not found" not in err
    assert cpu_plane == []


def test_cp_download_from_a_lease_id_redirects_to_gpu_exec(cpu_plane, tmp_path, capsys):
    assert cli.main(["cp", f"{LEASE}:/tmp/out.txt", str(tmp_path / "out.txt")]) == 2
    err = capsys.readouterr().err
    assert "GPU lease" in err and "sbx gpu exec" in err
    assert "not found" not in err
    assert cpu_plane == []


def test_a_cpu_id_containing_gl_keeps_the_connect_path(cpu_plane, capsys):
    """The redirect is keyed on the lease-id shape the gpu verbs validate,
    not a substring: a CPU sandbox id merely containing "gl-" must keep
    today's not-found wording and exit code."""
    assert cli.main(["exec", "sbx-gl-1", "echo hi"]) == 1
    err = capsys.readouterr().err
    assert "sbx-gl-1" in err and "not found" in err
    # all three create-lag retries (#23) still happen for a CPU id
    assert cpu_plane == ["sbx-gl-1"] * 3


def test_readme_rows_say_lease_ids_do_not_reach_exec_and_cp():
    text = README.read_text(encoding="utf-8")
    rows = {line.split("|")[1].strip().split("[")[0].strip(): line
            for line in text.splitlines()
            if line.startswith("| `sbx exec ID") or line.startswith("| `sbx cp ")}
    assert set(rows) == {"`sbx exec ID", "`sbx cp"}, "exec and cp rows must stay in the table"
    for name, row in rows.items():
        assert "GPU lease" in row, (
            f"cli/README.md's {name} row must say a GPU lease id (gl-...) is "
            "refused with a pointer to `sbx gpu exec` (launch finding G1)"
        )
