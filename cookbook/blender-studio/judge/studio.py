"""Original implementation of the blender template's procedural studio recipe.

Reference: template blender on https://sbx.agent-next.com, product_shot.py
SHA-256 0717b9cec97dffc0d857ce65eacead84aaeefa314cfeed61b08da027d7cf87a4.
No external assets or third-party source are vendored.
"""
import math

import bpy
from mathutils import Vector


def material(name, **values):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    for name, value in values.items():
        shader.inputs[name].default_value = value
    return mat


def smooth(obj, mat):
    obj.data.materials.append(mat)
    for face in obj.data.polygons:
        face.use_smooth = True
    return obj


def light(name, position, target, energy, size, color):
    data = bpy.data.lights.new(name, "AREA")
    data.energy, data.size, data.color = energy, size, color
    obj = bpy.data.objects.new(name, data)
    obj.location = position
    obj.rotation_euler = (Vector(target) - Vector(position)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.collection.objects.link(obj)
    return obj


def build_scene(settings):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    profile = [(-14, 0), (-6, 0), (-2, 0), (1, 0)]
    profile += [(1 + 4 * math.sin(i * math.pi / 32),
                 4 - 4 * math.cos(i * math.pi / 32)) for i in range(1, 17)]
    profile += [(5, 8), (5, 30)]
    vertices = [(x, y, z) for x in (-40, 40) for y, z in profile]
    n = len(profile)
    faces = [(i, i + 1, n + i + 1, n + i) for i in range(n - 1)]
    mesh = bpy.data.meshes.new("Sweep")
    mesh.from_pydata(vertices, [], faces)
    sweep = bpy.data.objects.new("Cyclorama", mesh)
    bpy.context.collection.objects.link(sweep)
    smooth(sweep, material("Backdrop", **{
        "Base Color": (0.16, 0.17, 0.2, 1), "Roughness": 0.8}))
    if settings["seam_height"]:
        bpy.ops.mesh.primitive_cube_add(
            location=(0, 4.7, settings["seam_height"]), scale=(20, 0.1, 0.06))
        seam = bpy.context.object
        seam.name = "Seam"
        smooth(seam, material("SeamBlack", **{"Base Color": (0.001, 0.001, 0.001, 1)}))

    spin = bpy.data.objects.new("Turntable", None)
    bpy.context.collection.objects.link(spin)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=1.35, depth=0.5,
                                       location=(0, 0, 0.25))
    plinth = bpy.context.object
    plinth.name = "Plinth"
    bevel = plinth.modifiers.new("SoftEdge", "BEVEL")
    bevel.width, bevel.segments = 0.04, 3
    smooth(plinth, material("Stone", **{
        "Base Color": (0.035, 0.035, 0.04, 1), "Roughness": 0.18,
        "Coat Weight": 0.6, "Coat Roughness": 0.05}))
    bpy.ops.mesh.primitive_monkey_add(
        location=(settings["hero_x"], 0, 1.33),
        rotation=(math.radians(-10), 0, math.radians(22)))
    hero = bpy.context.object
    hero.name = "Hero"
    sub = hero.modifiers.new("Subsurf", "SUBSURF")
    sub.levels = sub.render_levels = 2
    smooth(hero, material("CarPaint", **{
        "Base Color": (0.62, 0.008, 0.012, 1), "Roughness": 0.25,
        "Coat Weight": 1.0, "Coat Roughness": 0.03}))
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=24, radius=0.55,
                                        location=(-2.4, 1.0, 0.55))
    glass = bpy.context.object
    glass.name = "GlassOrb"
    smooth(glass, material("Glass", **{
        "Base Color": (0.95, 0.97, 1, 1), "Roughness": 0.0,
        "Transmission Weight": 1.0, "IOR": 1.5}))
    bpy.ops.mesh.primitive_torus_add(major_radius=0.48, minor_radius=0.16,
                                    major_segments=64, minor_segments=24,
                                    location=(2.45, 0.8, 0.16))
    ring = bpy.context.object
    ring.name = "GoldRing"
    smooth(ring, material("Gold", **{
        "Base Color": (1, 0.71, 0.29, 1), "Metallic": 1.0, "Roughness": 0.18}))
    products = bpy.data.collections.new("Products")
    backdrop = bpy.data.collections.new("Backdrop")
    backdrop.objects.link(sweep)
    for obj in (plinth, hero, glass, ring):
        products.objects.link(obj)
    for obj in (plinth, hero):
        obj.parent = spin
    spin.driver_add("rotation_euler", 2).driver.expression = (
        f"2 * pi * (frame - 1) / {settings['period']}")
    light("Key", (-4.5, -4, 5.5), (0, 0, 1.1), settings["key_energy"],
          3, (1, 0.95, 0.88))
    rim = light("Rim", (3.5, 4.5, 4), (0, 0, 1.2), 900, 2.5, (0.75, 0.85, 1))
    if settings["rim_link"]:
        rim.light_linking.receiver_collection = products
    halo = light("Halo", (0, -1, 2.2), (0, 5, 2.6), 900, 1.5, (0.85, 0.9, 1))
    if settings["halo_link"]:
        halo.light_linking.receiver_collection = backdrop
    light("Fill", (5, -4, 1.8), (0, 0, 0.9), 120, 5, (1, 1, 1))
    light("Top", (0, 0.5, 8), (0, 0.5, 0), 180, 4, (1, 1, 1))
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.02, 0.022, 0.026, 1)
    scene.world = world
    data = bpy.data.cameras.new("Camera")
    data.lens = 58
    camera = bpy.data.objects.new("Camera", data)
    camera.location = (0, settings["camera_y"], 2.3)
    camera.rotation_euler = (Vector((0, 0, 1.25)) - camera.location).to_track_quat(
        "-Z", "Y").to_euler()
    bpy.context.collection.objects.link(camera)
    scene.camera = camera
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Punchy"
    scene.view_settings.exposure = settings["exposure"]
    scene.frame_start, scene.frame_end = 1, 12
    return scene


def configure(scene, seed, width=256, height=144, samples=8):
    scene.render.engine = "CYCLES"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 4
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.cycles.device = "CPU"
    scene.cycles.seed = seed
    scene.cycles.use_animated_seed = False
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = False
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 6
    scene.cycles.transmission_bounces = 6
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
