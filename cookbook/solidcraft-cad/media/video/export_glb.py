#!/usr/bin/env python3
"""Turn this run's SolidCraft output into the .glb geometry the video loads.

Every vertex HyperFrames shows comes from a STEP file SolidCraft 0.10.1 wrote
in this run: the graded design (`examples/good/design.json`, 16 commands) is run
with the very command the judge runs to export its artifacts
(`solidcraft-cli run --out part.step --out part.stl`, judge/solidcraft_judge.py),
and the build-stage prefixes and the parametric thickness sweep are run the same
way with SolidCraft's own output. The .glb is a mesh of that exact STEP, so the
footage is the graded solid rather than a redrawn stand-in.

Writes:
    assets/part.glb         the graded 6 mm part
    assets/stage{N}.glb     the build stages (prefixes of the 16-command script)
    assets/sweep{T}.glb     the parametric sweep rebuilds

Usage: export_glb.py [--media DIR] [--assets DIR]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MEDIA = Path(__file__).resolve().parent.parent
DEMO = MEDIA.parent
CLI = Path.home() / ".local/solidcraft-0.10.1-linux-x86_64/bin/solidcraft-cli"

# The build stages the video steps through, as prefixes of the graded script
# (the same cut points media/make_media.py snapshots). Every prefix must already
# have produced a body, or `solidcraft-cli run --out` has nothing to export:
#   stage11  the plate extruded by `thickness`                 (commands 1-11)
#   stage15  + the boss sketch on the plane offset by thickness  (commands 1-15)
#   stage16  + the boss extruded and joined -> the graded solid  (all 16)
# command 10 only finishes the sketch, so the footage starts at the first solid.
STAGES = [11, 15, 16]
SWEEP_MM = [6.0, 6.5, 7.0, 7.5, 8.0]


def solidcraft(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(CLI), *args], cwd=cwd, capture_output=True,
                          text=True, timeout=600)


def stage_script(commands: int, work: Path) -> Path:
    """A temporary design.json holding the first `commands` of the graded script.

    SolidCraft resolves `--out` relative to the script's own directory, so each
    script is staged in its own scratch dir under `work` and the exports it
    writes stay inside the video's build area rather than in examples/good/.
    """
    full = json.loads((DEMO / "examples/good/design.json").read_text())["commands"]
    if not 0 < commands <= len(full):
        raise SystemExit(f"export_glb: stage prefix {commands} outside 1..{len(full)}")
    d = work / f"stage{commands}"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"stage{commands}.json").write_text(
        json.dumps({"commands": full[:commands]}, indent=1) + "\n")
    return d / f"stage{commands}.json"


def sweep_script(thickness_mm: float, work: Path) -> Path:
    """The graded script with `thickness` changed to thickness_mm."""
    full = json.loads((DEMO / "examples/good/design.json").read_text())["commands"]
    for c in full:
        if c["command"] == "parameters.change" and c.get("params", {}).get("name") == "thickness":
            c["params"]["expression"] = f"{thickness_mm} mm"
    d = work / f"sweep{thickness_mm}"
    d.mkdir(parents=True, exist_ok=True)
    name = f"sweep{thickness_mm}.json"
    (d / name).write_text(json.dumps({"commands": full}, indent=1) + "\n")
    return d / name


def export_step(script: Path, out_step: Path) -> None:
    """Run SolidCraft exactly as the judge does: `run --out part.step --out part.stl`."""
    proc = solidcraft(["run", script.name, "--out", out_step.name,
                       "--out", out_step.with_suffix(".stl").name, "--quiet"], script.parent)
    tail = "\n".join((proc.stderr or "").splitlines()[-5:])
    if proc.returncode != 0 or not out_step.is_file():
        raise SystemExit(f"export_glb: solidcraft-cli run failed for {script.name}: {tail}")


def step_to_glb(step: Path, glb: Path) -> None:
    """Mesh the STEP with OpenCascade and write glTF (RWGltf_CafWriter)."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.Message import Message_ProgressRange
    from OCP.RWGltf import RWGltf_CafWriter
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFApp import XCAFApp_Application
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.collections import (
        IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString,
    )

    reader = STEPControl_Reader()
    if reader.ReadFile(str(step)) != 1:
        raise SystemExit(f"export_glb: cannot read STEP file {step}")
    reader.TransferRoots()
    shape = reader.OneShape()
    BRepMesh_IncrementalMesh(shape, 0.015, False, 0.5, True)  # mm, matches the STL gate

    fmt = TCollection_ExtendedString("MDTV-XCAF")
    doc = TDocStd_Document(fmt)
    XCAFApp_Application.GetApplication_s().NewDocument(fmt, doc)
    XCAFDoc_DocumentTool.ShapeTool_s(doc.Main()).AddShape(shape, False)

    writer = RWGltf_CafWriter(TCollection_AsciiString(str(glb)), True)
    info = IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString()
    if not writer.Perform(doc, info, Message_ProgressRange()):
        raise SystemExit(f"export_glb: glTF export failed for {step}")


def build(script: Path, glb: Path, work: Path) -> None:
    step = script.with_suffix(".step")
    export_step(script, step)
    step_to_glb(step, glb)
    print(f"export_glb: {glb.name} ({glb.stat().st_size} bytes) from {script.name}")


def stage_good(work: Path) -> Path:
    """The graded design script, staged in its own scratch directory."""
    d = work / "good"
    d.mkdir(parents=True, exist_ok=True)
    (d / "design.json").write_bytes((DEMO / "examples/good/design.json").read_bytes())
    return d / "design.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--assets", type=Path, default=None)
    args = ap.parse_args()
    assets = args.assets or Path(__file__).resolve().parent / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    if not CLI.is_file():
        raise SystemExit(f"export_glb: {CLI} not found; run judge/setup.sh first")

    with tempfile.TemporaryDirectory(prefix="solidcraft-glb-") as tmp:
        work = Path(tmp)
        build(stage_good(work), assets / "part.glb", work)
        for n in STAGES:
            build(stage_script(n, work), assets / f"stage{n}.glb", work)
        for t in SWEEP_MM:
            build(sweep_script(t, work), assets / f"sweep{t}.glb", work)
    print("export_glb: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
