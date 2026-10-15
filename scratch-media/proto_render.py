#!/usr/bin/env python3
"""Prototype: render the judged toolpath as extruded beads (tubes)."""
import json, time, numpy as np, pyvista as pv

t0 = time.time()
tr = json.load(open('/tmp/media-work/trace/good.trace.json'))
extr = np.array(tr['extr'])  # z, x0, y0, x1, y1, dE, feed
print('load %.2fs, %d moves' % (time.time()-t0, len(extr)))

R = 0.21      # line_width 0.42 / 2
SIDES = 6

def tube_mesh(segs, r, sides=6, rads=None):
    """segs: (N,5) z,x0,y0,x1,y1. rads: optional per-seg radius."""
    t0 = time.time()
    n = len(segs)
    p0 = np.stack([segs[:,1], segs[:,2], segs[:,0]], axis=1)
    p1 = np.stack([segs[:,3], segs[:,4], segs[:,0]], axis=1)
    d = p1 - p0
    L = np.linalg.norm(d, axis=1)
    keep = L > 1e-3
    p0, p1, d, L = p0[keep], p1[keep], d[keep], L[keep]
    n = len(p0)
    rad = np.full(n, r) if rads is None else rads[keep]
    # orthonormal frame
    a = d / L[:, None]
    ref = np.where(np.abs(a[:, 2:3]) < 0.9,
                   np.tile([0., 0., 1.], (n, 1)), np.tile([1., 0., 0.], (n, 1)))
    u = np.cross(a, ref); u /= np.linalg.norm(u, axis=1)[:, None]
    v = np.cross(a, u)
    th = np.linspace(0, 2*np.pi, sides, endpoint=False)
    ring = (np.cos(th)[None, None, :] * u[:, :, None]
            + np.sin(th)[None, None, :] * v[:, :, None])   # (n,3,sides)
    rad = rad[:, None, None]
    A = p0[:, :, None] + ring * rad      # start ring (n,3,sides)
    B = p1[:, :, None] + ring * rad      # end ring
    nv = 2 * sides
    pts = np.concatenate([A, B], axis=2).transpose(0, 2, 1).reshape(-1, 3)
    idx = np.arange(n * nv).reshape(n, nv)
    i0, i1 = idx[:, :sides], idx[:, sides:]
    faces = []
    for k in range(sides):
        k2 = (k + 1) % sides
        f = np.stack([
            np.stack([i0[:, k], i0[:, k2], i1[:, k]], axis=1),
            np.stack([i1[:, k], i1[:, k2], i0[:, k2]], axis=1),
        ], axis=1).reshape(-1, 3)
        faces.append(f)
    faces = np.concatenate(faces)
    pd = pv.PolyData(pts, np.column_stack(
        [np.full(len(faces), 3), faces]).ravel())
    lay = np.repeat(np.asarray(segs[keep][:, 0]), nv)
    pd['layer_z'] = lay
    print('mesh %.2fs: %d verts %d tris' % (time.time()-t0, pd.n_points, len(faces)))
    return pd

pd = tube_mesh(extr, R)
t0 = time.time()
pl = pv.Plotter(off_screen=True, window_size=(1560, 1040))
pl.add_mesh(pd, scalars='layer_z', cmap='viridis', smooth_shading=True,
            specular=0.3, diffuse=0.85, ambient=0.25)
# travel moves thin grey
tv = np.array(tr['travel'])
tp = np.empty((2*len(tv), 3)); tp[0::2] = np.stack([tv[:,1], tv[:,2], tv[:,0]], 1)
tp[1::2] = np.stack([tv[:,3], tv[:,4], tv[:,0]], 1)
ii = np.arange(len(tv))
lines = np.column_stack([np.full(len(tv), 2), 2 * ii, 2 * ii + 1]).ravel()
pl.add_mesh(pv.PolyData(tp, lines), color='#8c8c8c', line_width=1.0)
# bed
bed = pv.Plane(center=(125, 105, -0.05), i_size=250, j_size=210,
               direction=(0, 0, 1))
pl.add_mesh(bed, color='#e8e8e8', pbr=False, ambient=0.9, opacity=0.35)
pl.camera_position = 'iso'
pl.camera.zoom(1.8)
img = pl.screenshot('/home/user/w/scratch-media/proto1.png')
print('render %.2fs' % (time.time()-t0))
