"""Offline lifecycle tests for the media runner, no GPU or credentials required."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import frames  # noqa: E402


class FramesTests(unittest.TestCase):
    def test_job_writes_the_checkpoint_exec_recovery_polls(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            with tarfile.open(out / "source.tgz", "w:gz") as tar:
                tar.addfile(tarfile.TarInfo("judge/empty"), io.BytesIO(b""))
            done = subprocess.CompletedProcess([], 0, "", "")
            with patch("subprocess.run", return_value=done):
                exec(frames.job(17, None), {"OUTPUT_DIR": str(out), "report": {}})
            result = json.loads((out / "job-result.json").read_text())["result"]
            self.assertTrue(result["ok"])
            self.assertEqual([row["exit"] for row in result["report"]["steps"]], [0, 0])

    def test_lost_delete_reply_still_confirms_with_get(self):
        calls = []
        def request(key, method, path, body=None):
            calls.append((method, path))
            if method == "DELETE":
                raise OSError("reply lost")
            if method == "GET" and path == "/sandboxes/gl-test-1":
                return 404, b""
            if path.endswith("/files"):
                return 200, b'{"files": []}'
            return 200, b"{}"
        def json_request(key, method, path, body=None):
            status, data = request(key, method, path, body)
            return {"sandboxID": "gl-test-1"} if method == "POST" else json.loads(data)
        ok = {"result": {"ok": True, "report": {"image_numpy": "2.2.6",
                                                 "steps": [{"exit": 0}]}}}
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(sys, "argv", ["frames.py", str(Path(temp) / "out")]), \
             patch.dict("os.environ", {"SBX_API_KEY": "test"}), \
             patch.object(frames.run, "request", side_effect=request), \
             patch.object(frames.run, "json_request", side_effect=json_request), \
             patch.object(frames.run, "execute", return_value=ok), \
             patch.object(frames.run, "upload_part"), \
             patch.object(frames.run, "dependencies", return_value={"m.tgz": b"m"}):
            frames.main()
        self.assertEqual(calls[-2:], [("DELETE", "/sandboxes/gl-test-1"),
                                      ("GET", "/sandboxes/gl-test-1")])


if __name__ == "__main__":
    unittest.main()
