"""Offline REST lifecycle regression tests, no GPU or credentials required."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run


class RunnerTests(unittest.TestCase):
    def args(self, path):
        return argparse.Namespace(keep=False, output=path, seed=17, skip_selftest=False)

    def exercise(self, root, *, exec_failure=False, cleanup_status=404, via_exec=False):
        calls = []
        def request(key, method, path, body=None):
            calls.append((method, path))
            if method == "POST" and path == "/sandboxes":
                self.assertEqual(body["accel"]["template"], "browser")
                return 201, b'{"sandboxID":"gl-test-1"}'
            if method == "PUT" and path.endswith("/upload-probe") and via_exec:
                return 405, b""
            if method == "POST":
                if exec_failure:
                    return 409, b""
                return 200, json.dumps({"result": {"ok": True, "report": {
                    "steps": [{"exit": 0}]}}}).encode()
            if path.endswith("/files"):
                return 200, b'{"files":[{"name":"verdict.json"},{"name":"studio.npy"}]}'
            if path.endswith("/verdict.json"):
                return 200, b'{"pass":true}'
            if path.endswith("/studio.npy"):
                return 200, b"real-buffer-fixture"
            if method == "DELETE":
                return 200, b"{}"
            if method == "GET":
                return cleanup_status, b"{}"
            return 201, b"{}"
        with patch.object(run, "request", side_effect=request), \
             patch.object(run, "dependencies", return_value={"numpy.whl": b"wheel"}), \
             patch.object(run, "source_archive", return_value=b"archive"):
            run.gpu_run(self.args(root), "test")
        return calls

    def test_success_downloads_and_deletes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            calls = self.exercise(output)
            self.assertEqual((output / "studio.npy").read_bytes(), b"real-buffer-fixture")
            self.assertEqual(json.loads((output / "runner.json").read_text())["cleanup_get_status"], 404)
            self.assertEqual(calls[-2:], [("DELETE", "/sandboxes/gl-test-1"),
                                         ("GET", "/sandboxes/gl-test-1")])

    def test_exec_failure_still_deletes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            with self.assertRaisesRegex(RuntimeError, "HTTP 409"):
                self.exercise(output, exec_failure=True)
            self.assertEqual(json.loads((output / "runner.json").read_text())["cleanup_get_status"], 404)

    def test_cleanup_must_be_404(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, "cleanup unconfirmed for gl-test-1"):
                self.exercise(Path(temp) / "output", cleanup_status=200)

    def test_unsafe_download_paths(self):
        for name in ("../secret", "/absolute", "x/../../secret", "x\\secret", ""):
            with self.assertRaisesRegex(RuntimeError, "unsafe"):
                run.safe_output(name)

    def test_keep_rejected_before_creating_lease(self):
        args = self.args(Path("unused"))
        args.keep = True
        with patch.object(run, "request") as request:
            with self.assertRaisesRegex(RuntimeError, "--keep"):
                run.gpu_run(args, "test")
            request.assert_not_called()

    def test_exec_upload_receipt_checked(self):
        result = json.dumps({"result": {"ok": True, "report": {"uploaded_bytes": 3}}}).encode()
        with patch.object(run, "request", return_value=(200, result)) as request:
            run.upload_part("test", "gl-test-1", "chunk", b"abc", via_exec=True)
            method, path, body = request.call_args.args[1:]
            self.assertEqual((method, path), ("POST", "/sandboxes/gl-test-1/exec"))
            self.assertIn("YWJj", body["code"])

    def test_put_stages_under_output_directory(self):
        with patch.object(run, "request", return_value=(200, b"{}")) as request:
            run.upload_part("test", "gl-test-1", "chunk", b"abc")
            self.assertEqual(request.call_args.args[1:],
                             ("PUT", "/sandboxes/gl-test-1/files/out/chunk", b"abc"))

    def test_lost_exec_reply_is_not_replayed(self):
        result = b'{"result":{"ok":true,"report":{"steps":[{"exit":0}]}}}'
        calls = []
        def request(key, method, path, body=None):
            calls.append((method, path))
            return (524, b"") if method == "POST" else (200, result)
        with patch.object(run, "request", side_effect=request):
            self.assertTrue(run.execute("test", "gl-test-1", "job")["result"]["ok"])
        self.assertEqual(sum(method == "POST" for method, _ in calls), 1)

    def test_job_locals_cannot_rebind_worker_canary(self):
        canary = object()
        namespace = {"x": canary, "OUTPUT_DIR": "unused", "report": {}}
        exec(run.isolate("x = 1\nreport['local_x'] = x"), namespace)
        self.assertIs(namespace["x"], canary)
        self.assertEqual(namespace["report"]["local_x"], 1)

    def test_exec_fallback_staging_is_serial(self):
        executor = run.ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(run, "upload_part"), \
             patch.object(run, "ThreadPoolExecutor", wraps=executor) as pools:
            self.exercise(Path(temp) / "output", via_exec=True)
            self.assertTrue(pools.call_args_list)
            self.assertTrue(all(call.kwargs["max_workers"] == 1
                                for call in pools.call_args_list))


if __name__ == "__main__":
    unittest.main()
