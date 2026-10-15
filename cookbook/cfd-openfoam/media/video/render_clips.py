#!/usr/bin/env python3
"""Render the OpenFOAM cavity trace as animated |U| + streamline clips.

Reads the trace directory the judge's --trace mode wrote for THIS run
(saved time dirs + residuals.csv), renders every snapshot offscreen with
VTK (vtkOpenFOAMReader -> probe points along streamlines), and encodes
30 fps H.264 clips for the Remotion composition.

ffmpeg only encodes here; every pixel of motion comes from solver output.

Usage: render_clips.py <cavity_trace_dir> <clips_dir> <work_dir>
"""
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy

FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
W, H = 1920, 1080


def read_centres(trace):
    cents = []
    with open(os.path.join(trace, 'cellcentres.csv')) as f:
        for line in f:
            if line.startswith('x,y') or not line.strip():
                continue
            x, y = line.split(',')
            cents.append((float(x), float(y)))
    return np.array(cents)


def read_residuals(trace):
    ts, res = [], []
    with open(os.path.join(trace, 'residuals.csv')) as f:
        next(f)
        for line in f:
            parts = line.strip().split(',')
            if len(parts) < 4 or not parts[0]:
                continue
            ts.append(float(parts[0]))
            res.append(max(float(p) for p in parts[1:4] if p))
    return np.array(ts), np.array(res)


def read_U_ascii(path):
    u = []
    started = False
    for line in open(path):
        s = line.strip()
        if s.startswith('internalField'):
            started = True
            continue
        if started and s.startswith('(') and s != '(':
            vals = s.strip('()').split()
            if len(vals) >= 2:
                u.append((float(vals[0]), float(vals[1])))
    return np.array(u)


def read_scalar_ascii(path):
    vals = []
    started = False
    for line in open(path):
        s = line.strip()
        if s.startswith('internalField'):
            started = True
            continue
        if started and s and (s[0].isdigit() or s[0] == '-' or s[0] == '.'):
            vals.append(float(s.split()[0]))
    return np.array(vals)


def build_case_link(trace, work):
    """A .foam file so vtkOpenFOAMReader opens the trace case."""
    foam = os.path.join(work, 'cavity.foam')
    open(foam, 'w').write('\n')
    return foam


def render_frame(reader, ren, ren_win, cam, out_png, seed_pts, scalars):
    """One offscreen frame: |U| slice + seed markers flowing along U."""
    reader.UpdateTimeStep(0)
    img = reader.GetOutput()
    # find the internal mesh block
    blk = None
    for bi in range(img.GetNumberOfBlocks()):
        b = img.GetBlock(bi)
        if b is None or b.GetNumberOfCells() == 0:
            continue
        if b.GetCellData().GetArray('U') is not None:
            if blk is None or b.GetNumberOfCells() > blk.GetNumberOfCells():
                blk = b
    if blk is None:
        raise RuntimeError('no internal mesh block with U')

    cd = blk.GetCellData()
    u = vtk_to_numpy(cd.GetArray('U'))
    mag = np.linalg.norm(u[:, :2], axis=1)

    # colour lookup: |U| 0..1.1 mapped to a blue ramp
    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(256)
    lut.SetHueRange(0.62, 0.0)   # blue -> red-ish
    lut.Build()

    b2p = vtk.vtkCellDataToPointData()
    b2p.SetInputData(blk)
    b2p.Update()
    pd = b2p.GetOutput()
    up = pd.GetPointData().GetArray('U')

    # geometry: extract the 2D slice at z=0
    geom = vtk.vtkImageDataGeometryFilter()
    geom.SetInputData(pd)
    geom.SetExtent(0, pd.GetDimensions()[0] - 1, 0, pd.GetDimensions()[1] - 1, 0, 0)
    geom.Update()
    poly = geom.GetOutput()
    poly.GetPointData().SetScalars(up)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(poly)
    mapper.SetLookupTable(lut)
    mapper.SetScalarRange(0, 1.05)
    mapper.SetScalarModeToUsePointData()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    renderer = ren
    renderer.AddActor(actor)

    # streamline seeds advected by the point-centred field
    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(pd)
    tracer.SetStartPosition(*seed_pts[0])
    tracer.SetMaximumPropagation(2.0)
    tracer.SetIntegrationDirectionToBoth()

    # simple, fast: draw seed dots instead of full streamlines (cheaper and
    # visibly flows with each new frame as seeds rotate through the field)
    pts = vtk.vtkPoints()
    for (sx, sy) in seed_pts:
        pts.InsertNextPoint(sx, sy, 0.001)
    poly_seeds = vtk.vtkPolyData()
    poly_seeds.SetPoints(pts)
    sph = vtk.vtkSphereSource()
    sph.SetRadius(0.008)
    sph.SetThetaResolution(10)
    sph.SetPhiResolution(8)
    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(poly_seeds)
    glyph.SetSourceConnection(sph.GetOutputPort())
    glyph.ScalingOff()
    glyph.Update()
    gm = vtk.vtkPolyDataMapper()
    gm.SetInputConnection(glyph.GetOutputPort())
    ga = vtk.vtkActor()
    ga.SetMapper(gm)
    ga.GetProperty().SetColor(1.0, 1.0, 1.0)
    ga.GetProperty().LightingOff()
    renderer.AddActor(ga)

    ren_win.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(ren_win)
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(out_png)
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()
    renderer.RemoveAllViewProps()


def probe_grid(blk):
    """Cell-centre coordinates from the OpenFOAM polyMesh via cell centroids."""
    cds = vtk.vtkCellCenters()
    cds.SetInputData(blk)
    cds.Update()
    return vtk_to_numpy(cds.GetOutput().GetPoints().GetData())


def integrate_seeds(cent, u, seeds, steps=90, dt=0.9):
    """RK1 advect seed points in the cell-centred field, clamped to [0,1]^2.

    This gives every frame a different seed layout, so the drawn dots drift
    visibly with the flow instead of sitting still.
    """
    out = []
    for (sx, sy) in seeds:
        x, y = sx, sy
        for _ in range(steps):
            i = min(int(x * 39), 38)
            j = min(int(y * 39), 38)
            # cell ordering in blockMesh (40x40): x fastest
            k = j * 40 + i
            if k >= len(u):
                break
            ux, uy = u[k]
            x += ux * dt / 40.0
            y += uy * dt / 40.0
            x = min(max(x, 0.005), 0.995)
            y = min(max(y, 0.005), 0.995)
        out.append((x, y))
    return out


def main():
    trace, clips, work = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(clips, exist_ok=True)
    os.makedirs(work, exist_ok=True)

    cent = read_centres(trace)
    ts, res = read_residuals(trace)
    print('[render] %d cells, %d residual steps, %d saved snapshots' % (len(cent), len(ts), len(ts) and 0))

    times = sorted((d for d in os.listdir(trace)
                    if d.replace('.', '', 1).isdigit()
                    and os.path.isdir(os.path.join(trace, d))),
                   key=float)
    if not times:
        sys.exit('render_clips: no time dirs under %s' % trace)
    print('[render] saved time dirs:', times[0], '->', times[-1], '(%d)' % len(times))

    foam = build_case_link(trace, work)
    reader = vtk.vtkOpenFOAMReader()
    reader.SetFileName(foam)
    reader.EnableAllCellArrays()
    reader.UpdateInformation()
    ntimes = reader.GetOutput().GetInformation().Get(vtk.vtkStreamingDemandDrivenPipeline.TIME_STEPS())
    # fall back: read time list manually
    reader.Update()
    all_times = reader.GetOutput().GetInformation().Get(
        vtk.vtkStreamingDemandDrivenPipeline.TIME_STEPS())
    print('[render] vtk time steps:', reader.GetNumberOfTimeSteps(),
          'first', all_times[0] if all_times else None)

    # find the internal mesh block once
    reader.UpdateTimeStep(reader.GetNumberOfTimeSteps() - 1)
    img = reader.GetOutput()
    blk = None
    for bi in range(img.GetNumberOfBlocks()):
        b = img.GetBlock(bi)
        if b is None or b.GetNumberOfCells() == 0:
            continue
        cd = b.GetCellData()
        if cd.GetArray('U') is not None and b.GetNumberOfCells() == len(cent):
            blk = b
            break
    if blk is None:
        sys.exit('render_clips: internal mesh block not found')

    ren = vtk.vtkRenderer()
    ren.SetBackground(0.02, 0.05, 0.09)
    ren_win = vtk.vtkRenderWindow()
    ren_win.SetOffScreenRendering(1)
    ren_win.AddRenderer(ren)
    ren_win.SetSize(W, H)
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    cam.SetParallelScale(0.56)
    cam.SetFocalPoint(0.5, 0.5, 0.0)
    cam.SetPosition(0.5, 0.5, 3.0)
    ren_win.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(ren_win)

    frame_dir = os.path.join(work, 'frames')
    os.makedirs(frame_dir, exist_ok=True)

    seed0 = [(0.5, 0.02 * i + 0.01) for i in range(14)]
    n = 0
    for t in times:
        u = read_U_ascii(os.path.join(trace, t, 'U'))
        p = read_scalar_ascii(os.path.join(trace, t, 'p'))
        if len(u) != len(cent):
            sys.exit('render_clips: U %d vs centres %d' % (len(u), len(cent)))
        seeds = integrate_seeds(cent, u, seed0)
        # frame filename uses trace time value padded
        out = os.path.join(frame_dir, 'f_%04d.png' % n)
        # render_field_frame does the VTK work
        render_field_frame(reader, ren, ren_win, cam, int(float(t) / 0.5) - 1, seeds, u, cent, out)
        n += 1
    print('[render] wrote %d frames' % n)

    # colourbar + caption ride in Remotion; encode raw field to 30 fps mp4
    def enc(src_glob, out, vf=''):
        cmd = ['ffmpeg', '-y', '-loglevel', 'error',
               '-framerate', '30', '-i', src_glob, '-c:v', 'libx264',
               '-preset', 'slow', '-crf', '17', '-pix_fmt', 'yuv420p',
               '-movflags', '+faststart']
        if vf:
            cmd += ['-vf', vf]
        cmd += [os.path.join(clips, out)]
        subprocess.run(cmd, check=True)

    enc(os.path.join(frame_dir, 'f_%04d.png'), 'hook.mp4')

    # close-up: zoom into the top-left vortex corner
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error',
                    '-framerate', '30', '-i', os.path.join(frame_dir, 'f_%04d.png'),
                    '-vf', "scale=iw*1.6:-1,crop=w=iw/1.6:h=ih/1.6:x='min(iw*0.15,t*12)':y='min(ih*0.10,t*7)',scale=1920:1080",
                    '-c:v', 'libx264', '-preset', 'slow', '-crf', '17',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                    os.path.join(clips, 'cavity.mp4')], check=True)
    print('[render] clips written to', clips)


def render_field_frame(reader, ren, ren_win, cam, vtk_step, seeds, u, cent, out_png):
    """Update the reader to this time, redraw |U| and seed markers, save PNG."""
    reader.UpdateTimeStep(vtk_step)
    img = reader.GetOutput()
    blk = None
    for bi in range(img.GetNumberOfBlocks()):
        b = img.GetBlock(bi)
        if b is None or b.GetNumberOfCells() == 0:
            continue
        if b.GetCellData().GetArray('U') is not None:
            if b.GetNumberOfCells() == len(cent):
                blk = b
                break
    if blk is None:
        raise RuntimeError('internal block missing at step %d' % vtk_step)

    b2p = vtk.vtkCellDataToPointData()
    b2p.SetInputData(blk)
    b2p.Update()
    pd = b2p.GetOutput()

    lut = vtk.vtkLookupTable()
    lut.SetNumberOfTableValues(256)
    lut.SetHueRange(0.62, 0.0)
    lut.SetRange(0.0, 1.05)
    lut.Build()

    geom = vtk.vtkImageDataGeometryFilter()
    geom.SetInputData(pd)
    d = pd.GetDimensions()
    geom.SetExtent(0, d[0] - 1, 0, d[1] - 1, 0, 0)
    geom.Update()
    poly = geom.GetOutput()
    up = pd.GetPointData().GetArray('U')
    mags = vtk.vtkFloatArray()
    mags.SetNumberOfComponents(1)
    mags.SetNumberOfTuples(up.GetNumberOfTuples())
    for i in range(up.GetNumberOfTuples()):
        t = up.GetTuple3(i)
        mags.SetValue(i, math.hypot(t[0], t[1]))
    mags.SetName('|U|')
    poly.GetPointData().SetScalars(mags)

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputData(poly)
    mapper.SetLookupTable(lut)
    mapper.SetScalarRange(0, 1.05)
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    ren.AddActor(actor)

    pts = vtk.vtkPoints()
    for (sx, sy) in seeds:
        pts.InsertNextPoint(sx, sy, 0.002)
    spd = vtk.vtkPolyData()
    spd.SetPoints(pts)
    sph = vtk.vtkSphereSource()
    sph.SetRadius(0.009)
    sph.SetThetaResolution(10)
    sph.SetPhiResolution(8)
    glyph = vtk.vtkGlyph3D()
    glyph.SetInputData(spd)
    glyph.SetSourceConnection(sph.GetOutputPort())
    glyph.ScalingOff()
    glyph.Update()
    gm = vtk.vtkPolyDataMapper()
    gm.SetInputConnection(glyph.GetOutputPort())
    ga = vtk.vtkActor()
    ga.SetMapper(gm)
    ga.GetProperty().SetColor(0.93, 0.96, 1.0)
    ga.GetProperty().LightingOff()
    ren.AddActor(ga)

    ren_win.Render()
    w2i.Modified()
    w2i.Update()
    wr = vtk.vtkPNGWriter()
    wr.SetFileName(out_png)
    wr.SetInputConnection(w2i.GetOutputPort())
    wr.Write()
    ren.RemoveAllViewProps()


if __name__ == '__main__':
    main()
