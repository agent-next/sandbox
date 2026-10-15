"""Numeric physical and artifact gates; no artifact-provided executable code."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
import zlib

import numpy as np

from driver import Renderer

HERE = Path(__file__).resolve().parent
WEIGHTS = np.array([0.2126, 0.7152, 0.0722])
COLOR_FIELDS = {"baseColor", "specularColor", "coatColor", "fuzzColor",
                "emissionColor"}
UNIT_FIELDS = {"baseWeight", "baseMetalness", "baseDiffuseRoughness",
               "specularWeight", "specularRoughness", "coatWeight",
               "coatRoughness", "fuzzWeight", "fuzzRoughness"}
MATERIAL_FIELDS = COLOR_FIELDS | UNIT_FIELDS | {"emissionLuminance", "emissive"}


def kill_owned_tree(pid):
    """Include browser processes even when they create their own process groups."""
    parents = {}
    for status in Path("/proc").glob("[0-9]*/status"):
        try:
            line = next(line for line in status.read_text().splitlines()
                        if line.startswith("PPid:"))
            parents[int(status.parent.name)] = int(line.split()[1])
        except (OSError, StopIteration, ValueError):
            continue
    owned = {pid}
    while True:
        expanded = owned | {child for child, parent in parents.items() if parent in owned}
        if expanded == owned:
            break
        owned = expanded
    for child in sorted(owned, reverse=True):
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass


def checksum():
    return {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(HERE.rglob("*")) if p.is_file()
            and "__pycache__" not in p.parts}


def fields(obj, required, optional=()):
    assert isinstance(obj, dict), "expected object"
    assert set(required) <= obj.keys(), f"missing fields: {set(required) - obj.keys()}"
    assert obj.keys() <= set(required) | set(optional), "unsupported fields"


def number(x, low, high):
    assert type(x) in (int, float) and np.isfinite(x) and low <= x <= high, \
        f"number outside [{low}, {high}]"


def vector(x, low, high, n=3):
    assert isinstance(x, list) and len(x) == n, "invalid vector"
    for v in x:
        number(v, low, high)


def validate(s):
    fields(s, ["seed", "resolution", "spp", "camera", "materials", "spheres",
               "floor", "environment", "lights"])
    assert type(s["seed"]) is int and 0 <= s["seed"] < 32767, "seed budget"
    vector(s["resolution"], 64, 512, 2)
    assert all(type(x) is int and x % 16 == 0 for x in s["resolution"]), \
        "resolution must be 16-pixel aligned"
    assert type(s["spp"]) is int and 16 <= s["spp"] <= 256, "spp budget"
    fields(s["camera"], ["position", "target", "fov"])
    for key in ("position", "target"):
        vector(s["camera"][key], -50, 50)
    number(s["camera"]["fov"], 20, 80)
    assert np.linalg.norm(np.subtract(s["camera"]["position"],
                                     s["camera"]["target"])) > 0.1, "camera direction"
    assert 4 <= len(s["materials"]) <= 6, "material budget"
    for name, m in s["materials"].items():
        assert isinstance(name, str) and name, "material name"
        fields(m, [], MATERIAL_FIELDS)
        for k, v in m.items():
            if k in COLOR_FIELDS:
                vector(v, 0, 1)
            elif k in UNIT_FIELDS:
                number(v, 0, 1)
            elif k == "emissive":
                assert type(v) is bool, "emissive declaration"
            else:
                number(v, 0, 10)
        assert m.get("emissionLuminance", 0) == 0 or m.get("emissive") is True, \
            "G2: undeclared emission"
    assert isinstance(s["spheres"], list) and 3 <= len(s["spheres"]) <= 5, \
        "sphere count"
    sphere_materials = []
    for ball in s["spheres"]:
        fields(ball, ["position", "radius", "material"])
        vector(ball["position"], -10, 10)
        number(ball["radius"], 0.2, 1.5)
        assert ball["material"] in s["materials"], "unknown sphere material"
        assert np.linalg.norm(np.subtract(s["camera"]["position"],
                                         ball["position"])) > ball["radius"] + 0.05, \
            "camera inside sphere"
        sphere_materials.append(ball["material"])
    assert len({json.dumps(s["materials"][name], sort_keys=True)
                for name in sphere_materials}) >= 3, "distinct sphere materials"
    fields(s["floor"], ["y", "size", "material"])
    assert s["floor"]["material"] in s["materials"], "unknown floor material"
    number(s["floor"]["y"], -5, 5)
    number(s["floor"]["size"], 5, 30)
    for ball in s["spheres"]:
        assert abs(ball["position"][1] - ball["radius"] - s["floor"]["y"]) < 0.02, \
            "spheres must rest on floor"
    env = s["environment"]
    assert env.get("type") in ("constant", "gradient"), "environment type"
    keys = ["color"] if env["type"] == "constant" else ["top", "bottom"]
    fields(env, ["type", *keys])
    for key in keys:
        vector(env[key], 0, 10)
    assert isinstance(s["lights"], list) and 1 <= len(s["lights"]) <= 3, "light budget"
    for light in s["lights"]:
        assert light.get("type") in ("rect", "sphere"), "light type"
        shape = ["size", "target"] if light["type"] == "rect" else ["radius"]
        fields(light, ["type", "position", "color", "intensity", *shape])
        vector(light["position"], -20, 20)
        vector(light["color"], 0, 1)
        number(light["intensity"], 0, 1000)
        if light["type"] == "rect":
            vector(light["size"], 0.1, 10, 2)
            vector(light["target"], -20, 20)
        else:
            number(light["radius"], 0.1, 3)


def furnace(material):
    return {"resolution": [32, 32], "materials": {"test": material},
            "spheres": [{"position": [0, 0, 0], "radius": 1, "material": "test"}],
            "camera": {"position": [0, 0, 4], "target": [0, 0, 0], "fov": 40},
            "floor": None, "lights": [],
            "environment": {"type": "constant", "color": [1, 1, 1]}}


def masks():
    # Independent perspective rays; stay well clear of mesh/silhouette edges.
    uv = (np.arange(32) + 0.5) / 32 * 2 - 1
    x, y = np.meshgrid(uv, uv)
    tangent2 = (x*x + y*y) * np.tan(np.deg2rad(20)) ** 2
    impact = 4 * np.sqrt(tangent2 / (1 + tangent2))
    return impact < 0.8, impact > 1.2


def g1(renderer, seed, wrong=False):
    sphere, background = masks()
    rows = []
    for rho in (0.18, 0.5, 0.8):
        material = {"baseColor": [rho * (0.5 if wrong else 1)] * 3,
                    "specularWeight": 0, "coatWeight": 0, "fuzzWeight": 0}
        blocks = np.stack([renderer.render(furnace(material), 8, seed + i)[..., :3]
                           for i in range(4)])
        mean = blocks[:, sphere].mean(axis=(0, 1))
        # Variance of four-block pixel means, not spatial image variance.
        variance = blocks[:, sphere].var(axis=0, ddof=1) / len(blocks)
        se = np.sqrt(variance.sum(axis=0)) / sphere.sum()
        tolerance = 4 * se + 0.015
        bg_error = float(np.max(np.abs(blocks[:, background] - 1)))
        rows.append({"rho": rho, "mean": mean.tolist(), "standard_error": se.tolist(),
                     "tolerance": tolerance.tolist(), "background_max_error": bg_error,
                     "pass": bool(np.all(np.abs(mean - rho) <= tolerance)
                                  and bg_error <= 1e-4)})
    return {"pass": all(row["pass"] for row in rows), "cases": rows,
            "sphere_pixels": int(sphere.sum()), "blocks": 4, "spp_per_block": 8}


def g2(renderer, scene, seed):
    sphere, _ = masks()
    rows = []
    for name, material in sorted(scene["materials"].items()):
        image = renderer.render(furnace(material), 16, seed)
        mean = image[sphere, :3].mean(axis=0)
        rows.append({"material": name, "mean": mean.tolist(),
                     "emissive": material.get("emissive", False),
                     "pass": bool(np.isfinite(image).all()
                                  and (material.get("emissive", False)
                                       or np.all(mean <= 1.05)))})
    return {"pass": all(row["pass"] for row in rows), "materials": rows}


def g3(renderer, scene, seed):
    levels = [1, 2, 4, 8]
    reference = renderer.render(scene, 128, seed + 100)[..., :3].astype(np.float64)
    errors = []
    for spp in levels:
        image = renderer.render(scene, spp, seed + 200)[..., :3].astype(np.float64)
        errors.append(float(np.sqrt(np.mean((image - reference) ** 2))))
    slope = float(np.polyfit(np.log(levels), np.log(np.maximum(errors, 1e-15)), 1)[0])
    return {"pass": bool(-0.65 <= slope <= -0.35), "spp": levels,
            "reference_spp": 128, "rmse": errors, "slope": slope}


def g4(renderer, scene, seed):
    a = renderer.render(scene, scene["spp"], seed)
    b = renderer.render(scene, scene["spp"], seed)
    c = renderer.render(scene, scene["spp"], seed + 1)
    hashes = [hashlib.sha256(x.tobytes()).hexdigest() for x in (a, b, c)]
    return ({"pass": hashes[0] == hashes[1] and hashes[0] != hashes[2],
             "same_seed_hashes": hashes[:2], "different_seed_hash": hashes[2]}, a, c)


def g5(scene, a, b):
    finite = int((~np.isfinite(a)).sum())
    mapped = np.clip(a[..., :3], 0, 1)
    median = float(np.median(mapped @ WEIGHTS))
    clipped = float(np.mean(np.any(mapped >= 1, axis=-1)))
    h, w = a.shape[:2]
    region = (slice(int(h * 0.85), int(h * 0.95)),
              slice(int(w * 0.35), int(w * 0.65)))
    # Prove the patch is floor, not sky or a sphere, via independent rays.
    floor_patch = patch_is_floor(scene, h, w, region)
    la = a[region][..., :3] @ WEIGHTS
    lb = b[region][..., :3] @ WEIGHTS
    mean = float((la.mean() + lb.mean()) / 2)
    noise = float(np.sqrt(np.mean((la - lb) ** 2) / 2) / max(mean, 1e-12))
    return {"pass": bool(finite == 0 and 0.08 <= median <= 0.85
                         and clipped <= 0.10 and noise <= 0.15 and floor_patch),
            "nonfinite": finite, "median_luminance": median,
            "clipped_fraction": clipped, "floor_relative_noise": noise,
            "floor_patch_verified": floor_patch, "resolution": scene["resolution"],
            "spp": scene["spp"]}


def save_outputs(path, image):
    """Keep the linear buffer and a losslessly encoded, unit-exposure preview."""
    np.save(path, image, allow_pickle=False)
    path = Path(path)
    rgb = image[..., :3]
    summary = {"shape": list(image.shape), "dtype": str(image.dtype),
               "hdr_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
               "rgb_min": float(rgb.min()), "rgb_max": float(rgb.max()),
               "rgb_mean": rgb.mean(axis=(0, 1)).tolist(),
               "nonfinite": int((~np.isfinite(image)).sum())}
    path.with_suffix(".json").write_text(json.dumps(summary, sort_keys=True) + "\n")
    pixels = np.rint(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
    height, width = pixels.shape[:2]
    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    scanlines = b"".join(b"\0" + row.tobytes() for row in pixels)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(scanlines))
           + chunk(b"IEND", b""))
    path.with_suffix(".png").write_bytes(png)


def patch_is_floor(scene, h, w, region):
    origin = np.array(scene["camera"]["position"], dtype=float)
    forward = np.array(scene["camera"]["target"], dtype=float) - origin
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, [0, 1, 0])
    if np.linalg.norm(right) < 1e-8:
        return False
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    for y in range(*region[0].indices(h)):
        for x in range(*region[1].indices(w)):
            t = np.tan(np.deg2rad(scene["camera"]["fov"] / 2))
            ray = (forward + right * (2*(x+0.5)/w-1)*t*w/h
                   + up * (1-2*(y+0.5)/h)*t)
            ray /= np.linalg.norm(ray)
            if abs(ray[1]) < 1e-8:
                return False
            distance = (scene["floor"]["y"] - origin[1]) / ray[1]
            hit = origin + distance * ray
            if distance <= 0 or max(abs(hit[0]), abs(hit[2])) > scene["floor"]["size"]:
                return False
            for ball in scene["spheres"]:
                offset = origin - ball["position"]
                b = float(offset @ ray)
                disc = b*b - float(offset @ offset) + ball["radius"]**2
                if disc >= 0 and 0 < -b - np.sqrt(disc) < distance:
                    return False
    return True


def run(args):
    start = time.monotonic()
    before = checksum()
    verdict = {"pass": False, "seed": args.seed, "requested_backend": args.backend,
               "gates": {}, "timing": {}}
    phase = "artifact"
    renderer = None
    try:
        with tempfile.TemporaryDirectory(prefix="pathtrace-grade-") as temp:
            artifact = Path(temp) / "scene.json"
            shutil.copyfile(args.artifact, artifact)
            scene = json.loads(artifact.read_text(), parse_constant=lambda x: (
                (_ for _ in ()).throw(ValueError(f"non-finite JSON: {x}"))))
            validate(scene)
            phase = "renderer"
            with Renderer(args.backend, args.api) as renderer:
                for name, function in (
                    ("G1", lambda: g1(renderer, args.seed, args.wrong_albedo)),
                    ("G2", lambda: g2(renderer, scene, args.seed)),
                    ("G3", lambda: g3(renderer, scene, args.seed)),
                ):
                    then = time.monotonic()
                    print(f"Running {name}", file=sys.stderr, flush=True)
                    verdict["gates"][name] = function()
                    verdict["timing"][name] = round(time.monotonic() - then, 3)
                then = time.monotonic()
                print("Running G4/G5", file=sys.stderr, flush=True)
                verdict["gates"]["G4"], a, b = g4(renderer, scene, args.seed)
                verdict["timing"]["G4"] = round(time.monotonic() - then, 3)
                verdict["gates"]["G5"] = g5(scene, a, b)
                if args.hdr_out:
                    save_outputs(args.hdr_out, a)
                verdict.update(renderer.info)
                verdict["chromium"] = renderer.version
    except Exception as exc:
        verdict["error"] = f"{type(exc).__name__}: {exc}"
        verdict["error_kind"] = phase
        if renderer is not None:
            verdict.update(getattr(renderer, "info", {}))
            verdict["chromium"] = renderer.version
    finally:
        verdict["judge_unchanged"] = before == checksum()
    elapsed = round(time.monotonic() - start, 3)
    verdict["timing"]["total_seconds"] = elapsed
    # Timing is deliberately isolated; outside timing, results are deterministic.
    verdict["pass"] = (len(verdict["gates"]) == 5 and "error" not in verdict
                       and all(g["pass"] for g in verdict["gates"].values())
                       and verdict["judge_unchanged"] and elapsed < 600)
    return verdict


def main():
    p = argparse.ArgumentParser()
    p.add_argument("artifact", type=Path)
    p.add_argument("--seed", type=int, default=17)
    p.add_argument("--json", type=Path)
    p.add_argument("--backend", choices=("cpu", "gpu"), default="cpu")
    p.add_argument("--api", choices=("webgpu", "webgl"), default="webgpu")
    p.add_argument("--hdr-out", type=Path, help="optional RGBA float32 .npy output")
    p.add_argument("--wrong-albedo", action="store_true", help=argparse.SUPPRESS)
    p.add_argument("--trusted-copy", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if not 0 <= args.seed < 32000:
        p.error("seed must be in [0, 32000)")
    def deadline(signum, frame):
        raise TimeoutError("grade exceeded 590-second compute budget")

    signal.signal(signal.SIGALRM, deadline)
    if args.trusted_copy:
        signal.alarm(590)
        verdict = run(args)
    else:
        # Run only a private copy of the fixed judge, not files beside the input.
        before = checksum()
        with tempfile.TemporaryDirectory(prefix="pathtrace-judge-") as temp:
            target = Path(temp) / "judge"
            shutil.copytree(HERE, target, ignore=shutil.ignore_patterns("__pycache__"))
            command = [sys.executable, str(target / "grade.py"),
                       str(args.artifact.resolve()), "--seed", str(args.seed),
                       "--backend", args.backend, "--api", args.api, "--trusted-copy"]
            if args.wrong_albedo:
                command.append("--wrong-albedo")
            if args.hdr_out:
                command += ["--hdr-out", str(args.hdr_out.resolve())]
            started = time.monotonic()
            proc = subprocess.Popen(command, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, start_new_session=True)
            expired = False
            try:
                stdout, stderr = proc.communicate(timeout=595)
            except subprocess.TimeoutExpired:
                expired = True
                kill_owned_tree(proc.pid)
                stdout, stderr = proc.communicate(timeout=2)
            if stderr:
                print(stderr, file=sys.stderr, end="")
            try:
                verdict = json.loads(stdout) if not expired else {}
            except ValueError:
                verdict = {"pass": False, "error": "judge subprocess returned no JSON",
                           "gates": {}, "timing": {}}
            if expired:
                verdict = {"pass": False, "error": "judge exceeded 595-second process budget",
                           "error_kind": "renderer", "requested_backend": args.backend,
                           "seed": args.seed, "gates": {},
                           "timing": {"total_seconds": round(time.monotonic()-started, 3)}}
            verdict["judge_unchanged"] = (verdict.get("judge_unchanged", False)
                                           and before == checksum())
            verdict["pass"] = bool(verdict["pass"] and verdict["judge_unchanged"]
                                   and proc.returncode == 0)
    signal.alarm(0)
    output = json.dumps(verdict, sort_keys=True, allow_nan=False)
    if args.json:
        args.json.write_text(output + "\n")
    print(output)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
