#!/usr/bin/env python3
"""Run the sandbox-built Tally simulator app on a Devin macOS VM and judge what it saw.

Called by run.py --run-on-mac with the sandbox id and the path of Tally-sim.zip inside it.
The sandbox serves the zip on a token URL (a free port, checked through the public URL before
any Devin session starts) and receives the VM's recording and screenshots on the same server. A Devin session (platform "macos", ACU-capped,
not resumable) downloads the zip, checks its sha256, installs and launches it in the iOS
Simulator, taps +1 three times and Reset once, records the screen and uploads the files.
Verdict PASS needs: sha match, install + launch ok, counts 0 / 3 / 0 read from the screen,
no crash, and all four files received. The session is always terminated.

Env: DEVIN_API_KEY (Devin API token) and DEVIN_ORG_ID (org-...); DEVIN_MAX_ACU (default 2).
"""

import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.devin.ai/v3/organizations/"
FILES = ["tally.mp4", "shot0.png", "shot3.png", "shot_reset.png"]
SCHEMA = {
    "type": "object",
    "properties": {
        "sha_ok": {"type": "boolean"}, "macos": {"type": "string"}, "xcode": {"type": "string"},
        "simulator_device": {"type": "string"}, "install_ok": {"type": "boolean"},
        "launch_ok": {"type": "boolean"}, "launch_output": {"type": "string"},
        "count_initial": {"type": ["integer", "null"]}, "count_after_3_taps": {"type": ["integer", "null"]},
        "count_after_reset": {"type": ["integer", "null"]}, "crash_seen": {"type": "boolean"},
        "uploads": {"type": "array", "items": {"type": "string"}}, "problems": {"type": "string"},
    },
    "required": ["sha_ok", "install_ok", "launch_ok", "count_initial", "count_after_3_taps",
                 "count_after_reset", "crash_seen", "uploads", "problems"],
}
PROMPT = """Closed-loop test of an iOS app that was built on Linux (xtool, no Xcode) in an agent-next sandbox. Do NOT rebuild it with Xcode; test the given binary as-is. Do not create a repo or PR. Total work should take under 15 minutes.

1. curl -fsSL -o /tmp/Tally.zip "{app_url}" ; check `shasum -a 256 /tmp/Tally.zip` equals {sha} ; ditto -x -k /tmp/Tally.zip /tmp/tally
2. Report `sw_vers`, `xcodebuild -version` and the simulator device you use.
3. Boot an iPhone simulator (pick one from `xcrun simctl list devices available`; boot by UDID), `open -a Simulator`, `xcrun simctl install booted /tmp/tally/Tally.app`, `xcrun simctl launch booted com.agentnext.tally`. Report exact output and exit codes.
4. `xcrun simctl io booted recordVideo --codec=h264 /tmp/tally.mp4 &` ; wait 2 s ; `xcrun simctl io booted screenshot /tmp/shot0.png`
5. With computer use tap "+1" exactly 3 times about 1 s apart, then screenshot /tmp/shot3.png; tap "Reset", wait 1 s, screenshot /tmp/shot_reset.png. Stop the recording with kill -INT and wait for the file to finish.
6. Read the number on screen in each screenshot. Check `xcrun simctl spawn booted log show --last 2m --predicate 'process == "Tally"'` for crashes.
7. Upload each file (each must print "ok <bytes>"):
{uploads}
8. Return the structured output with only what you observed; name any failed step and paste its error."""


def devin(method, path, body=None):
    req = urllib.request.Request(
        API + os.environ["DEVIN_ORG_ID"] + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + os.environ["DEVIN_API_KEY"], "Content-Type": "application/json"},
        method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read() or b"{}")


def sbx_exec(sid, command, timeout=120):
    p = subprocess.run(["sbx", "exec", sid, "--timeout", str(timeout), "--", "bash", "-lc", command],
                       capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"sbx exec failed ({p.returncode}): {p.stderr[-2000:]}")
    return p.stdout


RECEIVER = r'''
import http.server, os, sys
tok, root = sys.argv[1], sys.argv[2]
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=root, **k)
    def list_directory(self, path): self.send_error(404)
    def do_PUT(self):
        name = self.path.rsplit("/", 1)[-1]
        if not self.path.startswith("/" + tok + "/up/") or name not in {files}:
            self.send_error(403); return
        n = int(self.headers.get("Content-Length", 0)); data = self.rfile.read(n)
        os.makedirs(os.path.join(root, "up"), exist_ok=True)
        open(os.path.join(root, "up", name), "wb").write(data)
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok %d\n" % len(data))
srv = http.server.ThreadingHTTPServer(("0.0.0.0", 0), H)
open(os.path.join(root, "port"), "w").write(str(srv.server_address[1]))
srv.serve_forever()
'''


def run(sid, sim_zip, out_dir=Path(__file__).resolve().parent / "media" / "mac-run"):
    tok = secrets.token_hex(12)
    root = f"/tmp/macrun/{tok}"
    sha = sbx_exec(sid, f"mkdir -p {root} && cp {sim_zip} {root}/Tally-sim.zip && sha256sum {root}/Tally-sim.zip").split()[0]
    sbx_exec(sid, f"cat > /tmp/macrun/recv.py <<'EOF'\n{RECEIVER.replace('{files}', repr(set(FILES)))}\nEOF\n"
                  f"cd /tmp/macrun && rm -f port && (setsid nohup python3 recv.py {tok} /tmp/macrun > recv.log 2>&1 < /dev/null &)"
                  f" && for i in $(seq 50); do test -s port && break; sleep 0.2; done")
    port = sbx_exec(sid, "cat /tmp/macrun/port").strip()
    base = f"https://{port}-{sid}.sbx.agent-next.com/{tok}"
    # Prove the public URL serves the exact zip before spending any Devin ACU on it.
    with urllib.request.urlopen(f"{base}/Tally-sim.zip", timeout=60) as r:
        got_sha = hashlib.sha256(r.read()).hexdigest()
    if got_sha != sha:
        raise RuntimeError(f"public URL served sha256 {got_sha}, expected {sha}")
    prompt = PROMPT.format(app_url=f"{base}/Tally-sim.zip", sha=sha, uploads="\n".join(
        f'   curl -sS -T /tmp/{f} "{base}/up/{f}"' for f in FILES))
    session = devin("POST", "/sessions", {
        "prompt": prompt, "platform": "macos", "resumable": False,
        "max_acu_limit": int(os.environ.get("DEVIN_MAX_ACU", "2")),
        "title": "apple-app-build: run sandbox-built app in iOS Simulator",
        "tags": ["apple-app-build"], "structured_output_schema": SCHEMA})
    sid_devin = session["session_id"]
    print(f"devin session {session['url']}", flush=True)
    t0, d = time.time(), {}
    try:
        while time.time() - t0 < 40 * 60:
            time.sleep(30)
            d = devin("GET", f"/sessions/{sid_devin}")
            if d.get("status") in ("exit", "error", "suspended") or d.get("status_detail") in ("finished", "waiting_for_user"):
                break
    finally:
        try:
            devin("DELETE", f"/sessions/{sid_devin}")
        except urllib.error.HTTPError as e:
            print(f"WARNING: could not terminate devin session {sid_devin}: {e.code}", file=sys.stderr)
    so = d.get("structured_output") or {}
    out_dir.mkdir(parents=True, exist_ok=True)
    got = []
    for f in FILES:
        b64 = sbx_exec(sid, f"test -s /tmp/macrun/up/{f} && base64 -w0 /tmp/macrun/up/{f} || true")
        if b64.strip():
            (out_dir / f).write_bytes(base64.b64decode(b64))
            got.append(f)
    checks = {
        "sha": so.get("sha_ok") is True,
        "install": so.get("install_ok") is True,
        "launch": so.get("launch_ok") is True,
        "counts 0/3/0": [so.get("count_initial"), so.get("count_after_3_taps"), so.get("count_after_reset")] == [0, 3, 0],
        "no crash": so.get("crash_seen") is False,
        "files received": got == FILES,
    }
    return {"verdict": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "devin_session": sid_devin, "acus_consumed": d.get("acus_consumed"),
            "seconds": round(time.time() - t0), "observed": so, "files": [str(out_dir / f) for f in got]}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: run_on_mac.py <sandbox id> <path of Tally-sim.zip in the sandbox>")
    print(json.dumps(run(sys.argv[1], sys.argv[2]), indent=2))
