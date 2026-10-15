from pathlib import Path
import sys
import unittest

DEMO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEMO / "judge"))
from security import validate

GOOD = (DEMO / "examples/good/edit.mlt").read_bytes()


class Security(unittest.TestCase):
    def test_good(self):
        validate(GOOD)

    def test_resource_escape(self):
        for path in (b"/etc/passwd", b"../outside.mp4", b"assets/../../x",
                     b"https://example.com/x", b"file:/etc/passwd", b"assets/link.mp4"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate(GOOD.replace(b"assets/clip_a.mp4", path))

    def test_services(self):
        for service in (b"xml", b"xml-string", b"frei0r.any", b"avformat-novalidate"):
            with self.subTest(service=service), self.assertRaises(ValueError):
                validate(GOOD.replace(b">avformat<", b">"+service+b"<"))

    def test_external_entities(self):
        with self.assertRaises(ValueError):
            validate(b'<!DOCTYPE mlt [<!ENTITY x SYSTEM "file:///etc/passwd">]>'+GOOD)

    def test_consumer_and_root_escape(self):
        for data in (GOOD.replace(b"<profile ", b'<consumer resource="/tmp/x"/><profile '),
                     GOOD.replace(b'<mlt ', b'<mlt root="/tmp" '),
                     GOOD.replace(b'name="level"', b'name="filename"')):
            with self.assertRaises(ValueError):
                validate(data)
