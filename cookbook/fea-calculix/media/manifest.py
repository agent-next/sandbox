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
        shows="Linear-static load ramp of the real good-fine .frd "
              "displacement field (displacement scaled, labelled), full-"
              "load gate readouts, then each of the 9 mutants' failing "
              "gates with measured vs limit from its verdict JSON; "
              "overload-10x, undersized, propped-tip and load-on-ntip "
              "cards embed that mutant's own real deformed field.",
        sources=["data/verdicts/*.json", "work/*/job.frd",
                 "work/*/fields.npz", "work/*/summary.json"],
        command="media/.venv/bin/python media/make_video.py "
                "(master: media/master/demo_lossless.mp4, -crf 0)"),
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
