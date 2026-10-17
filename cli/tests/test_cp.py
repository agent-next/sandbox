import sys
import types
from unittest.mock import Mock

import pytest

from sbx import cli


class NotFound(Exception):
    pass


@pytest.fixture
def sdk(monkeypatch):
    sandbox = Mock()
    sandbox.connect.return_value.files.get_info.return_value.type = "file"
    monkeypatch.setitem(sys.modules, "e2b", types.SimpleNamespace(
        Sandbox=sandbox, NotFoundException=NotFound,
    ))
    monkeypatch.setenv("E2B_API_KEY", "e2b_test_copy_secret")
    monkeypatch.delenv("SBX_API_KEY", raising=False)
    monkeypatch.delenv("E2B_DOMAIN", raising=False)
    return sandbox


@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 4096 + b"e2b_test_copy_secret"])
def test_upload_preserves_every_byte(sdk, tmp_path, capsys, data):
    source = tmp_path / "source with spaces:1.bin"
    source.write_bytes(data)
    files = sdk.connect.return_value.files
    files.get_info.side_effect = NotFound("destination does not exist")

    assert cli.main(["cp", str(source), "sbx-1:/tmp/remote file:1.bin"]) == 0

    sdk.connect.assert_called_once_with("sbx-1")
    files.write.assert_called_once_with("/tmp/remote file:1.bin", data)
    assert source.read_bytes() == data
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 4096 + b"e2b_test_copy_secret"])
def test_download_preserves_every_byte_and_overwrites(sdk, tmp_path, capsys, data):
    target = tmp_path / "download with spaces:1.bin"
    target.write_bytes(b"old content that must be replaced")
    files = sdk.connect.return_value.files
    files.read.return_value = data

    assert cli.main(["cp", "sbx-1:/tmp/remote file:1.bin", str(target)]) == 0

    sdk.connect.assert_called_once_with("sbx-1")
    files.read.assert_called_once_with("/tmp/remote file:1.bin", format="bytes")
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
    files.get_info.return_value.type = "dir"
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
    sdk.connect.return_value.files.write.assert_called_once_with("relative:1.bin", b"data")
    assert cli.os.environ["E2B_API_KEY"] == "alternative_copy_key"


def test_local_write_error_is_handled(sdk, tmp_path, capsys):
    target = tmp_path / "missing-parent" / "file.bin"
    sdk.connect.return_value.files.read.return_value = b"data"

    assert cli.main(["cp", "sbx-1:/tmp/file.bin", str(target)]) == 2
    assert "cp:" in capsys.readouterr().err
    assert not target.exists()
