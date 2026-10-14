"""Closed-form analytic oracle for the cad-verify-back judge.

Every expected number is derived from the spec JSON alone, by hand-derived
formulas — never from the artifact, and never by re-running the CAD kernel.
The judge writes these into the verdict so a pass can be checked by hand.

Units: mm and mm^3.
"""
import math


def expected(spec):
    """Return the dict of analytic expectations for the spec."""
    L = spec["plate_l"]
    W = spec["plate_w"]
    T = spec["plate_t"]
    bore = spec["bore_d"]
    boss_od = spec["boss_od"]
    boss_h = spec["boss_h"]
    n = spec["bolt_n"]
    d = spec["bolt_d"]
    pcd = spec["pcd"]

    r = pcd / 2.0
    # bolt hole centres: evenly spaced on the PCD starting at 0 deg (+X)
    centres = [
        (r * math.cos(2.0 * math.pi * i / n), r * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]
    # expected angular steps between consecutive holes, degrees
    step = 360.0 / n

    # volume, closed form:
    #   plate box  - bore hole through plate - bolt holes through plate
    #   + boss annulus (boss_od outside, bore already removed by cutThruAll)
    v_box = L * W * T
    v_bore = math.pi / 4.0 * bore**2 * T
    v_bolts = n * math.pi / 4.0 * d**2 * T
    v_boss = math.pi / 4.0 * (boss_od**2 - bore**2) * boss_h
    volume = v_box - v_bore - v_bolts + v_boss

    # design rules, closed form:
    #   edge distance of a bolt hole = distance from its centre to the
    #   nearest plate edge, minus its radius
    edge_d = min(
        min(L / 2.0 - abs(cx), W / 2.0 - abs(cy)) - d / 2.0
        for (cx, cy) in centres
    )
    #   ligament between adjacent bolt holes = centre distance - d
    lig = 2.0 * r * math.sin(math.pi / n) - d
    #   ligament between bore and each bolt hole
    lig_bore = r - bore / 2.0 - d / 2.0
    #   ligament between boss OD and bolt holes (boss is above; holes punch
    #   through the plate under the boss annulus if they overlapped it)
    lig_boss = r - boss_od / 2.0 - d / 2.0

    return {
        "bbox": [L, W, T + boss_h],
        "volume_mm3": volume,
        "volume_terms": {
            "plate_box": v_box,
            "bore_minus": v_bore,
            "bolts_minus": v_bolts,
            "boss_plus": v_boss,
        },
        "bore_d": bore,
        "bore_centre": (0.0, 0.0),
        "bolt_d": d,
        "bolt_centres": centres,
        "pcd_radius": r,
        "angular_step_deg": step,
        "boss_od": boss_od,
        "boss_h": boss_h,
        "min_edge_distance_mm": edge_d,
        "min_ligament_mm": min(lig, lig_bore, lig_boss),
        "ligament_bolts_mm": lig,
        "ligament_bore_mm": lig_bore,
        "ligament_boss_mm": lig_boss,
        "dxf_circle_count": n + 2,  # bore + boss OD + bolt holes
        "outline_corners": [
            (L / 2.0, W / 2.0), (-L / 2.0, W / 2.0),
            (-L / 2.0, -W / 2.0), (L / 2.0, -W / 2.0),
        ],
    }
