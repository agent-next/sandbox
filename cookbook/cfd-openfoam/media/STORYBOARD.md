# Cavity tracer playback

All shots play the velocity fields produced by the exact cavity case graded
in `make_media.sh`, seed 42. Tracers use midpoint advection at 1/60 s and
bilinear spatial / linear temporal interpolation of the saved OpenFOAM fields.
They are passive visualization probes, not additional CFD measurements.
The physical playback is 1× speed. Crops are fixed views of moving flow.

| Time | Real moving output | HUD / source |
| --- | --- | --- |
| 0–2 s | Finished cavity flow, solver t=28–30 s; tracers have physical trails from t=27.7 s onward | Finished flow, Re=100, actual solver time, 1× physical time |
| 2–8 s | Rewind to t=0.5 s; full cavity developing, 1,100 tracers | Building the cavity, actual solver time; `cavity_traces/*/U`, `cellcentres.csv` |
| 8–16 s | Close view of the driven lid and shear layer | Same evolving solver field and time; no still-image zoom |
| 16–20 s | Fixed close view of the returning flow | Recirculation and physical time |
| 20–26 s | Full cavity playback continues under the verdict | Final-case (solver t=30 s) u/v errors from gate 5; killed mutants counted from all ten grade JSONs |
| 26–28 s | Static end card | `python3 cookbook/cfd-openfoam/run.py` |

`make_frames.py` creates the physical playback clip; `composition.jsx` uses
Remotion to compose it with the measured HUD. `make_media.sh` writes both a
lossless master and the H.264 web encode, then records artifact hashes.
