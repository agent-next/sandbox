"""Render in a fresh sandbox, transfer evidence with sbx, always confirm cleanup."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import time

MEDIA = Path(__file__).resolve().parent
DEMO = MEDIA.parent
spec = importlib.util.spec_from_file_location("studio_runner", DEMO / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def upload(sid, path, destination):
    encoded = base64.b64encode(path.read_bytes()).decode()
    code = (f"import pathlib,base64;p=pathlib.Path({destination!r});"
            f"p.parent.mkdir(parents=True,exist_ok=True);"
            f"p.write_bytes(base64.b64decode({encoded!r}))")
    runner.sbx("exec", sid, "python3 -c " + shlex.quote(code))


def download(sid, remote, local, size, digest):
    local.parent.mkdir(parents=True, exist_ok=True)
    if local.exists() and local.stat().st_size == size and hashlib.sha256(
            local.read_bytes()).hexdigest() == digest:
        return
    partial = local.with_name(local.name + ".partial")
    with partial.open("wb") as stream:
        for offset in range(0, size, 196608):
            code = ("import base64;"
                    f"f=open({remote!r},'rb');f.seek({offset});"
                    "print(base64.b64encode(f.read(196608)).decode())")
            # A stalled exec transport once cost a whole transfer; retry chunks.
            for attempt in range(3):
                try:
                    text = runner.sbx("exec", sid, "--timeout", "120",
                                      "python3 -c " + shlex.quote(code))
                    break
                except RuntimeError:
                    if attempt == 2:
                        raise
                    time.sleep(3 * attempt + 1)
            stream.write(base64.b64decode(text, validate=True))
    if partial.stat().st_size != size or hashlib.sha256(
            partial.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f"transfer checksum mismatch: {local.name}")
    partial.replace(local)


def collect(sid):
    code = ("import pathlib,hashlib,json;"
            f"root=pathlib.Path({runner.REMOTE!r});"
            "files=list((root/'media/source').glob('*.png'))+"
            "[root/'media/source/render.json',root/'outputs-selftest/selftest.json']+"
            "list((root/'outputs-selftest').glob('*/hero.png'))+"
            "list((root/'outputs-selftest').glob('*/rim-on.png'));"
            "print(json.dumps([{'name':str(p.relative_to(root)),"
            "'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}"
            " for p in files]))")
    listing = json.loads(runner.sbx("exec", sid, "python3 -c " + shlex.quote(code)))
    def transfer(entry):
        name = entry["name"]
        if name.startswith("media/source/"):
            target = MEDIA / "source" / Path(name).name
        elif name == "outputs-selftest/selftest.json":
            target = MEDIA / "data/selftest.json"
        else:
            target = MEDIA / "source" / Path(name).parent.name / Path(name).name
        download(sid, runner.REMOTE + "/" + name, target, entry["size"], entry["sha256"])
        print(f"downloaded {name}: {entry['size']} bytes sha256={entry['sha256']}",
              flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(transfer, listing))
    (MEDIA / "data").mkdir(exist_ok=True)
    (MEDIA / "data/transfers.json").write_text(json.dumps(listing, indent=2) + "\n")
    (MEDIA / "data/capture.json").write_text(json.dumps({
        "mode": "single_sandbox",
        "sandbox": sid,
        "proof_command": "sh judge/selftest.sh --seed 17",
        "proof_backend": "blender sandbox",
    }, indent=2) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sandbox", help="collect an already-finished development render")
    args = p.parse_args()
    sid = args.sandbox
    try:
        if not sid:
            sid = runner.sbx("create", "--template", "blender", "--timeout-min", "90")
            print(f"media sandbox={sid}", flush=True)
            runner.remote_step(sid, "snapshot", runner.snapshot(), 120)
            upload(sid, MEDIA / "render.py", runner.REMOTE + "/media/render.py")
            prefix = "cd " + runner.REMOTE + " && "
            runner.remote_step(sid, "setup", prefix + "sh judge/setup.sh", 60)
            runner.remote_step(sid, "selftest", prefix + "sh judge/selftest.sh", 600)
            runner.remote_step(sid, "media-render", prefix +
                               "blender -b --factory-startup --python-exit-code 1 -t 4 "
                               "-P media/render.py -- --out media/source --seed 17", 3000)
        collect(sid)
    finally:
        if sid:
            runner.cleanup(sid)


if __name__ == "__main__":
    main()
