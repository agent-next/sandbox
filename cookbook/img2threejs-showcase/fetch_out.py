"""Pack /w/out in one sandbox and download it as a single tarball.

usage: fetch_out.py <sandbox_id> <dest_dir> [--no-video | --video-only]
Small files first (--no-video) keep verdicts safe on a slow client link; videos follow separately.
"""
import io
import sys
import tarfile

from e2b import Sandbox

sid, dest = sys.argv[1], sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else ""
select = {"--no-video": "--exclude='*.mp4' out", "--video-only": "$(cd /w && ls out/*.mp4)"}.get(mode, "out")
sbx = Sandbox.connect(sid)
print(sid, sbx.commands.run("cat /w/status", timeout=30).stdout.strip(), flush=True)
sbx.commands.run(f"cp /w/pipeline.log /w/out/ && tar -C /w -czf /w/out.tgz {select}", timeout=600, request_timeout=660)
blob = bytes(sbx.files.read("/w/out.tgz", format="bytes", request_timeout=3600))
with tarfile.open(fileobj=io.BytesIO(blob)) as t:
    t.extractall(dest, filter="data")
print(sid, "ok", len(blob), flush=True)
