"""Canonical scene for the gpu-sim-sweep demo.

A 7-DoF Panda-like arm (capsule links, Franka-style joint ranges, position
actuators — written in code, not the official Panda MJCF) next to a table
with 8 boxes dropped onto it from staggered heights. The same XML string is
used byte-for-byte by the CPU reference (single world, mujoco) and by every
GPU sweep point (mujoco_warp, nworld parallel worlds), so CPU and GPU solve
identical physics.

The good artifact embeds canonical_xml() output verbatim; the judge rejects
an artifact whose scene differs (after whitespace normalisation), so only
the numeric sweep parameters are tunable.
"""

# Steady-state position target for the 7 arm joints (rad).
ARM_TARGET = [0.4, -0.35, 0.6, -1.6, 0.2, 1.3, 0.5]

TABLE_TOP = 0.275  # z of the table surface (box centre 0.25, half-size 0.025)
BOX_HALF = 0.04    # half-size of the falling boxes

# name, body pos (rel), capsule from->to, radius, joint axis, range (rad)
LINKS = [
    ("link1", (0, 0, 0.08), (0, 0, 0.00, 0, 0, 0.16), 0.045, (0, 0, 1), (-2.8973, 2.8973)),
    ("link2", (0, 0, 0.16), (0, 0, 0.00, 0, 0, 0.26), 0.045, (0, 1, 0), (-1.7628, 1.7628)),
    ("link3", (0, 0, 0.26), (0, 0, 0.00, 0, 0, 0.12), 0.040, (0, 0, 1), (-2.8973, 2.8973)),
    ("link4", (0, 0, 0.12), (0, 0, 0.00, 0, 0, 0.28), 0.040, (0, 1, 0), (-3.0718, -0.0698)),
    ("link5", (0, 0, 0.28), (0, 0, 0.00, 0, 0, 0.10), 0.035, (0, 0, 1), (-2.8973, 2.8973)),
    ("link6", (0, 0, 0.10), (0, 0, 0.00, 0, 0, 0.12), 0.035, (0, 1, 0), (-0.0175, 3.7525)),
    ("link7", (0, 0, 0.12), (0, 0, 0.00, 0, 0, 0.08), 0.030, (0, 0, 1), (-2.8973, 2.8973)),
]


def _header() -> list:
    # Solver/integrator settings are pinned IN the XML (option element) so the
    # artifact carries the complete physics it wants graded; the defaults of
    # MuJoCo's <option> (timestep 0.002, Euler integrator) are NOT what this
    # demo runs, so all four knobs are explicit.
    return [
        '<mujoco model="arm-and-boxes">',
        "<compiler angle='radian'/>",
        '<option timestep="0.001" integrator="implicitfast" iterations="100"'
        ' gravity="0 0 -9.81"/>',
        "<default>",
        '  <joint type="hinge" damping="8" armature="0.15"/>',
        '  <geom condim="3" friction="1.0 0.005 0.0001" solref="0.01 1"'
        ' solimp="0.99 0.999 0.001 0.5 2" density="1000" rgba="0.8 0.8 0.85 1"/>',
        "</default>",
        "<worldbody>",
        '<geom name="floor" type="plane" size="3 3 0.1"/>',
    ]


def _arm_bodies() -> list:
    out = []
    for i, (name, pos, ft, rad, axis, rng) in enumerate(LINKS):
        out.append(
            f'<body name="{name}" pos="{pos[0]} {pos[1]} {pos[2]}">\n'
            f'  <joint name="joint{i+1}" axis="{axis[0]} {axis[1]} {axis[2]}"'
            f' range="{rng[0]} {rng[1]}"/>\n'
            f'  <geom type="capsule" fromto="{ft[0]} {ft[1]} {ft[2]} {ft[3]} {ft[4]} {ft[5]}"'
            f' size="{rad}"/>\n')
    out.append('<body name="hand" pos="0 0 0.08">'
               '<geom name="hand" type="box" size="0.04 0.06 0.02" pos="0 0 0.02"/></body>')
    out += ["</body>\n" for _ in LINKS]
    return out


def _actuators() -> list:
    xml = ["<actuator>"]
    for i, (_, _, _, _, _, rng) in enumerate(LINKS):
        xml.append(f'<position name="p{i+1}" joint="joint{i+1}" kp="300"'
                   f' ctrlrange="{rng[0]} {rng[1]}" forcerange="-60 60"/>')
    xml.append("</actuator>")
    return xml


def canonical_xml() -> str:
    """The one scene every number in this demo comes from."""
    xml = _header() + _arm_bodies()
    xml.append('<body name="table" pos="0.85 0 0.25">'
               '<geom name="tabletop" type="box" size="0.35 0.35 0.025"/></body>')
    spots = [(-0.2, -0.2), (0, -0.2), (0.2, -0.2), (-0.2, 0), (0.2, 0),
             (-0.2, 0.2), (0, 0.2), (0.2, 0.2)]
    for i, (dx, dy) in enumerate(spots):
        z = 0.50 + 0.30 * (i % 3)
        xml.append(f'<body name="box{i}" pos="{0.85 + dx} {dy} {z}">'
                   f'<freejoint name="boxjoint{i}"/>'
                   f'<geom name="boxgeom{i}" type="box" size="0.04 0.04 0.04"/></body>')
    return "\n".join(xml + ["</worldbody>"] + _actuators() + ["</mujoco>"])


def normalize_xml(xml: str) -> str:
    """Whitespace-insensitive comparison key for scene equality."""
    return " ".join(xml.split())
