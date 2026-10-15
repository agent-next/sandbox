import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "judge"))
from grade import ebu_levels
import grade


class Ebu(unittest.TestCase):
    def test_silent_audio_is_a_measurement_not_a_parser_crash(self):
        lufs, peak = ebu_levels("Summary:\n I: -70.0 LUFS\n Peak: -inf dBFS")
        self.assertEqual(lufs, -70)
        self.assertEqual(peak, -math.inf)

    def test_last_summary_and_missing_measurements(self):
        text = "Summary:\n I: -70.0 LUFS\n Peak: -inf dBFS\nSummary:\n I: -16.0 LUFS\n Peak: -8.5 dBFS"
        self.assertEqual(ebu_levels(text), (-16, -8.5))
        with self.assertRaisesRegex(ValueError, "summary"):
            ebu_levels("no measurements")

    def test_integrity_includes_bytecode_files_too(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(grade, "JDIR", Path(tmp)):
            cache = Path(tmp) / "__pycache__"
            cache.mkdir()
            path = cache / "judge.pyc"
            path.write_bytes(b"first")
            before = grade.checksums()
            path.write_bytes(b"changed")
            self.assertNotEqual(before, grade.checksums(),
                                "a changed judge bytecode file was ignored")
