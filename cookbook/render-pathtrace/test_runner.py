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

    def exercise(self, root, *, exec_failure=False, cleanup_status=404, via_exec=False,
                 image_numpy="2.2.6", create_replies=None, stall_download=False):
        calls = []
        download_timeouts = []
        def request(key, method, path, body=None, timeout=None):
            calls.append((method, path))
            if method == "GET" and "/files/" in path:
                download_timeouts.append(timeout)
            if method == "POST" and path.endswith("/exec") and "image_numpy" in body["code"]:
                return 200, json.dumps({"result": {"ok": True, "report": {
                    "image_numpy": image_numpy}}}).encode()
            if method == "POST" and path == "/sandboxes":
                self.assertEqual(body["accel"]["template"], "browser")
                if create_replies:
                    return create_replies.pop(0)
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
                if stall_download:
                    raise TimeoutError("The read operation timed out")
                return 200, b"real-buffer-fixture"
            if method == "DELETE":
                return 200, b"{}"
            if method == "GET":
                return cleanup_status, b"{}"
            return 201, b"{}"
        self.calls = calls
        self.download_timeouts = download_timeouts
        with patch.object(run, "request", side_effect=request), \
             patch.object(run, "dependencies", return_value={"mutracer-0.1.1.tgz": b"m"}), \
             patch.object(run, "numpy_wheel", return_value=b"wheel"), \
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

    def test_image_numpy_skips_wheel_upload(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = self.exercise(Path(temp) / "output")
            self.assertFalse([path for method, path in calls
                              if method == "PUT" and path.endswith(".whl")])

    def test_missing_image_numpy_uploads_verified_wheel(self):
        with tempfile.TemporaryDirectory() as temp:
            calls = self.exercise(Path(temp) / "output", image_numpy=None)
            self.assertIn(("PUT", f"/sandboxes/gl-test-1/files/out/{run.WHEEL}"), calls)

    def test_job_without_wheel_uses_image_numpy(self):
        self.assertNotIn("SBX_RENDER_NUMPY_WHEEL", run.job_source(17, None))
        self.assertIn("SBX_RENDER_NUMPY_WHEEL", run.job_source(17, run.WHEEL))

    def test_exec_failure_still_deletes(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            with self.assertRaisesRegex(RuntimeError, "HTTP 409"):
                self.exercise(output, exec_failure=True)
            self.assertEqual(json.loads((output / "runner.json").read_text())["cleanup_get_status"], 404)

    def test_create_honors_the_409_retry_hint(self):
        """#55: a 409 create whose body carries retry_after_s is retried, not discarded."""
        replies = [(409, b'{"error":"concurrent_sandbox_limit",'
                         b'"message":"account at concurrent-sandbox limit","retry_after_s":5}'),
                   (409, b'{"error":"concurrent_sandbox_limit",'
                         b'"message":"account at concurrent-sandbox limit","retry_after_s":7}')]
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(run.time, "sleep") as sleep:
            raised = None
            try:
                self.exercise(Path(temp) / "output", create_replies=replies)
            except RuntimeError as exc:
                raised = exc
            self.assertIsNone(raised, f"create must recover via the hint: {raised}")
            self.assertEqual([c.args for c in sleep.call_args_list], [(5,), (7,)])
            self.assertEqual(self.calls[-2:], [("DELETE", "/sandboxes/gl-test-1"),
                                               ("GET", "/sandboxes/gl-test-1")])

    def test_create_409_hint_exhaustion_surfaces_the_hint(self):
        """#55: when the hinted retries run out, the error keeps the gateway's hint."""
        replies = [(409, b'{"error":"concurrent_sandbox_limit",'
                         b'"message":"account at concurrent-sandbox limit",'
                         b'"retry_after_s":999}')] * 3
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(run.time, "sleep") as sleep:
            raised = None
            try:
                self.exercise(Path(temp) / "output", create_replies=replies)
            except RuntimeError as exc:
                raised = exc
            self.assertIsInstance(raised, RuntimeError)
            self.assertIn("HTTP 409", str(raised))
            self.assertIn("retry in 999s", str(raised))
            self.assertEqual([c.args for c in sleep.call_args_list], [(30,), (30,)])
            self.assertNotIn("DELETE", [method for method, _ in self.calls])

    def test_stalled_download_raises_and_releases_the_lease(self):
        """#55: a silent transfer must fail loudly within minutes, and drop the lease."""
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "output"
            raised = None
            try:
                self.exercise(output, stall_download=True)
            except (RuntimeError, TimeoutError, OSError) as exc:
                raised = exc
            self.assertIsInstance(raised, RuntimeError,
                                  f"a stalled download must fail loudly, got {raised!r}")
            self.assertIn("stalled", str(raised))
            self.assertIn("studio.npy", str(raised))
            receipt = json.loads((output / "runner.json").read_text())
            self.assertEqual(receipt["delete_status"], 200)
            self.assertEqual(receipt["cleanup_get_status"], 404)
            self.assertEqual(self.calls[-2:], [("DELETE", "/sandboxes/gl-test-1"),
                                               ("GET", "/sandboxes/gl-test-1")])
            self.assertEqual(self.download_timeouts,
                             [run.DOWNLOAD_STALL_TIMEOUT_S, run.DOWNLOAD_STALL_TIMEOUT_S])
            self.assertLessEqual(run.DOWNLOAD_STALL_TIMEOUT_S, 300,
                                 "the watchdog must fire in minutes, not the 3700s exec budget")

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
