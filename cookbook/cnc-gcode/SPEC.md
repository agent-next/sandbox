# cnc-gcode: 2.5D pocket milling with G-code, judged by a material-removal simulation

## Goal

An agent writes its own CAM program (`cam.py`, Python stdlib + numpy only) that
reads `spec.json` and emits `part.nc` — real RS274/NGC G-code (G17 G21 G90,
G0/G1/G2/G3, F, S, M3/M5) — for one 2.5D milling job: a **rectangular pocket
with a round island** machined in an aluminium block with a flat end mill.
A judge the agent cannot fool then *simulates the G-code* as material removal
on a 0.05 mm heightmap grid and decides, with numeric rules, whether the part
is machined to spec: pocket cleared, island and walls un-gouged, passes within
stepdown/stepover limits, chip load in band, rapids never plough into stock.

Why a sandbox: the agent designs and fixes its own artifact (the CAM script and
the G-code it emits) inside a disposable machine, iterating against the judge.
Nothing it writes can touch a real machine tool, and the judge — a simulator
independent of the artifact — is never modified by anything the agent runs.

## The job (spec.json — the single machine-readable source of truth)

| item | value |
|---|---|
| stock | 80 × 60 × 25 mm aluminium 6061-T6, X0 Y0 at the stock's lower-left corner, Z0 at the stock top, Z negative into the stock |
| pocket | 56 × 36 mm, centred at (40, 30), 6.0 mm deep, **corner radius 6.0 mm** |
| island | Ø 16.0 mm round pillar, centred at (40, 30), left at full stock height (top Z = 0) |
| tool | Ø 6.0 mm 2-flute **flat** end mill |
| limits | max stepdown 2.0 mm, max stepover 3.0 mm, spindle 8000 rpm ± 5 %, chip load 0.02–0.20 mm/tooth, feed 300–2500 mm/min |
| machine | envelope X [0, 210], Y [0, 210], Z [−30, 60] mm; safe Z = +5.0 mm; the machine starts at (0, 0, safe Z) |
| grid | 0.05 mm (1600 × 1200 cells over the stock footprint) |

`corner_radius (6.0) >= tool radius (3.0)`, so the pocket is fully machinable
by the tool; the judge nevertheless computes the unreachable-corner allowance
from geometry, not from this observation (see the residual gate).

## Non-goals (explicitly out of scope)

- No 3D / multi-surface machining, tool tilt, or 3+2 axis work — strictly 2.5D
  (flat-bottomed features at constant Z per pass).
- One tool, one program: no tool changes, no tool-length offsets, no wear
  offsets, no work-offset shifts (G54 etc.), no canned cycles, no cutter
  compensation via G41/G42 — the agent applies the tool-radius offset itself in
  `cam.py`.
- No machine dynamics: acceleration, look-ahead, jerk, spindle ramp-up,
  coolant, chip evacuation, tool deflection, cutting forces or power. The
  process limits are checked geometrically (stepdown, stepover, chip load).
- No islands other than the one round island, no rest machining, no adaptive
  clearing, no simulation of the tool shank or holder (tool length is
  unlimited).
- No inch mode: the program must be in G21 (millimetre) mode, absolute
  distances (G90), XY plane (G17).

## Artifact

The agent produces **`cam.py`**, run by the judge as

```
python3 cam.py --spec spec.json --out part.nc
```

in a scratch copy (the judge always feeds it the repo's own `spec.json`; the
artifact cannot change the spec it is graded against). `cam.py` must:

- import only the Python standard library and numpy (checked by AST — the
  allowlist is in the judge),
- be deterministic (no randomness, no network, no clock),
- write `part.nc`: millimetre G-code using only `G0 G1 G2 G3 G17 G21 G90`,
  `M3 M5` (`M2`/`M30` optional program end), `F`, `S`, `X Y Z I J` words and
  `( ... )` / `;` comments. Arcs are I/J centre-offset form in the XY plane.
  Anything else (G20, G91, G18/G19, canned cycles, R-form arcs, ...) is
  rejected by the judge with a named error, not silently reinterpreted.

The judged object is the *G-code* `part.nc` that `cam.py` emits, plus the fact
that `cam.py` itself is a self-contained stdlib/numpy script.

## The judge's simulation model (independent of the artifact)

`judge/gcode_sim.py` parses `part.nc` and simulates it as pure material
removal on a heightmap grid of 0.05 mm cells (cell centres at `(i+0.5)·g`,
`(j+0.5)·g`), initialised to Z = 0 (stock top):

- The tool is a cylinder with a flat bottom of radius `r = 3.0 mm`. A move is
  simulated by sweeping the tool's footprint — the set of grid cells within
  `r` (+1e-9 mm, a closed-set tie-break) of the move's path (line segment or
  arc) — and setting `H = min(H, Z_end)` there. A move that ramps down in Z is
  modelled at its end Z: everything above `Z_end` in the footprint is removed.
- G0 rapids remove material too (a rapid that hits stock is a crash, and the
  judge both flags it and models the damage).
- Stock below the pocket floor is modelled down to Z = −25 mm (the stock
  bottom); the envelope check keeps the tool above Z = −30 mm.

The analytic oracle for every geometry gate is the target heightmap derived
from `spec.json` alone:

```
target(x, y) = -6.0 mm   if (x, y) is inside the rounded-rect pocket AND outside the island disk
             =  0.0 mm   otherwise (stock top; island left standing)
```

The judge never looks at the toolpath the artifact *intended* — only at the
heightmap its G-code actually produces, and at the spec.

## Judge gates (numeric pass rules)

`judge/grade.sh` runs `cam.py` in a scratch copy, then `judge/grade.py`
evaluates the gates below. Every gate must pass. Reported numbers land in the
verdict JSON under `gates.<name>` with `pass: true|false` and the measured
values.

| # | gate | rule (fail if ...) |
|---|---|---|
| 0 | `artifact` | `cam.py` parses, imports only the allowlisted stdlib+numpy modules, runs (timeout 120 s, exit 0) and writes a non-empty `part.nc`. |
| 0b | `units` | no `G20` (inch mode) anywhere in `part.nc`, on a raw lexical scan that runs before the full parse — a `G20` line fails here *by name, quoting the offending line number* (a mutant is killed only when a named gate fails; a bare parse error is not a kill). `G21` presence is also checked by gate 1. |
| 1 | `program` | G-code parses; `G21`, `G90` and `G17` present; no unsupported words; `M3` (with `S`) precedes the first cutting move; the program ends with `M5`; every feed move carries a feed rate (modal or explicit). |
| 2 | `envelope` | every sampled point of every move (endpoints, arc extremes, 1° arc samples) is inside X [0, 210], Y [0, 210], Z [−30, 60]. |
| 3 | `stepdown` | axial engagement of every cutting move — `max(H_before − Z_end)` over the swept footprint — is ≤ 2.0 mm + 1e-6. |
| 4 | `stepover` | pass spacing of every lateral feed move — the minimum distance from points sampled every 0.25 mm along its path to any earlier-executed lateral feed path at the same Z level (±1e-9 mm) — is ≤ 3.0 mm + 0.05 (one grid cell of measurement tolerance). The first lateral feed move at each Z level is exempt (it is the level's entry slot). |
| 5 | `process` | for every feed move: `chip load = F / (S × flutes)` in [0.02, 0.20] mm/tooth, `F` in [300, 2500] mm/min, and `S` within ±5 % of 8000 rpm. |
| 6 | `rapid_safety` | every G0 whose end Z is below the safe Z (+5.0 mm) sweeps only over already-cut air: no grid cell in its footprint may have `H_before > Z_end + 0.01` mm. (So a rapid plunge into stock, or a rapid traverse through uncut stock, fails; plunging into material must be a G1 at feed.) |
| 7 | `residual` | after the whole program, every cell of the must-clear region — inside the pocket, outside the island, and reachable by the tool (see allowance below) — has `H ≤ target + 0.05` mm. Reported: worst residual (mm) and residual area (mm²). |
| 8 | `gouge` | no cell may have `H < target − 0.01` mm, outside a one-grid-cell band around the pocket and island boundaries (grid quantisation allowance; a real gouge is orders of magnitude larger). Reported: worst gouge depth (mm) and gouged area (mm²). |
| 9 | `simulator_selfcheck` | the judge simulates two synthetic programs of its own on fresh stock: a 20 mm straight slot and a full circle, both cut at Z = −2. The measured slot width at 5 stations (8 radial stations for the circle) must equal the tool diameter 6.0 mm within one grid cell (0.05 mm). This cross-checks the line- and arc-sweep rasteriser against analytic geometry on every grade run, independent of the artifact. |
| 10 | `reference` | **independent cross-check with LinuxCNC's standalone RS274/NGC interpreter `rs274`** (Debian bookworm `linuxcnc-uspace 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2`, GPLv2+, https://github.com/LinuxCNC/linuxcnc — pinned URLs + sha256 in `judge/reference_packages.tsv`, extracted rootless by `setup.sh`). The reference must (a) parse and execute the program to exit 0, (b) select millimetre units in its own canonical output (`USE_LENGTH_UNITS ... MM`; a G20 program reports INCH and fails here), and (c) its canonical move list — counts of feeds/rapids/arcs, min/max Z, XY bounding box (both sides use the same conservative arc convention: endpoints + arc centres) — must agree with the judge's own parsed move list exactly for counts and within 1e-3 mm for coordinates. The one accepted append is a trailing `M2` line (rs274 requires a program-end word; the spec makes M2/M30 optional for the artifact). |

**Corner/unreachable allowance in gate 7.** The must-clear region excludes
cells no legal tool position can reach: cells inside the pocket whose distance
to the allowed tool-centre set (pocket inset by the tool radius, corner radius
`R − r` clamped at 0, minus the disk of radius `island_radius + r` around the
island centre) exceeds `r`. For this spec (`R = 6 ≥ r = 3`, island annulus
10 mm wide > Ø 6) that set is empty — the check is exact, not forgiving. If
the spec ever carried `R < r` the allowance would grow automatically.

**Reference cross-check.** Gate `reference` (owner direction: prefer mature
open-source tools over our own code) runs the program through LinuxCNC's
standalone RS274/NGC interpreter `rs274` — the reference interpreter of the
open-source CNC world (LinuxCNC: github.com/LinuxCNC/linuxcnc, 2.5 k stars,
GPL-2.0, actively maintained; the packaged build is Debian bookworm's,
pinned by URL + sha256 and installed rootless by `setup.sh`, no apt and no
root). Its canonical move list must agree with the judge's own simulator on
feeds/rapids/arcs counts, min/max Z and the XY bounding box.
Alternatives considered: CAMotics (needs Qt/X11 and a long source build; does
not install cleanly headless) and building rs274 from the LinuxCNC source
tree (needs the full linuxcnc build); the packaged standalone interpreter
installed in minutes and is the mature choice. If a future environment cannot
install it, `grade.py` fails gate `reference` with "rs274 not installed" —
the judge never silently falls back to self-agreement only.

## Acceptance oracle (self-test)

`judge/selftest.sh` proves the judge can fail:

- the known-good example `examples/good/cam.py` passes every gate;
- each of the seven single-edit mutants produced by `judge/mutate.py` from that
  example is **killed by at least one *named* gate** — a mutant rejected only
  by a crash, parse error or timeout (no gate flagged in the verdict JSON) is
  *not* a kill and fails the self-test outright:
  `no_tool_offset` (offset scale 0 → `gouge`), `deep_pass` (single full-depth
  pass → `stepdown` 6 > 2 mm), `rapid_into_stock` (plunge emitted as G0 →
  `rapid_safety`), `swapped_arcs` (G2/G3 swapped on the island contour →
  `residual`), `inch_mode` (G20 → `units`), `wide_stepover` (stepover 1.2 × D →
  `stepover` and `residual`), `hot_feed` (feed × 5 → `process` chip load
  0.5 > 0.20 mm/tooth);
- reference note: all six semantically-bad mutants are *syntactically valid*
  G-code, so rs274 parses them without error (their defects are geometric or
  process-level, invisible to a syntax-only reference); the `inch_mode` program
  reports `USE_LENGTH_UNITS INCH` and is rejected by gate `reference` too;
- grading the good example twice with the same seed yields byte-identical
  verdict JSON (excluding the `timing` key);
- kill rate ≥ 90 % (7/7 = 100 % expected), else the self-test exits non-zero.

## Tools (pinned by the judge)

| tool | version | how pinned |
|---|---|---|
| Python | 3.12 (stdlib parts of the judge) | system interpreter, `>= 3.12` asserted |
| numpy | 2.5.3 (PyPI wheel, cp312 manylinux/musllinux x86-64) | `judge/requirements.txt`, `pip install --require-hashes`; sha256 per wheel; released 2026-09-06 |
| LinuxCNC `rs274` (reference gate) | 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2 (Debian bookworm `linuxcnc-uspace`) | `judge/reference_packages.tsv`: URL + sha256 per `.deb`, extracted rootless by `setup.sh` |
| `libboost-python1.74.0`, `libpython3.11` (rs274 runtime deps) | 1.74.0+ds1-21, 3.11.2-6+deb12u9 (bookworm) | same `.tsv`, same sha256 check |

No tool is fetched as "latest". `judge/setup.sh` installs numpy into a private
venv at `$HOME/.cnc-gcode/venv` and records what it installed in
`judge/VERSIONS.txt`.

## Determinism

The judge has no random choices (`--seed` is accepted and recorded but unused);
simulation is pure numpy arithmetic on a fixed grid, single-threaded. The same
`part.nc` always yields the same verdict JSON.
