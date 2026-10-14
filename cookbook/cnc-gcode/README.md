# cnc-gcode: 2.5D pocket milling with G-code, judged by material-removal simulation

An agent writes its **own CAM script** (`cam.py`, stdlib + numpy) that turns a
job spec into real G-code (`part.nc`: `G17 G21 G90`, `G0/G1/G2/G3`, `F`, `S`,
`M3/M5`) for a rectangular pocket with a round island in an aluminium block —
then a judge it cannot fool simulates the G-code as **material removal on a
0.05 mm heightmap grid** (a flat end mill swept along every line and arc) and
checks the part numerically against the analytic geometry: the pocket must be
cleared to depth everywhere the tool can reach, the island, walls and floor
must not be gouged by more than 0.01 mm, no rapid move may plough into stock,
every pass must respect the 2 mm stepdown / 3 mm stepover limits, and the chip
load `F/(rpm × flutes)` must stay in band. The simulator cross-checks itself
on every run: a straight slot and a full circle it cuts analytically must
measure exactly one tool diameter wide, within one grid cell.

Why a sandbox: the agent designs and fixes its own artifact — a CAM program
and the G-code it emits — inside a disposable machine, iterating against a
judge that is independent of anything the agent writes. Nothing touches a
real machine tool, and the judge's sources are checksummed before and after
every grade, so the artifact cannot tamper with its own grader.

## Results

| | |
|---|---|
| **Verdict** | ✅ **PASS** — all 10 gates, 7/7 mutants killed (100 % kill rate) |
| **Stock cleared** | 1783.98 mm² of pocket floor (target geometry: 1814.37 mm² minus the 25.71 mm² round-island fillet band no Ø6 tool can reach) |
| **Residual stock** | 0 cells above the +0.05 mm tolerance |
| **Gouge** | 0 cells deeper than the −0.01 mm tolerance (walls, island, floor) |
| **Worst axial engagement** | 2.000 mm (limit 2.000 mm) |
| **Worst pass spacing** | 2.500 mm (limit 3.000 mm) |
| **Chip load** | 0.025–0.100 mm/tooth (limits 0.02–0.20) |
| **Slot self-check** | straight slot 6.000 mm wide, circular slot 5.957–5.982 mm (tool Ø 6.000 ± one 0.05 mm cell) |
| **Determinism** | verified — same seed → byte-identical verdict JSON |

Numbers are from `bash judge/grade.sh examples/good/cam.py --json /tmp/v.json`
(default seed 20261014) on 2 vCPU / 4 GB; see RECEIPT.md for the raw output
and two fresh-environment runs.

## What the artifact must do

See [SPEC.md](SPEC.md) for the full rules. In short: `cam.py` reads
`spec.json` (80 × 60 × 25 mm stock, 56 × 36 × 6 mm pocket with 6 mm corner
radius, Ø16 mm island, Ø6 mm 2-flute flat end mill) and writes `part.nc`
that machines it — tool-radius offset applied by the script itself, rapids
only over already-cut air, plunges at feed, arcs in I/J form. The judge
refuses anything outside the supported dialect by name (G20 inch mode,
G91 incremental, canned cycles, R-form arcs, ...).

## One-command run

```bash
export SBX_API_KEY=<your key>     # https://sbx.agent-next.com/console
python3 cookbook/cnc-gcode/run.py    # needs the sbx CLI (pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli")
```

`run.py` creates a disposable sandbox, clones this repo at `--ref main`
(default; `--ref` to override), runs `judge/setup.sh` → `judge/selftest.sh` →
`judge/grade.sh examples/good/cam.py`, prints the verdict JSON, and always
kills the sandbox (`--keep` leaves it up). Non-zero exit on any failure.

Without a key, run the same steps in any Debian 12 box with Python 3.12,
from `cookbook/cnc-gcode/`:

```bash
bash judge/setup.sh                                        # pinned numpy 2.5.3 venv (~35 s fresh)
bash judge/selftest.sh                                     # good example + 7 mutants + determinism (~65 s)
bash judge/grade.sh examples/good/cam.py --json verdict.json   # ~6 s, default seed 20261014
```

Measured wall times (2 vCPU, ~4 GB, Debian bookworm):

| step | wall |
| --- | --- |
| `judge/setup.sh` (fresh venv + pinned numpy) | ~35 s |
| `judge/selftest.sh` (good + 7 mutants + determinism) | ~65 s |
| `judge/grade.sh examples/good/cam.py` | ~6 s |
| fresh `git clone --depth 1` of this repo | ~5 s |

## Ask your agent

Paste this into a session with the sandbox plugin enabled:

> In a sandbox, build the 2.5D CAM demo for `cookbook/cnc-gcode` from
> scratch. Clone this repo, read `cookbook/cnc-gcode/SPEC.md` and
> `spec.json`, then write your own `cam.py` (Python stdlib + numpy only) that
> emits `part.nc`: G17 G21 G90, G0/G1/G2/G3, F, S, M3/M5, millimetres,
> absolute, I/J arcs. The job: 56 × 36 × 6 mm pocket with 6 mm corner radius
> and a Ø16 mm round island in 80 × 60 × 25 mm aluminium, cut with a Ø6 mm
> 2-flute flat end mill — apply the tool-radius offset yourself. Iterate with
> `bash judge/grade.sh /path/to/your/cam.py --json /tmp/v.json` until every
> gate passes, and make sure you are not caught by any of the seven
> single-edit mutants in `judge/mutate.py`. Show me the final verdict JSON
> and the key numbers (worst residual, worst gouge, stepdown, stepover, chip
> load). Do not modify anything under `judge/`.

The agent works on the artifact inside the disposable sandbox; the judge
lives in the repo, always grades a scratch copy against the repo's own
`spec.json`, and is never modified by what the agent runs.

## Limits (stated plainly)

- The simulation is a heightmap of material removal for one flat end mill:
  no cutting forces, tool deflection, chatter, chip evacuation, spindle
  power or acceleration limits; process limits are checked geometrically
  (stepdown, stepover, chip load) rather than from physics.
- The judge interprets a deliberate subset of RS274/NGC (G0/G1/G2/G3 in the
  XY plane with I/J, G17/G21/G90, M3/M5). Programs using anything else are
  rejected by name instead of misinterpreted — no canned cycles, no G41/G42,
  no work offsets, no inch mode.
- Geometry gates are exact to one grid cell (0.05 mm): boundary cells within
  one cell of a wall or the island are excluded from the gouge check to keep
  grid quantisation from producing false alarms; for this spec the
  unreachable-corner allowance in the residual check is empty (corner radius
  6 mm ≥ tool radius 3 mm), so the clearance check is exact.
- No reference CAM verifier is run: CAMotics needs Qt/X11 and a long source
  build that does not install cleanly headless on 2 vCPU / 3 GB, so the
  independent oracles are the analytic target heightmap and the analytic
  slot geometry (see SPEC.md, "Reference cross-check").
- numpy 2.5.3 (PyPI, sha256-pinned wheels) and Python 3.12 are the only
  dependencies; the judge's simulator is ~450 lines of stdlib + numpy, MIT
  licence like the rest of this repo. `media/`, `REPRODUCE.md` and the
  independent reproduction run are tracked in RECEIPT.md as not yet done.

## Reproducing every number

```bash
bash judge/setup.sh
bash judge/selftest.sh                       # kill rate + determinism line
bash judge/grade.sh examples/good/cam.py --json /tmp/v.json
python3 -c "import json;print(json.load(open('/tmp/v.json'))['summary'])"
```

Every number quoted above comes from those three commands with the default
seed (20261014); the verdict JSON contains the per-gate measurements.
RECEIPT.md holds two fresh-environment runs side by side.
