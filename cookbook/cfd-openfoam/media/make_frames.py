#!/usr/bin/env python3
"""Advect tracers through the exact OpenFOAM velocity fields saved by grade.sh.

Produces a 30 fps physical flow playback. Particle positions are integrated
from solver output, never drawn from an illustrative vortex equation.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image, ImageDraw


def read_field(path):
    started = False
    values = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith('internalField'):
            started = True
        elif started and line.startswith('(') and line != '(':
            parts = line.strip('()').split()
            if len(parts) == 3:
                values.append([float(v) for v in parts[:2]])
        elif started and line == ');':
            break
    return np.asarray(values)


def main():
    trace, output = map(pathlib.Path, sys.argv[1:3])
    output.mkdir(parents=True, exist_ok=True)
    centres = np.loadtxt(trace / 'cellcentres.csv', delimiter=',', skiprows=1)
    xs, ys = np.unique(centres[:, 0]), np.unique(centres[:, 1])
    order = np.lexsort((centres[:, 0], centres[:, 1]))
    times = sorted([p for p in trace.iterdir() if p.is_dir() and p.name.replace('.', '', 1).isdigit()], key=lambda p: float(p.name))
    fields = np.asarray([read_field(p / 'U')[order].reshape(len(ys), len(xs), 2) for p in times])
    snapshots = np.asarray([float(p.name) for p in times])
    verdict = json.loads((trace.parent / 'verdicts/04_cavity_good.json').read_text())
    lid_speed = next(g['details']['lid_velocity'] for g in verdict['gates'] if g['gate'] == 5)
    rng = np.random.default_rng(42)
    particles = rng.uniform(.025, .975, (1100, 2))
    trails = [particles.copy() for _ in range(9)]
    width, height = 1920, 1080
    for frame in range(-9, 26 * 30):
        # One physical second per playback second; seed 42 fixes tracer release.
        if frame == 60:
            rng = np.random.default_rng(42)
            particles = rng.uniform(.025, .975, (1100, 2))
            trails = [particles.copy() for _ in range(9)]
        physical_time = (snapshots[-1] - 2 + frame / 30 if frame < 60
                         else snapshots[0] + (frame - 60) / 30)
        upper = min(np.searchsorted(snapshots, physical_time), len(snapshots)-1)
        lower = max(upper-1, 0)
        fraction = (physical_time-snapshots[lower]) / max(snapshots[upper]-snapshots[lower], 1e-9)
        velocity = fields[lower] * (1-fraction) + fields[upper] * fraction
        def sample(points):
            px = np.clip((points[:, 0]-xs[0])/(xs[1]-xs[0]), 0, len(xs)-1.001)
            py = np.clip((points[:, 1]-ys[0])/(ys[1]-ys[0]), 0, len(ys)-1.001)
            ix, iy = px.astype(int), py.astype(int)
            fx, fy = (px-ix)[:, None], (py-iy)[:, None]
            return ((1-fx)*(1-fy)*velocity[iy, ix] + fx*(1-fy)*velocity[iy, ix+1] + (1-fx)*fy*velocity[iy+1, ix] + fx*fy*velocity[iy+1, ix+1])
        # Midpoint integration, with two substeps per video frame.
        for _ in range(0 if frame in (0, 60) else 2):
            dt = 1/60
            particles += dt * sample(particles + dt/2 * sample(particles))
        outside = np.any((particles < .013) | (particles > .987), axis=1)
        particles[outside] = rng.uniform(.025, .975, (outside.sum(), 2))
        for old in trails:
            old[outside] = particles[outside]
        trails = trails[1:] + [particles.copy()]
        if frame < 0:
            continue
        # Fixed physical views: the full cavity, the driven lid, the return flow.
        shot = 0 if frame < 240 else 1 if frame < 480 else 2 if frame < 600 else 3
        bounds = [(0, 0, 1), (.12, .40, 1), (.05, .02, .79), (0, 0, 1)][shot]
        x0, y0, y1 = bounds
        palettes = [(22, 211, 220), (10, 94, 134), (117, 208, 145), (20, 114, 140)]
        colour = palettes[shot]
        image = Image.new('RGB', (width, height), (236, 245, 245) if shot in (1, 3) else (16, 32, 46))
        draw = ImageDraw.Draw(image)
        scale = 1080 / (y1-y0)
        def project(p):
            return ((p[0]-x0)*scale+700, 1080-(p[1]-y0)*scale)
        draw.rectangle((700+(0-x0)*scale, 1080-(1-y0)*scale, 700+(1-x0)*scale, 1080-(0-y0)*scale), outline=(83, 113, 134), width=5)
        # Moving top-wall markers show the imposed boundary velocity.
        for marker in range(9):
            mx = (marker/9 + physical_time*lid_speed) % 1
            ax, ay = project((mx, .992))
            draw.line((ax-20, ay, ax+20, ay), fill=(240, 115, 52), width=7)
            draw.polygon([(ax+20, ay), (ax+8, ay-9), (ax+8, ay+9)], fill=(240, 115, 52))
        speeds = np.linalg.norm(sample(particles), axis=1)
        for i in range(len(particles)):
            coords = [project(p[i]) for p in trails]
            speed = float(speeds[i])
            brightness = .45 + .55 * min(speed/.35, 1)
            rgb = tuple(int(v*brightness) for v in colour)
            draw.line(coords, fill=rgb, width=4)
            x, y = coords[-1]
            draw.ellipse((x-3, y-3, x+3, y+3), fill=(14, 69, 89) if shot in (1, 3) else (220, 248, 255))
        image.save(output / f'frame_{frame:04d}.png', compress_level=1)
    (output / 'playback.json').write_text(json.dumps({'seed':42,'fps':30,'frames':780,'time_scale':1,'hook_solver_times':[float(snapshots[-1]-2),float(snapshots[-1])],'rewind_at_video_s':2,'first_solver_time':float(snapshots[0]),'last_solver_time':float(snapshots[-1]),'tracers':1100,'source':'grade.sh --trace cavity_traces; cellcentres.csv and */U','integration':'midpoint, dt=1/60 s; bilinear spatial and linear temporal interpolation'}))
    print('wrote 780 physical playback frames')


if __name__ == '__main__':
    main()
