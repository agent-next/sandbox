"""Hermetic checks for the hash-locked judge installer."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


HERE = Path(__file__).resolve().parent


class SetupTests(unittest.TestCase):
    def test_rejects_non_312_before_creating_venv(self):
        for version in ("3.10", "3.11", "3.13"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                setup = root / "setup.sh"
                shutil.copyfile(HERE / "setup.sh", setup)
                bin_dir = root / "bin"
                bin_dir.mkdir()
                python = bin_dir / "python3"
                python.write_text(
                    '#!/bin/sh\n'
                    'if [ "$1" = "-c" ]; then\n'
                    '    printf "%s\\n" "$TEST_PYTHON_VERSION"\n'
                    'else\n'
                    '    echo "unexpected setup work: $*" >&2\n'
                    '    exit 99\n'
                    'fi\n'
                )
                python.chmod(0o755)
                uname = bin_dir / "uname"
                uname.write_text(
                    '#!/bin/sh\n'
                    'case "$1" in\n'
                    '    -s) echo Linux ;;\n'
                    '    -m) echo x86_64 ;;\n'
                    '    *) exit 99 ;;\n'
                    'esac\n'
                )
                uname.chmod(0o755)
                result = subprocess.run(
                    ["/bin/sh", str(setup)],
                    env={**os.environ, "HOME": str(root),
                         "PATH": f"{bin_dir}:{os.defpath}",
                         "TEST_PYTHON_VERSION": version},
                    text=True, capture_output=True, timeout=10,
                )
                self.assertEqual(
                    result.returncode, 2,
                    f"setup.sh must reject Python {version} before installation: "
                    f"{result.stdout}{result.stderr}",
                )
                self.assertIn(
                    f"unsupported Python {version} (supported: CPython 3.12)",
                    result.stderr,
                )
                self.assertFalse((root / ".venvs").exists())


if __name__ == "__main__":
    unittest.main()
