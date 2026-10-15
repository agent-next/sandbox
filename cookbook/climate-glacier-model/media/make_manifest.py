#!/usr/bin/env python3
"""Write media/MANIFEST.json: what each media file shows, the command that
produced it, its source data, and its sha256.

Usage: make_manifest.py <demo-dir>
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCENARIOS = ("warm_2p0", "warm_2p4", "warm_2p8")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate,nb_frames,codec_name",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    st = json.loads(out)["streams"][0]
    return {"width": st["width"], "height": st["height"],
            "fps": st["r_frame_rate"], "frames": int(st["nb_frames"]),
            "codec": st["codec_name"]}


def main() -> int:
    demo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent
    media = demo / "media"

    good = json.loads((media / "data" / "verdicts" / "good.json").read_text())
    mutants = [p for p in (media / "data" / "verdicts").glob("*.json")
               if p.stem != "good"]
    killed = sum(1 for p in mutants
                 if not json.loads(p.read_text())["passed"])
    kill_rate = f"{killed}/{len(mutants)}"

    files = {
        "result.png": {
            "shows": "Key figure. Left: the three scenario volume curves from "
                     "the judge's own run of examples/good (solid) against the "
                     "analytic oracle V_exact(t) (dashed), the 50 %-of-V(0) "
                     "crossing rule line, and each measured crossing year. "
                     "Right: the shape gate's measured deviation from the "
                     "analytic volume at every year against the +-2 % pass "
                     "band; the band is the pass line. Worst deviation 0.38 %.",
            "sources": ["data/run/good/volumes.csv",
                        "data/verdicts/good.json"],
            "command": f"{'$HOME/glacier-venv/bin/python'} media/fig_result.py .",
        },
        "loop.png": {
            "shows": "Agent loop and self-test. Left: gates still failing per "
                     "iteration of a real fix sequence (data/loop/iter1..5, "
                     "each graded by judge/grade.sh); the label is the gate the "
                     "judge failed that iteration on (artifact -> zero_melt -> "
                     "final_volume -> figure -> PASS). Right: the self-test "
                     "kill matrix, known-good vs the 13 single-edit mutants, "
                     "each row the gate that killed it.",
            "sources": ["data/verdicts/good.json",
                        "data/verdicts/*.json (13 mutants)",
                        "data/loop/iter1.json .. iter5.json"],
            "command": f"{'$HOME/glacier-venv/bin/python'} media/fig_loop.py .",
        },
        "demo.mp4": {
            "shows": "The simulation itself: the three volume curves draw "
                     "themselves in over the 100-year sweep from the judge's "
                     "own good-run data, with the 50 %-crossing line and each "
                     "scenario's crossing year marked as its curve reaches it; "
                     "30 fps, 1920x1080, H.264 (-crf 18). A lossless master "
                     "(-crf 0) is written to media/master/ (git-ignored).",
            "sources": ["data/run/good/volumes.csv",
                        "data/verdicts/good.json"],
            "command": "bash media/make_media.sh",
        },
    }

    for name, entry in files.items():
        p = media / name
        if not p.is_file():
            print(f"make_manifest: {name} missing", file=sys.stderr)
            return 1
        entry["sha256"] = sha256(p)
        entry["bytes"] = p.stat().st_size

    doc = {
        "demo": "cookbook/climate-glacier-model",
        "regenerate": "bash media/make_media.sh",
        "seed": good["seed"],
        "verdict_passed": good["passed"],
        "kill_rate": kill_rate,
        "tools": {
            "python": "judge/requirements.txt (numpy 2.2.6, matplotlib 3.10.6; "
                      "the venv judge/setup.sh creates)",
            "ffmpeg": "distro build (see RECEIPT.md)",
        },
        "files": files,
    }
    out = media / "MANIFEST.json"
    out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"wrote {out}")
    for name, entry in files.items():
        print(f"  {name}: {entry['bytes']} bytes  sha256 {entry['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
