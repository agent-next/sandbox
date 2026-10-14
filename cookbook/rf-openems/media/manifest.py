#!/usr/bin/env python3
"""MANIFEST.json -- provenance for each media artifact.

Every entry names the real source data files under media/data/ (written
by grade.sh --json / grade.py --trace / selftest.sh via make_data.sh)
and the exact command that built the artifact. The sha256 of each
source file is recorded too, so the committed inputs of every figure
are verifiable.
"""
import hashlib
import json
import os

MEDIA = os.path.dirname(os.path.abspath(__file__))

FILES = {
    "result.png": dict(
        shows="S11(dB) vs frequency of the judged-good antenna from the "
              "grader's real sweep trace (good__s11_artifact.csv), the "
              "judge's independent re-derivation from the raw openEMS "
              "port time series (G6) and the fine-mesh re-run (G8); red "
              "dashed -10 dB pass line (G4), shaded 2.45 GHz +-2 % band "
              "(G5), measured min S11 annotated; right panel: oracle "
              "line probe phases and eeff vs Hammerstad-Jensen (G7).",
        sources=["data/verdicts/good.json",
                 "data/traces/good__s11_artifact.csv",
                 "data/traces/good__s11_judge.csv",
                 "data/traces/good__s11_fine.csv"],
        command="media/make_media.sh -> $RF_PY media/fig_result.py"),
    "loop.png": dict(
        shows="Agent-loop replay (bad -> partly fixed -> good; a replay "
              "of real grade.sh JSONs, not a live agent trace) with the "
              "per-iteration verdict, and the self-test kill table: "
              "each mutant's killer gate with the measured value vs "
              "limit parsed from its verdict JSON, plus the good row "
              "and the kill rate from selftest.txt.",
        sources=["data/verdicts/good.json",
                 "data/verdicts/bad_nan_er.json",
                 "data/verdicts/bad_substrate_er.json",
                 "data/verdicts/bad_thick_substrate.json",
                 "data/verdicts/bad_coarse_mesh.json",
                 "data/verdicts/bad_patch_length.json",
                 "data/verdicts/bad_no_ground.json",
                 "data/verdicts/bad_feed_center.json",
                 "data/selftest.txt"],
        command="media/make_media.sh -> $RF_PY media/fig_loop.py"),
    "demo.mp4": dict(
        shows="30 s, 1920x1080 30 fps: title; S11 curves of the "
              "replayed iterations in a fixing agent's order (each from "
              "its own grade.py --trace CSV, with the gate that killed "
              "it and the measured value vs limit; sanity-killed cases "
              "show no trace, honestly); the good design with G6/G8 "
              "overlays and all-gate readout; closing selftest kill "
              "rate. Labelled on the title card as a replay of real "
              "grade runs, not a live agent trace. No field snapshots: "
              "this openEMS setup writes no 3D field dumps (see "
              "media/REVIEW.md).",
        sources=["data/verdicts/*.json", "data/traces/*.csv",
                 "data/selftest.txt"],
        command="media/make_media.sh -> $RF_PY media/make_video.py "
                "(lossless master: media/master/demo_lossless.mp4, "
                "-crf 0, git-ignored)"),
}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expand(sources):
    out = []
    for s in sources:
        if "*" in s:
            d = os.path.dirname(s)
            pat = os.path.basename(s).replace("*", "")
            out += sorted(os.path.join(d, p)
                          for p in os.listdir(os.path.join(MEDIA, d))
                          if pat in p and not p.startswith("."))
        else:
            out.append(s)
    return out


def main():
    out = {
        "demo": "cookbook/rf-openems",
        "regenerate_data": "bash media/make_data.sh   (re-runs the judge)",
        "regenerate_media": "bash media/make_media.sh (reads media/data/)",
        "tools": {
            "python": "3.11.2 (judge/setup.sh sysroot)",
            "matplotlib": "3.9.2 (judge/setup.sh, hash-pinned wheel)",
            "numpy": "1.24.2 (judge/setup.sh, sha256-pinned .deb)",
            "ffmpeg": "imageio-ffmpeg 0.5.1 static build "
                      "(judge/setup.sh, hash-pinned wheel)",
        },
        "files": {},
    }
    for name, meta in FILES.items():
        p = os.path.join(MEDIA, name)
        if not os.path.exists(p):
            raise SystemExit(f"missing {p} -- build media first")
        entry = dict(meta, sha256=sha256(p), bytes=os.path.getsize(p))
        entry["source_sha256"] = {
            s: sha256(os.path.join(MEDIA, s)) for s in expand(meta["sources"])}
        out["files"][name] = entry
    with open(os.path.join(MEDIA, "MANIFEST.json"), "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(f"wrote {os.path.join(MEDIA, 'MANIFEST.json')}")


if __name__ == "__main__":
    main()
