# sim-tuner / planned cut

Every shot uses `data/trajectories.npz`, captured inside CPU grading by
`collect.py`. Same initial conditions, 2 ms timestep, no interpolated poses.
Default / tuned / hidden truth stay in that order. Caption numbers come from
the fresh `run.py --seed 7` receipt, `data/run-1.json`.

| slot | picture | caption / evidence |
|---|---|---|
| 0–4 s, hook | Three box close-ups, synchronized real 3D states and a translucent truth ghost | Fit 5 physics values. Match unseen motion. / target gaps in cm / PASS and limit |
| 4–9 s, input → output | Same box case, alternate lighting | Same caption and score; target gap changes with the actual timestep |
| 9–14 s, escalate | Close view of the two-link servo arm responding | Actuation: watch the arm settle. / unseen test 1 |
| 14–18 s, stress | A second held-out command, overhead camera | Unseen command, same tuned parameters / held-out command 2 |
| 18–22 s, proof | Three rigs still replaying, judge HUD | PASS 0.02206 < 0.025 held-out error / Judge rejected all 18 broken fits. CPU / GPU agree. |
| 22–25 s, end | Frozen real 3D frame, launch command | `python3 cookbook/sim-tuner/run.py` |

Every moving shot repeats a real one-second recording at real time, explicitly
labelled `1x replay loop`. Camera orbit and alternating lighting are rendering
choices, not different physics. No search screen recording was fabricated.
The box-gap readout is an instantaneous horizontal distance in cm; the judge's
error is normalized RMS over all seven signals and is **not** a distance in cm.

The prerecorded search is a CPU search, not an invented GPU agent trace.
Its measured per-iteration train errors and mutant table appear in `loop.png`;
the video spends its time on the physical consequence of tuning instead.
