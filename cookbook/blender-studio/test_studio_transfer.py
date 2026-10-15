"""Failed downloads must not replace verified render evidence."""
import base64
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

MEDIA = Path(__file__).resolve().parent / "media"
spec = importlib.util.spec_from_file_location("studio_capture", MEDIA / "capture.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class TransferTests(unittest.TestCase):
    def test_verified_bytes_replace_old_capture(self):
        payload = b"generated render evidence"
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            path.write_bytes(b"old capture")
            with patch.object(capture.runner, "sbx", return_value=
                              base64.b64encode(payload).decode()):
                capture.download("sandbox-test", "/tmp/frame.png", path,
                                 len(payload), digest)
            self.assertEqual(path.read_bytes(), payload)
            self.assertFalse(path.with_suffix(".png.partial").exists())

    def test_wrong_bytes_preserve_old_capture(self):
        payload = b"truncated or wrong evidence"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            path.write_bytes(b"old capture")
            with patch.object(capture.runner, "sbx", return_value=
                              base64.b64encode(payload).decode()):
                with self.assertRaisesRegex(RuntimeError, "checksum mismatch"):
                    capture.download("sandbox-test", "/tmp/frame.png", path,
                                     len(payload), hashlib.sha256(b"expected").hexdigest())
            self.assertEqual(path.read_bytes(), b"old capture")

    def test_valid_cached_capture_needs_no_remote_read(self):
        payload = b"generated verified evidence"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            path.write_bytes(payload)
            with patch.object(capture.runner, "sbx") as remote:
                capture.download("sandbox-test", "/tmp/frame.png", path, len(payload),
                                 hashlib.sha256(payload).hexdigest())
            remote.assert_not_called()

    def test_stalled_chunk_is_retried(self):
        payload = b"evidence after one stalled exec"
        replies = [subprocess.TimeoutExpired("sbx", 150), base64.b64encode(payload).decode()]
        def fake_run(*args, **kwargs):
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return subprocess.CompletedProcess(args, 0, reply, "")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frame.png"
            with patch.object(capture.runner.subprocess, "run", side_effect=fake_run), \
                 patch.object(capture.time, "sleep"):
                capture.download("sandbox-test", "/tmp/frame.png", path, len(payload),
                                 hashlib.sha256(payload).hexdigest())
            self.assertEqual(path.read_bytes(), payload)


if __name__ == "__main__":
    unittest.main()
