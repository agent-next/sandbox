#!/usr/bin/env python3
"""Render the math film in a disposable CPU sandbox, then destroy it.

Creates an agent-full:standard sandbox, installs ManimGX, uploads scene.py,
renders 1920x1080 60 fps with narration (an ElevenLabs voice through fal when
FAL_KEY is exported here; silent with subtitles otherwise) and downloads the
MP4 and .srt into the current directory. The sandbox is killed in `finally`
and its death confirmed. Wall times for install and render are printed.

Requires: Python 3.10+, the `e2b` package (pip install e2b) and E2B_API_KEY
(or SBX_API_KEY) in the environment. Key values are never echoed.

Usage:
    python3 run.py            # writes completing_the_square.mp4 and .srt here
"""
from __future__ import annotations

import os
import sys
import time

from e2b import CommandExitException, Sandbox

TEMPLATE = "agent-full:standard"  # CPU: 4 vCPU, 8 GiB — no GPU needed
SCENE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene.py")
REMOTE = "/root/scene.py"
VIDEO = "completing_the_square.mp4"
SUBS = "completing_the_square.srt"
CREATE_TIMEOUT_S = 2400  # the sandbox self-kills if the client is lost
RUN_TIMEOUT_S = 1800  # the render itself (measured: ~10 min on 4 vCPU)


def log(msg: str) -> None:
    print(msg, flush=True)


def run(sb: Sandbox, cmd: str, timeout: float) -> None:
    """Run a command, streaming its output; raise, scrubbed, if it fails."""
    proc = sb.commands.run(cmd, timeout=timeout, request_timeout=timeout + 30,
                           on_stdout=lambda s: sys.stdout.write(s),
                           on_stderr=lambda s: sys.stdout.write(s))
    sys.stdout.flush()
    if proc.exit_code != 0:
        raise RuntimeError(f"command failed with exit {proc.exit_code}")


def main() -> None:
    if not os.environ.get("E2B_API_KEY") and not os.environ.get("SBX_API_KEY"):
        raise RuntimeError(
            "no API key: export E2B_API_KEY (or SBX_API_KEY); "
            "get one at https://sbx.agent-next.com/console"
        )
    key = os.environ.get("E2B_API_KEY") or os.environ["SBX_API_KEY"]
    # the SDK reads E2B_API_KEY and the agent-next domain from the environment
    os.environ["E2B_API_KEY"] = key
    os.environ.setdefault("E2B_DOMAIN", "sbx.agent-next.com")
    fal = os.environ.get("FAL_KEY")  # handed to the sandbox, never echoed

    with open(SCENE, "rb") as fh:
        scene_py = fh.read()

    t0 = time.monotonic()
    log(f"math-video: creating {TEMPLATE} sandbox")
    sb = Sandbox.create(template=TEMPLATE, timeout=CREATE_TIMEOUT_S,
                        envs={"FAL_KEY": fal} if fal else None,
                        api_key=key, domain="sbx.agent-next.com")
    sid = sb.sandbox_id
    log(f"math-video: sandbox {sid}")

    t_install = t_render = None
    try:
        if fal:
            log("math-video: FAL_KEY found — rendering narrated")
        else:
            log("math-video: no FAL_KEY — rendering silent with subtitles "
                "(the film keeps its subtitles and pacing)")
        sb.files.write(REMOTE, scene_py)

        t1 = time.monotonic()
        log("math-video: installing manimgx (uv, python 3.14)")
        run(sb, "uv tool install --python 3.14 manimgx==0.1.1 "
                "&& ~/.local/bin/manimgx --version", timeout=600)
        t_install = time.monotonic() - t1

        t2 = time.monotonic()
        log("math-video: rendering 1920x1080 60 fps")
        run(sb, f"cd /root && ~/.local/bin/manimgx render {REMOTE} "
                f"-r 1920x1080 --fps 60 -o /root/{VIDEO}",
            timeout=RUN_TIMEOUT_S)
        t_render = time.monotonic() - t2

        log("math-video: downloading the MP4 and subtitles")
        for name in (VIDEO, SUBS):
            data = sb.files.read(f"/root/{name}", format="bytes")
            with open(name, "wb") as fh:
                fh.write(data)
            log(f"math-video: wrote {os.path.abspath(name)} "
                f"({len(data) / 1e6:.1f} MB)")
    finally:
        try:
            sb.kill()
            gone = not sb.is_running()
        except Exception as exc:  # cleanup failures name the id to kill
            raise RuntimeError(
                f"cleanup unconfirmed for {sid}: kill/check raised {exc!r}; "
                f"kill it manually") from exc
        if not gone:
            raise RuntimeError(f"cleanup unconfirmed for {sid}: still "
                               f"running after kill; kill it manually")
        log(f"math-video: sandbox {sid} destroyed; confirmed gone")

    log(f"math-video: install {t_install:.0f}s, render {t_render:.0f}s, "
        f"total {time.monotonic() - t0:.0f}s")
    log(f"math-video: output {os.path.abspath(VIDEO)}")


if __name__ == "__main__":
    try:
        main()
    except CommandExitException as exc:
        print(f"math-video: in-sandbox command failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"math-video: {exc}", file=sys.stderr)
        raise SystemExit(1)
