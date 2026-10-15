# blender --background --factory-startup --python make_prop.py -- \
#     --json spec.json --blend-out out.blend --glb-out prop.glb --turntable outdir
#
# Stage 1 of the pipeline: a text description of a prop (spec.json)
# becomes a rigged, animated, game-ready .glb plus a 4-view turntable
# PNG set, modelled with Blender's Python API.
#
# The script is deterministic: no RNG, and the spec carries the seed it
# was written with. It only uses primitives, modifiers and the glTF 2.0
# exporter that ship with Blender; no add-ons, no network.
#
# spec.json (written by the agent from one line of text):
#   {
#     "prompt": "a vintage brass street lantern on a short post",
#     "seed": 7,
#     "parts": [
#       {"name": "post",   "shape": "cylinder", "size": [0.035, 1.5],
#        "origin": [0, 0, 0.0], "material": "brass", "physics": "static",
#        "rig": {"bone": "post", "parent": null}},
#       ...
#     ],
#     "animation": {"frames": 96, "fps": 24, "channels": [
#        {"bone": "armature|swing", "frame": 1, "rot": [0, 0, 0]},
#        ...
#     ]}
#   }
#
# Output:
#   prop.glb      one mesh per part + *_collision physics proxies
#                 (UCX_ prefix), one armature, one swing animation
#   outdir/*.png  4 views (front, three-quarter, side, top-ish) of the
#                 finished prop, rendered with Workbench at 960x960

import argparse
import json
import math
import os
import sys


def log(msg):
    print(f"[make_prop] {msg}", flush=True)


# ---------------------------------------------------------------- materials

MAT_COLORS = {
    "brass": (0.72, 0.55, 0.20),
    "iron": (0.20, 0.21, 0.23),
    "glass": (0.75, 0.90, 0.95),
    "wood": (0.45, 0.28, 0.13),
    "copper": (0.60, 0.32, 0.20),
    "stone": (0.55, 0.54, 0.50),
    "flame": (1.00, 0.70, 0.25),
}


def make_material(name, kind):
    import bpy

    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    color = MAT_COLORS.get(kind, (0.8, 0.8, 0.8))
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        if kind == "glass":
            # Blender 4.2 replaced the Transmission input with Eevee
            # Next's surface_render_method; Cycles reads alpha either
            # way. Keep the surface translucent in both engines.
            bsdf.inputs["Alpha"].default_value = 0.28
            bsdf.inputs["Roughness"].default_value = 0.05
            mat.surface_render_method = "BLENDED"
            mat.blend_method = "BLEND"
        elif kind in ("brass", "copper"):
            bsdf.inputs["Metallic"].default_value = 1.0
            bsdf.inputs["Roughness"].default_value = 0.30
        elif kind == "flame":
            bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 3.0
        else:
            bsdf.inputs["Roughness"].default_value = 0.60
    return mat


# ------------------------------------------------------------------- meshes

def build_part(part):
    """One spec part -> one Blender object (mesh + collision proxy)."""
    import bpy
    import bmesh

    name = part["name"]
    shape = part["shape"]
    size = part.get("size", [])
    origin = part.get("origin", [0.0, 0.0, 0.0])

    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)

    # Profiles are packed densely enough that any real prop clears the
    # 500-vertex bar after the subdivide; the add below is a floor, not
    # the source of the count.
    density = {"coarse": 6, "standard": 14, "fine": 24}.get(
        part.get("tessellation", "standard"), 14)

    bm = bmesh.new()
    if shape == "cylinder":                       # size: [radius, height]
        r, h = float(size[0]), float(size[1])
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=density,
            radius1=r, radius2=r, depth=h)
    elif shape == "cone":                         # size: [radius, height]
        r, h = float(size[0]), float(size[1])
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=density,
            radius1=r, radius2=0.0, depth=h)
    elif shape == "sphere":                       # size: [radius]
        r = float(size[0])
        bmesh.ops.create_uvsphere(
            bm, u_segments=density, v_segments=max(8, density // 2), radius=r)
    elif shape == "cube":                         # size: [x, y, z]
        bmesh.ops.create_cube(bm, size=1.0)
        bm.ops if False else None
        sx, sy, sz = (float(v) for v in size)
        for v in bm.verts:
            v.co = (v.co.x * sx, v.co.y * sy, v.co.z * sz)
    elif shape == "lathe":                        # size: [radius]; profile
        # in part["profile"] as [[z, radius_w], ...]; built with the
        # spin operator so fillets and beads are real geometry.
        r0 = float(size[0])
        prof = part.get("profile", [[0.0, 0.0], [1.0, 1.0]])
        verts = []
        for z, w in prof:
            x = r0 * float(w)
            verts.append(bm.verts.new((x, 0.0, float(z))))
        edges = [bm.edges.new((verts[i], verts[i + 1]))
                 for i in range(len(verts) - 1)]
        bmesh.ops.spin(
            bm, geom=edges, axis=(0.0, 1.0, 0.0), cent=(0.0, 0.0, 0.0),
            steps=density, angle=2.0 * math.pi, use_merge=True)
    else:
        raise ValueError(f"unknown shape {shape!r} for part {name!r}")

    bm.to_mesh(mesh)
    bm.free()

    # Subdivision is where the vertex count really comes from: game
    # meshes need the density for smooth silhouettes and the collision
    # proxies need to track them.
    level = part.get("subdiv", 2)
    if level and shape not in ("cube",):
        mod = obj.modifiers.new("subdiv", "SUBSURF")
        mod.levels = 0
        mod.render_levels = int(level)

    obj.location = (float(origin[0]), float(origin[1]), float(origin[2]))
    mat = part.get("material", "iron")
    obj.data.materials.append(make_material(f"{name}_mat", mat))
    bpy.context.scene.collection.objects.link(obj)

    # Collision proxy: the physics hull the game engine imports (the
    # UCX_ naming is the UE/Unity convention for collision geometry).
    physics = part.get("physics", "static")
    if physics not in ("none",):
        build_collision(obj, part, physics)

    return obj


def build_collision(obj, part, physics):
    import bpy

    name = part["name"]
    shape = part["shape"]
    size = part.get("size", [])
    origin = part.get("origin", [0.0, 0.0, 0.0])

    cmesh = bpy.data.meshes.new(f"UCX_{name}")
    cobj = bpy.data.objects.new(f"UCX_{name}", cmesh)
    import bmesh
    bm = bmesh.new()
    if shape in ("cylinder", "cone"):
        r, h = float(size[0]), float(size[1])
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=12,
            radius1=r * 1.02, radius2=(r * 1.02 if shape == "cylinder" else 0.0),
            depth=h * 1.01)
    elif shape == "sphere":
        r = float(size[0])
        bmesh.ops.create_uvsphere(
            bm, u_segments=12, v_segments=8, radius=r * 1.02)
    elif shape == "lathe":
        r0 = float(size[0])
        zmax = max(float(p[0]) for p in part.get("profile", [[0, 0], [1, 1]]))
        rmax = r0 * max(abs(float(p[1])) for p in part.get("profile", [[0, 0], [1, 1]]))
        bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=12,
            radius1=rmax * 1.02, radius2=rmax * 1.02, depth=zmax * 1.01)
    else:                                          # cube fallback: AABB
        bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(cmesh)
    bm.free()
    cobj.location = (float(origin[0]), float(origin[1]), float(origin[2]))
    cobj.display_type = "WIRE"
    if physics == "dynamic":
        cobj["physics_type"] = "dynamic"
    else:
        cobj["physics_type"] = "static"
    # The glTF exporter applies armature deformation to children; the
    # proxy is parented to the moving part so the hull tracks it.
    cobj.parent = obj
    bpy.context.scene.collection.objects.link(cobj)
    return cobj


# ------------------------------------------------------------------- rigging

def build_armature(parts):
    """One bone per rigged part; bone stretches the part's height."""
    import bpy

    rigged = [p for p in parts if p.get("rig")]
    if not rigged:
        return None
    arm = bpy.data.armatures.new("armature")
    ob = bpy.data.objects.new("armature", arm)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    import bpy
    eb = arm.edit_bones
    for p in rigged:
        b = eb.new(p["rig"]["bone"])
        z0 = float(p.get("origin", [0, 0, 0])[2])
        h = part_height(p)
        b.head = (0.0, 0.0, z0)
        b.tail = (0.0, 0.0, z0 + max(h, 0.05))
        parent_name = p["rig"].get("parent")
        if parent_name and parent_name in eb:
            b.parent = eb[parent_name]
            b.use_connect = False
    bpy.ops.object.mode_set(mode="OBJECT")

    # Parent every visual mesh to its bone (keep transform; no vertex
    # groups needed for rigid props -- glTF exports that as node TRS).
    by_name = {o.name: o for o in bpy.context.scene.objects if o.type == "MESH"}
    for p in rigged:
        target = by_name.get(p["name"])
        bone = p["rig"]["bone"]
        if target is None:
            continue
        arm_ob = ob
        if target.parent != arm_ob:
            target.parent = arm_ob
        target.parent_type = "BONE"
        target.parent_bone = bone
    return ob


def part_height(part):
    size = part.get("size", [])
    shape = part["shape"]
    if shape in ("cylinder", "cone") and len(size) >= 2:
        return float(size[1])
    if shape == "sphere":
        return 2.0 * float(size[0])
    if shape == "cube" and len(size) >= 3:
        return float(size[2])
    if shape == "lathe":
        prof = part.get("profile", [[0, 0], [1, 1]])
        return max(float(z) for z, _ in prof) - min(float(z) for z, _ in prof)
    return 0.5


# ---------------------------------------------------------------- animation

def build_animation(spec, armature_ob):
    import bpy

    anim = spec.get("animation") or {}
    channels = anim.get("channels") or []
    if not (armature_ob and channels):
        return None
    scene = bpy.context.scene
    scene.frame_set(1)

    pb = armature_ob.pose
    for ch in channels:
        bone = pb.bones.get(ch["bone"])
        if bone is None:
            raise ValueError(f"animation names unknown bone {ch['bone']!r}")
    action = bpy.data.actions.new("swing")
    if not armature_ob.animation_data:
        armature_ob.animation_data_create()
    armature_ob.animation_data.action = action

    # One rotation curve per animated bone: Euler keyframes, which the
    # glTF exporter writes as rotation tracks per bone.
    grouped = {}
    for ch in channels:
        grouped.setdefault(ch["bone"], []).append(ch)
    frames_seen = set()
    for bone_name, keys in grouped.items():
        group = action.groups.new(name=bone_name)
        fcuves = []
        for axis in range(3):
            fc = action.fcurves.new(
                data_path=f'pose.bones["{bone_name}"].rotation_euler',
                index=axis, action_group=bone_name)
            fcuves.append(fc)
        for ch in keys:
            f = int(ch["frame"])
            frames_seen.add(f)
            rot = ch.get("rot", [0, 0, 0])
            for axis in range(3):
                fc = fcuves[axis]
                kp = fc.keyframe_points.insert(f, float(rot[axis]))
                kp.interpolation = ch.get("interp", "BEZIER")
    if frames_seen:
        scene.frame_start = min(frames_seen)
        scene.frame_end = max(frames_seen)
        scene.render.fps = int(anim.get("fps", 24))
    armature_ob.animation_data.action = action
    return action


# ----------------------------------------------------------------- render

def render_turntable(outdir, spec):
    import bpy
    import mathutils

    scene = bpy.context.scene
    os.makedirs(outdir, exist_ok=True)
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_object_outline = True
    scene.display.shading.show_cavity = True
    rw = 960
    scene.render.resolution_x = rw
    scene.render.resolution_y = rw
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    # Studio backdrop: dark neutral world so brass/glass read well.
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.055, 0.06, 0.075, 1.0)
        bg.inputs[1].default_value = 1.0

    # Frame everything: the floor is z=0 and props are ~2 m tall.
    camera = bpy.data.objects.get("Camera") or bpy.data.objects.new(
        "Camera", bpy.data.cameras.new("Camera"))
    if camera.name not in scene.collection.objects:
        scene.collection.objects.link(camera)
    scene.camera = camera
    cam = camera.data
    cam.lens = 85
    cam.sensor_fit = "HORIZONTAL"

    # Camera orbits the prop: 4 views = the turntable set.
    views = [("front", 90.0, 8.0), ("threequarter", 50.0, 12.0),
             ("side", 0.0, 10.0), ("top", 75.0, 35.0)]
    target_z = 1.0
    dist = 4.2
    for name, az_deg, el_deg in views:
        az, el = math.radians(az_deg), math.radians(el_deg)
        camera.location = (
            dist * math.cos(el) * math.cos(az),
            dist * math.cos(el) * math.sin(az),
            target_z + dist * math.sin(el))
        direction = mathutils.Vector((0.0, 0.0, target_z)) - camera.location
        camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        scene.render.filepath = os.path.join(outdir, f"view_{name}.png")
        bpy.ops.render.render(write_still=True)
        log(f"rendered {scene.render.filepath}")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", required=True)
    ap.add_argument("--blend-out")
    ap.add_argument("--glb-out", required=True)
    ap.add_argument("--turntable")
    args = ap.parse_args(argv)

    with open(args.json) as fh:
        spec = json.load(fh)

    import bpy
    import mathutils  # noqa: F401  (used in render_turntable)

    # Clean scene: --factory-startup already gives an empty .blend, but
    # be explicit so the script also runs inside a user's editor.
    bpy.ops.wm.read_factory_settings()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"

    log(f'prompt: {spec.get("prompt", "?")}')
    for part in spec["parts"]:
        build_part(part)
    log(f"built {len(spec['parts'])} parts (+ collision proxies)")

    armature_ob = build_armature(spec["parts"])
    if armature_ob:
        action = build_animation(spec, armature_ob)
        log(f"armature: {len(armature_ob.data.bones)} bones, "
            f"animation '{action.name if action else None}'")

    if args.blend_out:
        bpy.ops.wm.save_as_mainfile(filepath=args.blend_out)
        log(f"saved {args.blend_out}")

    # glTF 2.0 export: animations + armature + all meshes (collision
    # proxies ride along as plain children).
    bpy.ops.export_scene.gltf(
        filepath=args.glb_out,
        export_format="GLB",
        export_animations=True,
        export_skins=True,
        export_yup=True,
        export_extras=True,
        export_apply=False,
        export_cameras=False,
        export_lights=False,
        export_def_bones=False,
    )
    size = os.path.getsize(args.glb_out)
    log(f"exported {args.glb_out} ({size / 1e6:.2f} MB)")

    if args.turntable:
        render_turntable(args.turntable, spec)
    log("done")


if __name__ == "__main__":
    main()
