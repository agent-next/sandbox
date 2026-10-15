#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the good ctf-flag-hunt range.

Each mutant is exactly one textual edit of one file in examples/good/.
Used by judge/selftest.sh to prove the judge fails bad inputs.  The set
covers every gate: a mutant that fixes a vulnerability (must fail the
oracle), one that leaks a flag on the legitimate path (must fail the
negative control), one that bakes a flag into the source (must fail the
sweep) and one that writes a file (must fail the blast-radius gate).

Output: <outdir>/<name>/ containing the five edited sources.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# (name, file, exactly-one-occurrence substring, replacement, why)
MUTANTS = [
    ("offbyone-fixed", "notes.c",
     "if (id < 0 || id > n) {", "if (id < 0 || id >= n) {",
     "closes the off-by-one: no id reaches the flag"),
    ("traversal-fixed", "retrieve.c",
     'if (strncmp(name, "../", 3) == 0 || strcmp(name, "..") == 0) {',
     'if (strstr(name, "..") != NULL) {',
     "rejects any name containing ..: the traversal no longer escapes"),
    ("token-secret", "token.c",
     "x ^= (t << 7);", "x ^= ((t ^ 0x9e3779b97f4a7c15ULL) << 7);",
     "mixes in a secret constant: the token is no longer forgeable"),
    ("status-leak", "status.c",
     'printf("version=%s\\n", version);',
     'printf("version=%s\\n", flag);',
     "leaks the flag on the legitimate `status version` path"),
    ("admin-mode-fixed", "admin.c",
     "int mode = atoi(argv[1]);",
     "int mode = (argv[1][0] >= '0' && argv[1][0] <= '9') ? atoi(argv[1]) : -1;",
     "rejects a non-numeric mode instead of falling into 0"),
    ("flag-baked", "status.c",
     'static char build[VAL_LEN] = "unknown";',
     'static char build[VAL_LEN] = "flag{c4_0000000000000000}";',
     "a flag-shaped string baked into the source: the sweep catches it"),
    ("writes-a-file", "retrieve.c",
     "    char path[PATH_LEN];",
     '    FILE *l = fopen("access.log", "a");\n'
     '    if (l) { fputs("req\\n", l); fclose(l); }\n'
     "    char path[PATH_LEN];",
     "logs every request to a file: the blast-radius gate catches it"),
    ("build-warning", "notes.c",
     "    int n = 0;",
     "    int n = 0;\n    int unused;",
     "declares an unused variable: -Wall warns, the build gate fails"),
]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good-dir> <outdir>", file=sys.stderr)
        return 2
    good = Path(sys.argv[1])
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    for name, fname, old, new, why in MUTANTS:
        src = (good / fname).read_text()
        if src.count(old) != 1:
            print(f"mutants: anchor {old!r} in {fname} occurs "
                  f"{src.count(old)} times, need exactly 1", file=sys.stderr)
            return 1
        dest = outdir / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(good, dest)
        (dest / fname).write_text(src.replace(old, new))
        print(f"mutants: {name}/  edit {fname}: {why}")

    print(f"mutants: wrote {len(MUTANTS)} mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
