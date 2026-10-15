#!/usr/bin/env python3
"""Generate known-bad agents as single-edit mutants of the known-good one.

Each mutant changes exactly one thing in one task's solution, so the task it
targets must stop passing while the rest of the bench still works.  That is
what makes the kill rate meaningful: a mutant is killed when the task its
edit targets no longer passes, not when the 8/10 headline bar happens to
move.

Usage: mutants.py <good-agent-dir> <out-dir>
Writes <out-dir>/<mutant-name>/ (a full agent tree) and prints one line per
mutant describing the edit.
"""

from __future__ import annotations

import os
import shutil
import sys

# (name, task, needle, replacement, description)
# Every needle must appear exactly once in that task's apply.sh.
MUTANTS = [
    (
        "wal-writes-aside",
        "wal-repair",
        "os.replace(tmp, db)",
        'os.replace(tmp, db + ".repaired")',
        "wal-repair: splice the frames correctly but leave the result in a "
        "side file, so app.db itself is never repaired",
    ),
    (
        "git-detached-head",
        "git-lost-branch",
        'git checkout -q -B "$BRANCH" "$tip"',
        'git checkout -q --detach "$tip"',
        "git-lost-branch: recreate the commit but stay detached, so HEAD is "
        "never reattached to the branch",
    ),
    (
        "unit-wrong-exec",
        "systemd-unit",
        'ExecStart=$PROG --self-test',
        'ExecStart=/usr/bin/ingestd --self-test',
        "systemd-unit: name a plausible system path that does not exist on "
        "the image, instead of the program that runs",
    ),
    (
        "perms-chmod-777",
        "perms-maze",
        'chmod 755 opt/bench/var/scratch',
        'chmod 777 opt/bench/var/scratch',
        "perms-maze: the lazy repair -- make the scratch dir world-writable",
    ),
    (
        "csv-keeps-ragged",
        "csv-normalize",
        '    if len(fields) != 3:\n        continue                      '
        '# ragged rows are dropped',
        '    if len(fields) < 3:\n        continue',
        "csv-normalize: keep rows with too many fields instead of dropping "
        "them, so the canonical byte count changes",
    ),
    (
        "json-string-bool",
        "json-config",
        '    "enabled": enabled,',
        '    "enabled": str(enabled).lower(),',
        "json-config: write enabled back as the string \"true\" instead of a "
        "boolean",
    ),
    (
        "symlink-absolute",
        "symlink-maze",
        'ln -sfn "../releases/$release" links/current',
        'ln -sfn "$PWD/releases/$release" links/current',
        "symlink-maze: use an absolute target, so the link breaks when the "
        "tree is moved",
    ),
    (
        "tar-skips-modes",
        "tar-restore",
        '        os.chmod(dst, entry["mode"])',
        '        pass',
        "tar-restore: restore the contents but not the recorded modes",
    ),
    (
        "python-off-by-one",
        "bugfix-python",
        '    for i in range(len(values) - window + 1):\n        yield '
        'values[i:i + window]',
        '    for i in range(len(values) - window):\n        yield '
        'values[i:i + window]',
        "bugfix-python: restore the original off-by-one (the shipped test "
        "still passes)",
    ),
    (
        "cron-names-dow",
        "cron-repair",
        '0 6 * * 0 /opt/bench/bin/weekly.sh',
        '0 6 * * SUN /opt/bench/bin/weekly.sh',
        "cron-repair: use a day-of-week name, which the documented grammar "
        "does not allow",
    ),
    (
        "csv-drops-quoting",
        "csv-normalize",
        'writer = csv.writer(buf, lineterminator="\\n", '
        'quoting=csv.QUOTE_MINIMAL)',
        'writer = csv.writer(buf, lineterminator="\\n", '
        'quoting=csv.QUOTE_NONE, escapechar="\\\\")',
        "csv-normalize: emit the field with a comma in it unquoted, so the "
        "canonical bytes no longer match",
    ),
    (
        "tar-keeps-leftover",
        "tar-restore",
        '        for name in filenames:\n            rel = os.path.relpath('
        'os.path.join(dirpath, name), restore)\n            if rel not in '
        'wanted:\n                os.remove(os.path.join(dirpath, name))',
        '        for name in filenames:\n            pass',
        "tar-restore: restore every manifest entry but leave the stale "
        "file behind, so the tree has a path the manifest never names",
    ),
]


def build(good: str, out: str) -> list:
    made = []
    for name, task, needle, repl, desc in MUTANTS:
        src = os.path.join(good, "solutions", task, "apply.sh")
        text = open(src).read()
        count = text.count(needle)
        if count != 1:
            raise SystemExit(f"mutant {name}: needle occurs {count} times in "
                             f"{src}, expected exactly 1")
        dest = os.path.join(out, name)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(good, dest)
        target = os.path.join(dest, "solutions", task, "apply.sh")
        with open(target, "w") as fh:
            fh.write(text.replace(needle, repl))
        os.chmod(target, 0o755)
        made.append({"name": name, "task": task, "description": desc})
    return made


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good-agent-dir> <out-dir>", file=sys.stderr)
        return 2
    good, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    made = build(good, out)
    for m in made:
        print(f"mutants: {m['name']}  ({m['task']})  {m['description']}")
    print(f"mutants: wrote {len(made)} mutants to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
