#!/usr/bin/env python3
"""Generate known-bad runners for the self-test by single edits of the good one.

Each mutant is `examples/good/runner.py` with exactly one scripted edit. The
self-test expects every mutant to fail at least one gate (SPEC.md). The edits
are the realistic ways a containment runner goes wrong:

  no_cpu_limit          never sets RLIMIT_CPU
  no_nproc_limit        never sets RLIMIT_NPROC
  no_fsize_limit        never sets RLIMIT_FSIZE
  no_as_limit           never sets RLIMIT_AS
  no_timeout            never enforces the wall clock
  no_output_cap         never truncates stdout
  no_uid_drop           never drops the uid (no read/write confinement)
  trust_snippet         reports every snippet that exits 0 as "ok"
  misreport_benign      reports a clean exit as "error"
  widen_limits          sets every rlimit to "unlimited"

Usage: python3 mutants.py OUTDIR      (writes OUTDIR/<name>.py, prints names)
"""

import os
import sys

GOOD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "examples", "good", "runner.py")

# (name, must-exist-literal, replacement)
EDITS = [
    ("no_cpu_limit",
     "        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))\n",
     ""),
    ("no_nproc_limit",
     "        resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))\n",
     ""),
    ("no_fsize_limit",
     "        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))\n",
     ""),
    ("no_as_limit",
     "        resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))\n",
     ""),
    ("no_timeout",
     "        if time.monotonic() - started > wall:\n"
     "            reason = \"timeout\"\n"
     "            stop()\n"
     "            _, status = os.waitpid(pid, 0)\n"
     "            break\n",
     ""),
    ("no_output_cap",
     "        if seen > cap:\n"
     "            truncated = True\n"
     "            keep = cap - (seen - len(piece))\n"
     "            if keep > 0:\n"
     "                chunks.append(piece[:keep])\n"
     "            reason = \"output_cap\"\n"
     "            stop()\n"
     "            _, status = os.waitpid(pid, 0)\n"
     "            break\n",
     ""),
    ("no_uid_drop",
     "        if int(drop_uid):\n"
     "            os.setgroups([])\n"
     "            os.setgid(gid)\n"
     "            os.setuid(uid)\n"
     "            ns[\"uid_dropped\"] = True\n",
     ""),
    ("trust_snippet",
     "    if os.WEXITSTATUS(status) == 0:\n"
     "        return \"ok\", \"none\"\n",
     "    if os.WEXITSTATUS(status) == 0:\n"
     "        return \"ok\", \"none\"\n"
     "    return \"ok\", \"none\"\n"),
    ("misreport_benign",
     "    if os.WEXITSTATUS(status) == 0:\n"
     "        return \"ok\", \"none\"\n",
     "    if os.WEXITSTATUS(status) == 0:\n"
     "        return \"error\", \"exit\"\n"),
    ("widen_limits",
     "        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))\n"
     "        resource.setrlimit(resource.RLIMIT_AS, (as_bytes, as_bytes))\n"
     "        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))\n"
     "        resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))\n",
     "        resource.setrlimit(resource.RLIMIT_CPU,\n"
     "                            (resource.RLIM_INFINITY, resource.RLIM_INFINITY))\n"
     "        resource.setrlimit(resource.RLIMIT_AS,\n"
     "                            (resource.RLIM_INFINITY, resource.RLIM_INFINITY))\n"
     "        resource.setrlimit(resource.RLIMIT_FSIZE,\n"
     "                            (resource.RLIM_INFINITY, resource.RLIM_INFINITY))\n"
     "        resource.setrlimit(resource.RLIMIT_NPROC,\n"
     "                            (resource.RLIM_INFINITY, resource.RLIM_INFINITY))\n"),
]


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    with open(GOOD) as fh:
        good = fh.read()
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, old, new in EDITS:
        if old not in good:
            raise SystemExit("mutant %s: anchor not found in the good runner"
                             % name)
        mutant = good.replace(old, new, 1)
        if mutant == good:
            raise SystemExit("mutant %s: edit produced no change" % name)
        with open(os.path.join(out_dir, name + ".py"), "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
