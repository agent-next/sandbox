#!/usr/bin/env python3
"""Export a STEP file from the demo's own run into the .glb the video loads.

Every vertex the video shows comes from a STEP file this run wrote (SolidCraft
0.10.1, driven by media/make_media.py), so the footage is the graded geometry
itself rather than a redrawn stand-in.

Usage: python3 export_glb.py <in.step> <out.glb>
"""
from __future__ import annotations

import sys

from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.Message import Message_ProgressRange
from OCP.RWGltf import RWGltf_CafWriter
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.collections import IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString

DEFLECTION = 0.015  # mm: fine enough that 3772 triangles match the STL gate


def load_shape(step: str):
    reader = STEPControl_Reader()
    if reader.ReadFile(step) != 1:
        raise SystemExit(f"cannot read STEP file: {step}")
    reader.TransferRoots()
    return reader.OneShape()


def export(step: str, glb: str) -> None:
    shape = load_shape(step)
    BRepMesh_IncrementalMesh(shape, DEFLECTION, False, 0.5, True)

    fmt = TCollection_ExtendedString("MDTV-XCAF")
    doc = TDocStd_Document(fmt)
    app = XCAFApp_Application.GetApplication_s()
    app.NewDocument(fmt, doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    tool.AddShape(shape, False)

    writer = RWGltf_CafWriter(TCollection_AsciiString(glb), True)
    file_info = IndexedDataMap_TCollection_AsciiString_TCollection_AsciiString()
    if not writer.Perform(doc, file_info, Message_ProgressRange()):
        raise SystemExit(f"glTF export failed for {step}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    export(sys.argv[1], sys.argv[2])
    print(f"exported {sys.argv[2]}")
