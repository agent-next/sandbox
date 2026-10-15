"""oracle.py — the independent geometry oracle for the cad-to-usd judge.

Run with the judge venv python (usd-core + cadquery-ocp), e.g.
    $HOME/.venvs/cad2usd-judge/bin/python -I judge/oracle.py ...

Two halves, deliberately independent of the converter under test:

  measure_source(path)  OpenCASCADE (OCP) reads the STEP/IGES source and
      computes a tight exact bbox (BRepBndLib.AddOptimal) and the exact
      total face area (BRepGProp.SurfaceProperties).
  measure_usd(path)     usd-core (pxr) reads the USDA stage and computes
      the world-space mesh bbox (BBoxCache over every Mesh prim) and the
      total triangle area by walking points/faceVertexCounts/
      faceVertexIndices and fan-triangulating, in scene units.

Units: sources are in millimeters (RC-Car-CAD STEP/IGES authoring units);
a USD stage with metersPerUnit mpu stores the same geometry in scene
units where 1 scene unit = mpu metres. Both are converted to mm before
comparison (oracles and measurements below are in mm^2 / mm).
"""

import json
import math
import sys

# part keys in a fixed order — every gate reports them in this order
PARTS = [
    ("Servo_Futaba_S3003_v6_step", "Servo Futaba S3003 v6.step"),
    ("Servo_Futaba_S3003_v6_iges", "Servo Futaba S3003 v6.iges"),
    ("ShockTowerFront_stp", "ShockTowerFront/_ShockTowerFront.stp"),
]

REQUIRED_MPU = 0.001      # metres per scene unit (mm scene)
REQUIRED_UPAXIS = "Z"
BBOX_TOL = 0.01           # endpoint deltas <= 1% of oracle extent per axis
BBOX_FLOOR_MM = 0.1       # ... or 0.1 mm absolute
AREA_TOL = 0.03           # total area within 3%


def _import_ocp():
    from OCP.STEPControl import STEPControl_Reader
    from OCP.IGESControl import IGESControl_Reader
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_ShapeEnum
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    return dict(locals())


def measure_source(path):
    """OpenCASCADE measurements of a STEP/IGES file, in source (mm) units.

    Returns {"bbox_min": [...], "bbox_max": [...], "area": float,
    "faces": int} or raises ValueError with a message naming the file.
    """
    m = _import_ocp()
    if path.lower().endswith((".igs", ".iges")):
        reader = m["IGESControl_Reader"]()
    else:
        reader = m["STEPControl_Reader"]()
    if reader.ReadFile(path) != 1:  # IFSelect_RetDone
        raise ValueError(f"oracle: OpenCASCADE cannot read {path}")
    reader.TransferRoots()
    shape = reader.OneShape()

    area = 0.0
    faces = 0
    exp = m["TopExp_Explorer"](shape, m["TopAbs_ShapeEnum"].TopAbs_FACE)
    while exp.More():
        props = m["GProp_GProps"]()
        m["BRepGProp"].SurfaceProperties_s(m["TopoDS"].Face_s(exp.Current()),
                                           props)
        area += props.Mass()
        faces += 1
        exp.Next()
    if faces == 0:
        raise ValueError(f"oracle: {path} has no faces")

    box = m["Bnd_Box"]()
    m["BRepBndLib"].AddOptimal_s(shape, box)
    v = box.Get()
    return {"bbox_min": [v[0], v[1], v[2]],
            "bbox_max": [v[3], v[4], v[5]],
            "area": area, "faces": faces}


def _import_pxr():
    from pxr import Usd, UsdGeom, Gf
    return dict(locals())


def measure_usd(path):
    """usd-core measurements of a USDA stage, in scene units.

    Returns {"meters_per_unit", "up_axis", "default_prim", "prims",
    "meshes", "bbox_min", "bbox_max", "area", "triangles"} or raises
    ValueError.
    """
    m = _import_pxr()
    Usd, UsdGeom, Gf = m["Usd"], m["UsdGeom"], m["Gf"]
    stage = Usd.Stage.Open(path)
    if not stage:
        raise ValueError(f"usd: cannot open stage {path}")
    default_prim = stage.GetDefaultPrim()
    if not default_prim or not default_prim.IsValid():
        raise ValueError(f"usd: {path} has no valid defaultPrim")

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                              [UsdGeom.Tokens.default_])
    xc = UsdGeom.XformCache()
    nprim = nmesh = ntri = 0
    area = 0.0
    bmin = Gf.Vec3d(math.inf)
    bmax = Gf.Vec3d(-math.inf)
    for prim in stage.Traverse():
        nprim += 1
        if not prim.IsA(UsdGeom.Mesh):
            continue
        nmesh += 1
        mesh = UsdGeom.Mesh(prim)
        points = mesh.GetPointsAttr().Get()
        counts = mesh.GetFaceVertexCountsAttr().Get()
        idx = mesh.GetFaceVertexIndicesAttr().Get()
        if not (points and counts and idx):
            continue
        # world-space bbox incl. xformOps, accumulated across meshes
        r = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        mn, mx = r.GetMin(), r.GetMax()
        bmin = Gf.Vec3d(min(bmin[0], mn[0]), min(bmin[1], mn[1]),
                        min(bmin[2], mn[2]))
        bmax = Gf.Vec3d(max(bmax[0], mx[0]), max(bmax[1], mx[1]),
                        max(bmax[2], mx[2]))
        # exact triangle area in world space
        xf = xc.GetLocalToWorldTransform(prim)
        wp = [xf.Transform(Gf.Vec3d(p[0], p[1], p[2])) for p in points]
        i0 = 0
        for c in counts:
            ntri += c - 2
            for k in range(1, c - 1):
                a, b, cc = wp[idx[i0]], wp[idx[i0 + k]], wp[idx[i0 + k + 1]]
                u = Gf.Vec3d(b[0] - a[0], b[1] - a[1], b[2] - a[2])
                v = Gf.Vec3d(cc[0] - a[0], cc[1] - a[1], cc[2] - a[2])
                cr = Gf.Vec3d(u[1] * v[2] - u[2] * v[1],
                              u[2] * v[0] - u[0] * v[2],
                              u[0] * v[1] - u[1] * v[0])
                area += 0.5 * cr.GetLength()
            i0 += c
    if nmesh == 0:
        raise ValueError(f"usd: {path} contains no Mesh prims")
    return {"meters_per_unit": UsdGeom.GetStageMetersPerUnit(stage),
            "up_axis": str(UsdGeom.GetStageUpAxis(stage)),
            "default_prim": str(default_prim.GetPath()),
            "prims": nprim, "meshes": nmesh, "triangles": ntri,
            "bbox_min": [bmin[0], bmin[1], bmin[2]],
            "bbox_max": [bmax[0], bmax[1], bmax[2]],
            "area": area}


def to_mm(meas_usd):
    """Convert a measure_usd() result from scene units to millimetres.

    The stage declares metersPerUnit; 1 scene unit = mpu metres, so
    lengths scale by mpu*1000 and areas by (mpu*1000)^2. Returns a copy
    with bbox/area in mm; raises if the scale is not usable.
    """
    s = meas_usd["meters_per_unit"]
    if not isinstance(s, (int, float)) or s <= 0:
        raise ValueError(f"usd: invalid metersPerUnit {s!r}")
    k = s * 1000.0
    out = dict(meas_usd)
    out["bbox_min"] = [v * k for v in meas_usd["bbox_min"]]
    out["bbox_max"] = [v * k for v in meas_usd["bbox_max"]]
    out["area"] = meas_usd["area"] * k * k
    return out


def compare(oracle, usd_mm):
    """Compare an OpenCASCADE measurement against a mm-converted USD one.

    Returns (ok, detail dict) — ok is True only if both the per-axis
    bbox endpoint rule and the area rule pass.
    """
    detail = {"bbox": [], "area_rel": None}
    ok = True
    for ax in range(3):
        o_lo, o_hi = oracle["bbox_min"][ax], oracle["bbox_max"][ax]
        u_lo, u_hi = usd_mm["bbox_min"][ax], usd_mm["bbox_max"][ax]
        extent = max(o_hi - o_lo, 0.0)
        tol = max(BBOX_TOL * extent, BBOX_FLOOR_MM)
        dlo, dhi = abs(u_lo - o_lo), abs(u_hi - o_hi)
        ax_ok = dlo <= tol and dhi <= tol
        ok = ok and ax_ok
        detail["bbox"].append({
            "axis": "xyz"[ax],
            "usd_min": u_lo, "usd_max": u_hi,
            "oracle_min": o_lo, "oracle_max": o_hi,
            "delta_min": dlo, "delta_max": dhi,
            "tol_mm": tol, "pass": ax_ok,
        })
    o_area = oracle["area"]
    rel = abs(usd_mm["area"] - o_area) / o_area
    detail["area_rel"] = rel
    detail["area_pass"] = rel <= AREA_TOL
    ok = ok and detail["area_pass"]
    detail["bbox_pass"] = all(b["pass"] for b in detail["bbox"])
    return ok, detail


def jsonable(obj):
    """Recursively round floats and drop non-JSON values for verdicts."""
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


if __name__ == "__main__":
    # CLI probe: oracle.py <mode> <file>
    #   mode=source -> print the OpenCASCADE measurement as JSON
    #   mode=usd    -> print the usd-core measurement as JSON (scene units)
    mode, target = sys.argv[1], sys.argv[2]
    if mode == "source":
        print(json.dumps(jsonable(measure_source(target)), indent=2))
    elif mode == "usd":
        print(json.dumps(jsonable(measure_usd(target)), indent=2))
    else:
        sys.exit(f"oracle.py: unknown mode {mode!r}")
