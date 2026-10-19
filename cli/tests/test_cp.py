import enum
import sys
import types
from unittest.mock import Mock

import httpx
import pytest

from sbx import cli


class FileType(enum.Enum):
    """Mirrors e2b.FileType: a plain Enum, so FileType.DIR != "dir"."""
    FILE = "file"
    DIR = "dir"


class NotFound(Exception):
    pass


class SandboxNotFound(NotFound):
    """The SDK's connect-by-id 404, a NotFoundException (see test_sdk_contract)."""


class Timeout(Exception):
    pass


class InvalidArgument(Exception):
    pass


@pytest.fixture
def sdk(monkeypatch):
    sandbox = Mock()
    sandbox.connect.return_value.files.get_info.return_value.type = FileType.FILE
    monkeypatch.setitem(sys.modules, "e2b", types.SimpleNamespace(
        Sandbox=sandbox, NotFoundException=NotFound, SandboxNotFoundException=SandboxNotFound,
        InvalidArgumentException=InvalidArgument, FileType=FileType,
        TimeoutException=Timeout,
    ))
    monkeypatch.setenv("E2B_API_KEY", "e2b_test_copy_secret")
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.delenv("E2B_DOMAIN", raising=False)
    return sandbox


@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 4096 + b"e2b_test_copy_secret"],
                         ids=["empty", "all-bytes"])
def test_upload_preserves_every_byte(sdk, tmp_path, capsys, data):
    source = tmp_path / "source with spaces:1.bin"
    source.write_bytes(data)
    files = sdk.connect.return_value.files
    files.get_info.side_effect = NotFound("destination does not exist")

    assert cli.main(["cp", str(source), "sbx-1:/tmp/remote file:1.bin"]) == 0

    sdk.connect.assert_called_once_with("sbx-1")
    files.write.assert_called_once_with("/tmp/remote file:1.bin", data, request_timeout=600)
    assert source.read_bytes() == data
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 4096 + b"e2b_test_copy_secret"],
                         ids=["empty", "all-bytes"])
def test_download_preserves_every_byte_and_overwrites(sdk, tmp_path, capsys, data):
    target = tmp_path / "download with spaces:1.bin"
    target.write_bytes(b"old content that must be replaced")
    files = sdk.connect.return_value.files
    files.read.return_value = data

    assert cli.main(["cp", "sbx-1:/tmp/remote file:1.bin", str(target)]) == 0

    sdk.connect.assert_called_once_with("sbx-1")
    files.read.assert_called_once_with("/tmp/remote file:1.bin", format="bytes", request_timeout=600)
    assert target.read_bytes() == data
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("source,target", [
    ("local.bin", "other.bin"),
    ("sbx-1:/a", "sbx-2:/b"),
    (":/a", "local.bin"),
    ("local.bin", ":/b"),
    ("sbx-1:", "local.bin"),
    ("local.bin", "sbx-1:"),
    ("", "sbx-1:/b"),
    ("sbx-1:/a", ""),
])
def test_invalid_endpoints_are_usage_errors(sdk, capsys, source, target):
    assert cli.main(["cp", source, target]) == 2
    assert "cp:" in capsys.readouterr().err
    sdk.connect.assert_not_called()


@pytest.mark.parametrize("args", [[], ["local.bin"], ["a", "b", "c"]])
def test_wrong_argument_count_is_a_usage_error(sdk, capsys, args):
    with pytest.raises(SystemExit) as exc:
        cli.main(["cp", *args])
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err
    sdk.connect.assert_not_called()


@pytest.mark.parametrize("upload", [True, False])
def test_local_directories_are_rejected(sdk, tmp_path, capsys, upload):
    endpoints = [str(tmp_path), "sbx-1:/tmp/file.bin"]
    assert cli.main(["cp", *(endpoints if upload else endpoints[::-1])]) == 2
    assert "directories are not supported" in capsys.readouterr().err
    sdk.connect.assert_not_called()


@pytest.mark.parametrize("upload", [True, False])
def test_remote_directories_are_rejected_without_copying(sdk, tmp_path, capsys, upload):
    local = tmp_path / "local.bin"
    local.write_bytes(b"keep this content")
    files = sdk.connect.return_value.files
    files.get_info.return_value.type = FileType.DIR
    endpoints = [str(local), "sbx-1:/tmp"]

    assert cli.main(["cp", *(endpoints if upload else endpoints[::-1])]) == 2
    assert "directories are not supported" in capsys.readouterr().err
    files.read.assert_not_called()
    files.write.assert_not_called()
    assert local.read_bytes() == b"keep this content"


@pytest.mark.parametrize("remote", [True, False])
@pytest.mark.parametrize("upload", [True, False])
def test_directory_syntax_is_rejected_even_when_missing(sdk, tmp_path, capsys, remote, upload):
    local = tmp_path / "local.bin"
    local.write_bytes(b"keep this content")
    endpoints = [str(local) if remote else str(tmp_path / "missing") + "/",
                 "sbx-1:/tmp/missing/" if remote else "sbx-1:/tmp/file.bin"]

    assert cli.main(["cp", *(endpoints if upload else endpoints[::-1])]) == 2
    assert "directories are not supported" in capsys.readouterr().err
    sdk.connect.assert_not_called()


def test_missing_local_source_is_a_usage_error(sdk, tmp_path, capsys):
    assert cli.main(["cp", str(tmp_path / "missing.bin"), "sbx-1:/tmp/file.bin"]) == 2
    assert "cp:" in capsys.readouterr().err
    sdk.connect.assert_not_called()


def test_missing_remote_source_preserves_local_target(sdk, tmp_path, capsys):
    target = tmp_path / "target.bin"
    target.write_bytes(b"keep this content")
    sdk.connect.return_value.files.get_info.side_effect = NotFound("file not found")

    assert cli.main(["cp", "sbx-1:/tmp/missing.bin", str(target)]) == 2
    assert "not found" in capsys.readouterr().err
    assert target.read_bytes() == b"keep this content"


@pytest.mark.parametrize("upload,stage", [
    (True, "get_info"), (False, "get_info"), (True, "write"), (False, "read"),
])
def test_sdk_directory_errors_are_handled(sdk, tmp_path, capsys, upload, stage):
    local = tmp_path / "local.bin"
    local.write_bytes(b"keep this content")
    getattr(sdk.connect.return_value.files, stage).side_effect = InvalidArgument(
        "path is a directory: /tmp",
    )
    endpoints = [str(local), "sbx-1:/tmp"]

    assert cli.main(["cp", *(endpoints if upload else endpoints[::-1])]) == 2
    assert "path is a directory" in capsys.readouterr().err
    assert local.read_bytes() == b"keep this content"


@pytest.mark.parametrize("stage", ["connect", "get_info", "read", "write"])
def test_sdk_failures_exit_one_and_redact_secrets(sdk, tmp_path, capsys, stage):
    local = tmp_path / "local.bin"
    local.write_bytes(b"keep this content")
    files = sdk.connect.return_value.files
    operation = sdk.connect if stage == "connect" else getattr(files, stage)
    operation.side_effect = RuntimeError("service failed for e2b_test_copy_secret")
    endpoints = [str(local), "sbx-1:/tmp/file.bin"]

    assert cli.main(["cp", *(endpoints if stage == "write" else endpoints[::-1])]) == 1
    err = capsys.readouterr().err
    assert "e2b_test_copy_secret" not in err and "[redacted]" in err
    assert local.read_bytes() == b"keep this content"


def test_missing_key_is_a_usage_error(sdk, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("E2B_API_KEY")
    source = tmp_path / "local.bin"
    source.write_bytes(b"data")

    assert cli.main(["cp", str(source), "sbx-1:/tmp/file.bin"]) == 2
    assert "no API key" in capsys.readouterr().err
    sdk.connect.assert_not_called()


def test_sbx_api_key_and_relative_paths_are_supported(sdk, tmp_path, monkeypatch):
    monkeypatch.delenv("E2B_API_KEY")
    monkeypatch.setenv("SBX_API_KEY", "alternative_copy_key")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "local:1.bin").write_bytes(b"data")

    assert cli.main(["cp", "./local:1.bin", "sbx-1:relative:1.bin"]) == 0
    sdk.connect.return_value.files.write.assert_called_once_with("relative:1.bin", b"data", request_timeout=600)
    assert cli.os.environ["E2B_API_KEY"] == "alternative_copy_key"


@pytest.mark.parametrize("upload", [True, False])
def test_timeout_flag_sets_the_transfer_deadline(sdk, tmp_path, upload):
    local = tmp_path / "file.bin"
    local.write_bytes(b"data")
    files = sdk.connect.return_value.files
    files.read.return_value = b"data"
    endpoints = [str(local), "sbx-1:/tmp/file.bin"]

    assert cli.main(["cp", "--timeout", "1800", *(endpoints if upload else endpoints[::-1])]) == 0
    call = files.write if upload else files.read
    assert call.call_args.kwargs["request_timeout"] == 1800


@pytest.mark.parametrize("value", ["0", "-5", "nan"])
def test_timeout_flag_rejects_non_positive_values(sdk, tmp_path, capsys, value):
    assert cli.main(["cp", "--timeout", value, str(tmp_path / "f"), "sbx-1:/tmp/f"]) == 2
    assert "--timeout" in capsys.readouterr().err
    sdk.connect.assert_not_called()


def test_file_calls_retry_while_the_gateway_restarts(sdk, tmp_path, monkeypatch):
    # the SDK's text for an envd 503 (see test_restart_wait_reads_the_sdk_file_call_error)
    restarting = Exception('{"code":"restarting","retry_after_s":5}: This error is likely due to sandbox timeout.')
    local = tmp_path / "file.bin"
    local.write_bytes(b"data")
    files = sdk.connect.return_value.files
    files.get_info.side_effect = [restarting, NotFound("no such file")]
    files.write.side_effect = [restarting, None]
    sleeps = []
    monkeypatch.setattr(cli.time, "sleep", sleeps.append)

    assert cli.main(["cp", str(local), "sbx-1:/tmp/file.bin"]) == 0
    assert files.get_info.call_count == 2 and files.write.call_count == 2
    assert sleeps == [5, 5]


@pytest.mark.parametrize("error", [
    Timeout("Request timed out \u2014 the 'request_timeout' option can be used to increase this timeout"),
    httpx.ReadTimeout("timed out"),
], ids=["sdk-request-timeout", "httpx-read-timeout"])
@pytest.mark.parametrize("upload", [True, False])
def test_transfer_timeout_names_the_flag(sdk, tmp_path, capsys, upload, error):
    local = tmp_path / "file.bin"
    local.write_bytes(b"data")
    files = sdk.connect.return_value.files
    files.get_info.side_effect = NotFound("no such file") if upload else None
    (files.write if upload else files.read).side_effect = error
    endpoints = [str(local), "sbx-1:/tmp/file.bin"]

    assert cli.main(["cp", "--timeout", "45", *(endpoints if upload else endpoints[::-1])]) == 2
    assert "--timeout 45" in capsys.readouterr().err


def test_sandbox_expiry_is_not_reported_as_the_transfer_deadline(sdk, tmp_path, capsys):
    local = tmp_path / "file.bin"
    local.write_bytes(b"data")
    files = sdk.connect.return_value.files
    files.get_info.side_effect = NotFound("no such file")
    files.write.side_effect = Timeout("sandbox gone: This error is likely due to sandbox timeout.")

    assert cli.main(["cp", "--timeout", "45", str(local), "sbx-1:/tmp/file.bin"]) != 0
    assert "--timeout 45" not in capsys.readouterr().err


def test_local_write_error_is_handled(sdk, tmp_path, capsys):
    target = tmp_path / "missing-parent" / "file.bin"
    sdk.connect.return_value.files.read.return_value = b"data"

    assert cli.main(["cp", "sbx-1:/tmp/file.bin", str(target)]) == 2
    assert "cp:" in capsys.readouterr().err
    assert not target.exists()
