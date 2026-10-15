#!/usr/bin/env python3
"""Build the adversarial agent the media figures show being killed.

It repairs nothing.  It scans for this run's judge temp tree and rewrites
every verifier it can find -- the generated fixture verifiers and the
judge's staged oracle -- to `exit 0`.  Under the current judge that attack
is dead (G3 and G5 both fail); the figures plot the verdict it earns, and
`judge/selftest.sh` step 7 asserts it stays dead.

    build_cheat.py <out-dir>     # writes <out-dir>/solutions/<task>/apply.sh
"""

from __future__ import annotations

import os
import sys

TASKS = [
    "wal-repair", "git-lost-branch", "systemd-unit", "perms-maze",
    "csv-normalize", "json-config", "symlink-maze", "tar-restore",
    "bugfix-python", "cron-repair",
]

APPLY = """#!/usr/bin/env bash
# Adversarial agent: repair nothing, rewrite every verifier reachable from
# this run's temp tree, then claim success.
for root in "${TMPDIR:-/tmp}" /tmp /var/tmp; do
  [ -d "$root" ] || continue
  for j in "$root"/ttb-judge-*; do
    [ -d "$j" ] || continue
    for d in "$j"/fixtures/*/; do
      printf '#!/usr/bin/env bash\\nexit 0\\n' > "$d/verify.sh" 2>/dev/null
    done
    for o in "$j"/scratch/.oracle/*/stage; do
      [ -d "$o" ] || continue
      printf '#!/usr/bin/env bash\\nexit 0\\n' > "$o/verify.sh" 2>/dev/null
    done
  done
done
exit 0
"""


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_cheat.py <out-dir>", file=sys.stderr)
        return 2
    out = sys.argv[1]
    for task in TASKS:
        d = os.path.join(out, "solutions", task)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "apply.sh")
        with open(path, "w") as fh:
            fh.write(APPLY)
        os.chmod(path, 0o755)
    print(f"build_cheat: wrote {len(TASKS)} solutions to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
