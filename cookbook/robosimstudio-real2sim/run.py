#!/usr/bin/env python3
"""robosimstudio-real2sim: one command, one disposable GPU slice, one verdict.

Creates an agent-next GPU VRAM-slice lease, uploads the pinned RoboSimStudio
wheelhouse into it, builds the hidden reference, runs the judge self-test, and
grades the known-good artifact — then always deletes the lease and confirms it
is gone.

    python3 cookbook/robosimstudio-real2sim/run.py [--vram-gb 4] [--keep]
                                                   [--device cuda:0]

Needs SBX_API_KEY (or E2B_API_KEY) in the environment. The lease has no
network, so every wheel travels in through the exec payloads; that is the
single largest cost of a run and its wall time is printed per phase.

Standard library only.
"""

import argparse
import base64
import io
import json
import os
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "judge"))

from lease import Lease, LeaseError  # noqa: E402


def phase(label, started):
    """Print a phase's wall time and return the new clock."""
    now = time.monotonic()
    print(f"  {label}: {now - started:.1f} s", flush=True)
    return now


def payload_tar(wheels_dir):
    """Tar the wheelhouse and the judge, for the lease to untar under ~/rss."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(wheels_dir, arcname="wheels")
        tf.add(os.path.join(HERE, "judge"), arcname="judge")
        tf.add(os.path.join(HERE, "examples"), arcname="examples")
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vram-gb", type=int, default=4)
    ap.add_argument("--keep", action="store_true", help="leave the lease up and print its id")
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--wheels", default=os.path.expanduser("~/rss-wheels"))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    if not os.path.isdir(args.wheels) or not os.listdir(args.wheels):
        print(f"no wheelhouse at {args.wheels}; run judge/setup.sh --build first", file=sys.stderr)
        return 2

    lease = None
    started = time.monotonic()
    try:
        print("== lease ==", flush=True)
        lease = Lease(vram_gb=args.vram_gb)
        print(f"  created {lease.sid} ({args.vram_gb} GiB VRAM slice)", flush=True)
        clock = phase("create", started)

        print("== upload ==", flush=True)
        raw = payload_tar(args.wheels)
        chunks, seconds = lease.upload_tar(raw, dest="~/rss", chunk_bytes=16 * 1024 * 1024)
        print(f"  {len(raw) / 1e6:.1f} MB in {chunks} chunks, "
              f"{seconds / 1e3:.1f} s/MB", flush=True)
        clock = phase("upload", clock)

        print("== install ==", flush=True)
        report = lease.exec(
            "import os, subprocess, sys\n"
            "wheels = os.path.expanduser('~/rss/wheels')\n"
            "site = os.path.expanduser('~/rsssite')\n"
            "p = subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index',\n"
            "                    '--no-deps', '--target', site, '--find-links', wheels,\n"
            "                    'robosimstudio', 'newton', 'mujoco', 'mujoco-warp',\n"
            "                    'warp-lang', 'numpy'], capture_output=True, text=True)\n"
            "report['rc'] = p.returncode\n"
            "report['tail'] = (p.stdout + p.stderr)[-800:]\n",
            timeout_s=1800,
        )["report"]
        if report.get("rc") != 0:
            print(report.get("tail", ""), file=sys.stderr)
            raise LeaseError("install failed")
        clock = phase("install", clock)

        print("== reference ==", flush=True)
        ref = lease.exec(
            "import os, subprocess, sys\n"
            "env = dict(os.environ, PYTHONPATH=os.path.expanduser('~/rsssite'),\n"
            "           ROBOSIMSTUDIO_RENDERER='tiled')\n"
            "p = subprocess.run([sys.executable, os.path.expanduser('~/rss/judge/make_reference.py'),\n"
            "                    '--device', %r, '--out', os.path.expanduser('~/rss/judge/reference')],\n"
            "                   capture_output=True, text=True, env=env, timeout=5400)\n"
            "report['rc'] = p.returncode\n"
            "report['stdout'] = p.stdout[-2000:]\n"
            "report['stderr'] = p.stderr[-2000:]\n" % args.device,
            timeout_s=5700,
        )["report"]
        if ref.get("rc") != 0:
            print(ref.get("stderr", ""), file=sys.stderr)
            raise LeaseError("building the reference failed")
        clock = phase("reference", clock)

        print("== self-test ==", flush=True)
        selftest = lease.exec(
            "import os, subprocess, sys\n"
            "env = dict(os.environ, PYTHONPATH=os.path.expanduser('~/rsssite'),\n"
            "           ROBOSIMSTUDIO_RENDERER='tiled')\n"
            "p = subprocess.run(['bash', os.path.expanduser('~/rss/judge/selftest.sh'),\n"
            "                    '--seed', %r, '--device', %r],\n"
            "                   capture_output=True, text=True, env=env, timeout=5400)\n"
            "report['rc'] = p.returncode\n"
            "report['stdout'] = p.stdout[-4000:]\n"
            "report['stderr'] = p.stderr[-1500:]\n" % (str(args.seed), args.device),
            timeout_s=5700,
        )["report"]
        print(selftest.get("stdout", ""), flush=True)
        clock = phase("self-test", clock)

        print("== grade the good artifact ==", flush=True)
        graded = lease.exec(
            "import os, subprocess, sys\n"
            "env = dict(os.environ, PYTHONPATH=os.path.expanduser('~/rsssite'),\n"
            "           ROBOSIMSTUDIO_RENDERER='tiled')\n"
            "p = subprocess.run(['bash', os.path.expanduser('~/rss/judge/grade.sh'),\n"
            "                    os.path.expanduser('~/rss/examples/good/params.json'),\n"
            "                    '--seed', %r, '--device', %r],\n"
            "                   capture_output=True, text=True, env=env, timeout=5400)\n"
            "report['rc'] = p.returncode\n"
            "report['stdout'] = p.stdout[-4000:]\n"
            "report['stderr'] = p.stderr[-1500:]\n" % (str(args.seed), args.device),
            timeout_s=5700,
        )["report"]
        print(graded.get("stdout", ""), flush=True)
        clock = phase("grade", clock)

        if selftest.get("rc") != 0 or graded.get("rc") != 0:
            print("a judge step failed", file=sys.stderr)
            return 1
        print(f"total: {time.monotonic() - started:.1f} s", flush=True)
        return 0
    finally:
        if lease is not None and not args.keep:
            print("== cleanup ==", flush=True)
            try:
                lease.close()
                print(f"  {lease.sid} deleted and confirmed gone", flush=True)
            except LeaseError as exc:
                print(f"  cleanup unconfirmed: {exc}", file=sys.stderr)
                raise
        elif lease is not None:
            print(f"  kept {lease.sid}; delete it with DELETE /sandboxes/{lease.sid}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
