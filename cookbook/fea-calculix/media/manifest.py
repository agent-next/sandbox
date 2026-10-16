#!/usr/bin/env python3
"""MANIFEST.json -- provenance for each media artifact."""
import hashlib
import json
import os

MEDIA = os.path.dirname(os.path.abspath(__file__))

FILES = {
    "result.png": dict(
        shows="Deformed cantilever mesh (displacements from the real "
              "good-fine job.frd, x20) coloured by nodal von Mises from "
              "the same .frd, allowable stress 166.7 MPa marked on the "
              "colour bar (spec_limits gate); tip deflection + wall "
              "stress vs mesh size with the +-2% band (convergence "
              "gate); reference-beam FEA/Euler-Bernoulli ratios with the "
              "+-3% band (verification gate).",
        sources=["data/verdicts/good.json", "data/convergence.json",
                 "work/good-fine/job.frd", "work/good-coarse/job.frd",
                 "work/good-fine/mesh.inc", "work/good-coarse/mesh.inc"],
        command="media/.venv/bin/python media/fig_result.py"),
    "loop.png": dict(
        shows="Agent-loop replay (bad -> partly fixed -> good, gates "
              "failing per iteration, a replay of real grade JSONs) plus "
              "the 10-artifact x 3-gate self-test matrix; each red cell "
              "shows the measured value vs the limit from that mutant's "
              "real verdict JSON; script-enforced no-overlap check.",
        sources=["data/verdicts/good.json",
                 "data/verdicts/units-in-metres.json",
                 "data/verdicts/propped-tip.json",
                 "data/verdicts/load-on-ntip.json",
                 "data/verdicts/coarse-mesh.json",
                 "data/verdicts/unconverged.json",
                 "data/verdicts/load-wrong-dof.json",
                 "data/verdicts/overload-10x.json",
                 "data/verdicts/undersized.json",
                 "data/verdicts/no-stress-output.json",
                 "data/selftest.txt"],
        command="media/.venv/bin/python media/fig_loop.py"),
    "demo.mp4": dict(
        shows="Animated cut: the real good-fine .frd field orbited in "
              "3-D (hero at full load; linear-static ramp 0 -> 1000 N; "
              "dive onto the clamped wall), this run's own console replay "
              "at the measured Nx over still-playing footage, the "
              "overload-10x mutant's own field under 10x load, then the "
              "PASS badge + gate rows as a HUD over the still-moving "
              "field; 2.5 s static end card. All overlay numbers are "
              "injected from this run's verdict/selftest/timing files.",
        sources=["data/verdicts/*.json", "data/selftest.txt",
                 "work/run_logs/*.log", "work/run_logs/timing.json",
                 "work/*/job.frd", "work/*/fields.npz",
                 "work/*/summary.json", "clips/*.mp4",
                 "video/index.html"],
        command="bash media/make_media.sh (clips: render_clips.py; "
                "composition: gen_composition.py -> video/index.html; "
                "render: npx hyperframes render (pinned 0.8.99); "
                "encode: ffmpeg -crf 18 -maxrate 1900k -bufsize 3800k "
                "+faststart (VBV cap sized to the <= 8 MiB budget); "
                "master: media/master/demo_hf.mp4)"),
}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    out = {
        "demo": "cookbook/fea-calculix",
        "regenerate": "bash media/make_media.sh",
        "tools": {
            "ccx": "2.20-1 (judge/setup.sh, sha256-pinned .deb)",
            "gmsh": "4.10.0 (judge/setup.sh, sha256-pinned tarball)",
            "python": "media/requirements.txt (matplotlib 3.10.7, "
                      "numpy 2.2.6)",
            "hyperframes": "0.8.99 (media/video/package-lock.json, "
                           "npm ci; published 2026-09-30)",
            "ffmpeg": "distro build (see media/REVIEW.md)",
        },
        "files": {},
    }
    for name, meta in FILES.items():
        p = os.path.join(MEDIA, name)
        if not os.path.exists(p):
            raise SystemExit(f"missing {p} -- build media first")
        out["files"][name] = dict(meta, sha256=sha256(p),
                                  bytes=os.path.getsize(p))
    p = os.path.join(MEDIA, "MANIFEST.json")
    with open(p, "w") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(f"wrote {p}")


if __name__ == "__main__":
    main()
