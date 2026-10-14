# Known-bad artifacts

These are **generated** by `judge/mutants.py generate` into this directory.
Each is a single-edit mutation of `examples/good/antenna.py`:

| file | mutation | why it must fail |
|---|---|---|
| `bad_substrate_er.py` | `er = 3.2` (out of FR-4 range 3.5–5.0) | G2 physical sanity |
| `bad_patch_length.py` | `patch_L = 24.0` (resonance moved to 3+ GHz) | G5 resonance |
| `bad_no_ground.py` | geometry drops the ground plane (commented out) | G4 S11 at target (no return current → very poor match) |
| `bad_feed_center.py` | `feed_inset = 15.0, line_L = 0.0` — fed mid-patch at a voltage node | G4 S11 at target |
| `bad_coarse_mesh.py` | `resolution = 4` (spec: ≥ 6) | G2 or G7 (unlikely stable) |
| `bad_nan_er.py` | `er = float('nan')` | G1/G2 (fails parse-able numeric range) — sim must error |
