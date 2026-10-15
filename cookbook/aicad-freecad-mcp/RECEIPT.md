# RECEIPT — aicad-freecad-mcp

Real command output from this demo's build-out. Environment: the disposable
build sandbox itself (Debian 12, 2 vCPU, ~4 GB RAM, Python 3.12.15) — the
same stack `judge/setup.sh` installs. Every block below is pasted output,
not a summary. `run.py`'s end-to-end `sbx create → … → sbx kill` wrapper
cannot run inside this build sandbox (a sandbox cannot create a sandbox);
each step of its in-sandbox sequence was executed here directly against a
fresh `git clone` of this branch, output pasted below.

## Run 1 — fresh install (new `$HOME`, AppImage sha-256 re-verified, full
venv creation, AppImage extraction, freecad-mcp clone at pinned SHA)

```
$ HOME=/tmp/fakehome2 bash judge/setup.sh ; echo EXIT=$?
[setup] creating judge venv at /tmp/fakehome2/.venvs/aicad-judge
[setup] installing pinned judge deps (trimesh, manifold3d, cadquery/OCP, ezdxf)
[setup] FreeCAD AppImage present, sha256 verified earlier
[setup] extracting AppImage (takes a couple of minutes)
[setup] extracted to /tmp/fakehome2/freecad-1.0.1
[setup] cloning freecad-mcp at pinned SHA 78bf0230a03324b56c9a0b7f55150fb5be2a0d42
[setup] installing freecad-mcp into its own venv
[setup] freecad-mcp addon installed with loopback-only RPC auto-start
[setup] xvfb-run already present
[setup] versions recorded in .../judge/VERSIONS.txt
[setup] setup complete
EXIT=0
real 1m16.248s  (the very first run also downloads the 849 MB AppImage and
                verifies sha256 5a3fc405771b4fbb5f270110d055bc135123c9fc91bb7dbb5d068ac7fbe50f6e)
```

`judge/VERSIONS.txt` after the run:

```
aicad-freecad-mcp judge tool versions
recorded: 2026-10-15T00:35:39Z
requirements.txt sha256: 54054604372bfdc58f8850ad972c31a4da84a6ff7c6622889c546c6fba9beb0b
freecad: FreeCAD 1.0.1 Revision: 39285 (Git)
freecad appimage sha256: 5a3fc405771b4fbb5f270110d055bc135123c9fc91bb7dbb5d068ac7fbe50f6e
freecad-mcp git SHA: 78bf0230a03324b56c9a0b7f55150fb5be2a0d42
freecad-mcp addon version: 0.1.27
trimesh: 4.6.6
manifold3d: 3.1.1
cadquery: 2.5.2
ezdxf: 1.4.0
numpy: 2.2.6
OCP: 7.7.2 (via cadquery)
```

Idempotent re-run (everything already installed): exit 0, 6.8 s.

## Tool pipeline — MCP drive of the checked-in agent scripts

This is the exact in-sandbox step `run.py` sends (`bash -c` of the same
lines, fresh clone of this branch, tools from `judge/setup.sh`; FreeCAD GUI
under Xvfb, addon RPC on 127.0.0.1:9875, freecad-mcp MCP server over stdio):

```
$ python3 driver/drive_freecad.py --mcp-command $HOME/.venvs/freecad-mcp/bin/freecad-mcp \
      --freecadcmd $HOME/freecad-1.0.1/usr/bin/freecadcmd
[drive] MCP server initialized: {'name': 'FreeCADMCP', 'version': ''}
[drive] bracket  OK  volume=61853.9828 mm^3  (0.7 s)
[drive] bushing  OK  volume=42625.1291 mm^3  (0.4 s)
[drive] plate    OK  volume=71505.9189 mm^3  (1.7 s)
```

## Run 2 — selftest (same environment, repo working tree)

```
$ bash judge/selftest.sh ; echo EXIT=$?
== selftest: known-good artifacts ==
  good/bushing PASS (volume 42625.13 mm^3)
  good/plate PASS (volume 71505.92 mm^3)
  good/bracket PASS (volume 61853.98 mm^3)
== selftest: known-bad mutants ==
  bracket_no_fillet killed by: brep,features,stl_topology,xor_reference
  bushing_bore_22 killed by: brep,features,stl_topology,xor_reference
  bushing_stl_flip killed by: stl_topology
  bushing_stl_gap killed by: stl_topology
  plate_hole_count_5 killed by: features,xor_reference
  plate_hole_drift killed by: features
  plate_scale_25_4 killed by: bbox,brep,stl_topology
kill rate: 7/7 = 100%
== selftest: determinism ==
  two grades identical (excluding timing)
  judge/ unchanged
selftest OK
EXIT=0
real 1m20.231s
```

The same selftest, run from a fresh `git clone` of this branch (fresh
checkout, tools resolved via the default `~/.venvs/aicad-judge` and
`~/freecad-1.0.1` paths): identical output, kill rate 7/7 = 100 %, exit 0.

## Run 3 — grade of the known-good artifacts

```
$ bash judge/grade.sh examples/good/bushing --json /tmp/v.json ; echo EXIT=$?
EXIT=0    real 0m4.989s
$ bash judge/grade.sh examples/good/plate   --json /tmp/v.json
EXIT=0    real 0m4.660s
$ bash judge/grade.sh examples/good/bracket --json /tmp/v.json
EXIT=0    real 0m4.155s
```

Key numbers from `examples/good/bushing` (full verdict JSON, `all_pass: true`):

| gate | value | rule |
|---|---|---|
| brep | 1 solid, BRepCheck valid, volume 42625.1291 mm³, rel_error 0.0 | ≤ 0.5 % of analytic |
| bbox | (60.0, 60.0, 40.0), max axis error 0.0 mm | ≤ 0.05 mm |
| stl_topology | watertight ✓, winding-consistent ✓, 1512 faces, rel_error 4.14e-4 | ≤ 0.5 % |
| xor_reference | XOR 15.3664 mm³ = 3.61e-4 of reference 42607.7852 mm³ | ≤ 1 % |
| features | 3 cylindrical faces, radii {10, 18, 30} | exact within 0.05 mm |
| min_wall | 7.9974 mm (2400 samples, seed 20261015) | ≥ 1.2 mm |

plate: `all_pass: true` — xor_fraction 1.37e-4, 6 bolt holes at ρ = 35.000,
angles 0/60/…/300°, DXF audit 0 errors, 7 CIRCLEs, outline 100 × 80 centred.
bracket: `all_pass: true` — xor_fraction 1.7e-4, R5 ×2 + R6 ×2 + R8 fillet
face, min wall 8.06 mm.

## Determinism / reproducibility status

- two grades of the same artifact with the same `--seed` byte-identical
  apart from `timing` and per-gate `_s` — checked by `selftest.sh` (pass).
- (not done: two runs from two fresh **agent-next sandboxes** — `sbx create`
  is not available inside this build sandbox; `run.py` executes exactly the
  sequence above end-to-end when run from outside.)
- (not done: `REPRODUCE.md` independent reproduction by a different agent —
  happens before merge per DEMO-STANDARD.md.)

## Deviations

- **Builds run through `execute_code_headless`**: the freecad-mcp tool offers
  `execute_code` (GUI thread) and `execute_code_headless` (separate
  `freecadcmd` process). All three part builds are driven through the
  headless tool because Draft's DXF exporter cannot run on the GUI thread
  (it needs a 3-D view) and a headless-friendly path keeps the demo
  deterministic. The GUI + addon + RPC + MCP server are still exercised for
  real (`get_rpc_status` round-trips through the MCP server; FreeCAD itself
  produces every artifact).
- **pip pins without hashes**: `judge/requirements.txt` uses exact versions
  but not `--require-hashes` (the CadQuery/OCP dependency closure is ~40
  wheels); the AppImage tarball and the freecad-mcp git SHA are the two
  sha256/git-verified downloads.
- **xvfb/xauth via apt**: Debian packages (signed Release lists) rather
  than sha256-checked tarballs; `setup.sh` only installs them when missing.
- **Media**: deferred by task order (this task explicitly excludes media
  work). `(not done: media/, REPRODUCE.md)`.
- **min-wall sampling**: the 2400-sample ray-chord estimate can miss a thin
  strip (e.g. the plate's 2.25 mm rim reports 6.94 mm); it is a
  manufacturability trip-wire, not a certified minimum. Documented in
  SPEC.md.

## Clean-sequence rerun (earlier end-to-end failure)

An earlier `run.py --ref sbx/demo-aicad-freecad-mcp-fix-p` run failed at the
MCP drive step on a fresh sandbox (`FATAL: FreeCAD RPC addon is not listening
on port 9875`). Root cause, reproduced in a clean build sandbox: the image
ships `xvfb-run` but **not `xauth`**, and `xvfb-run` refuses to start without
it — it exits 3 with `xvfb-run: error: xauth command not found`, so FreeCAD
never launched and the RPC port never opened. `judge/setup.sh` only checked
`command -v xvfb-run`, concluded the X stack was present, and skipped the
apt install. (The original build sandbox had xauth, which is why the
pipeline passed there.)

Fixes (branch commits `85ad3a7`, `01bc2ac`):

- `judge/setup.sh` installs and then verifies both `xvfb` and `xauth`,
  failing loudly if either is missing after apt; it also resolves the addon
  Mod dir and the settings file from `freecadcmd`'s `getUserAppDataDir()`
  instead of a hard-coded path, and fails if the addon did not land there.
- `driver/drive_freecad.py` prints the tail of `/tmp/freecad.log` when the
  RPC port does not open in time, so this failure names its cause.
- `run.py` checks the FreeCAD GUI process is alive 2 s after launch (same
  log tail on failure) and narrows the cleanup `pkill` to the exact
  `$FREECAD_DIR/usr/bin/freecad` path.

Verification below: each in-sandbox script string copied from `run.py`, run
as its own `bash -lc` process (as `sbx exec` would), in order, in a sandbox
wiped first with
`rm -rf ~/.config/FreeCAD ~/.local/share/FreeCAD ~/.cache/freecad-mcp ~/freecad-1.0.1 ~/freecad-mcp-* ~/.venvs ~/FreeCAD_*.AppImage`
plus `sudo apt-get purge -y xauth xvfb` (the fixed setup.sh must reinstall
them) and no FreeCAD process left running. Environment: Debian 12, 2 vCPU,
3 GB RAM, Python 3.12.15 — same image class as that failing sandbox.

Step 1 — clone (as `run.py` sends it):

```
$ git clone --depth 1 -b sbx/demo-aicad-freecad-mcp-fix-p \
    https://github.com/agent-next/sandbox /tmp/sandbox
→ HEAD 01bc2ac, exit 0
```

Step 2 — `judge/setup.sh` (fresh `$HOME`: both venvs created, AppImage
downloaded 810 MB + sha256 `5a3fc405…` verified + extracted, freecad-mcp
cloned at pinned SHA, **xvfb + xauth installed by the fixed guard**):

```
[setup] creating judge venv at /home/user/.venvs/aicad-judge
[setup] installing pinned judge deps (trimesh, manifold3d, cadquery/OCP, ezdxf)
[setup] downloading FreeCAD 1.0.1 AppImage (~850 MB)
[setup] FreeCAD sha256 verified
[setup] extracting AppImage (takes a couple of minutes)
[setup] extracted to /home/user/freecad-1.0.1
[setup] cloning freecad-mcp at pinned SHA 78bf0230a03324b56c9a0b7f55150fb5be2a0d42
[setup] installing freecad-mcp into its own venv
[setup] freecad-mcp addon installed with loopback-only RPC auto-start
[setup] apt lists may be empty in this image; refreshing
[setup] installing xvfb + xauth (FreeCAD GUI needs an X server for the RPC addon)
[setup] versions recorded in .../judge/VERSIONS.txt
[setup] setup complete
SETUP_DONE
EXIT=0   wall ≈ 277 s
```

Step 3 — MCP drive (the step that had failed):

```
$ xvfb-run -a -s "-screen 0 1280x1024x24" $FREECAD_DIR/usr/bin/freecad \
    > /tmp/freecad.log 2>&1 &            (add-on auto-starts RPC on 9875)
$ python3 driver/drive_freecad.py --mcp-command $HOME/.venvs/freecad-mcp/bin/freecad-mcp \
    --freecadcmd $FREECAD_DIR/usr/bin/freecadcmd
[drive] MCP server initialized: {'name': 'FreeCADMCP', 'version': ''}
[drive] bracket  OK  volume=61853.9828 mm^3  (1.0 s)
[drive] bushing  OK  volume=42625.1291 mm^3  (0.6 s)
[drive] plate    OK  volume=71505.9189 mm^3  (2.7 s)
DRIVE_DONE
EXIT=0   real 0m20.934s
```

Step 4 — `judge/selftest.sh`:

```
== selftest: known-good artifacts ==
  good/bushing PASS (volume 42625.13 mm^3)
  good/plate   PASS (volume 71505.92 mm^3)
  good/bracket PASS (volume 61853.98 mm^3)
== selftest: known-bad mutants ==
  bracket_no_fillet killed by: brep,features,stl_topology,xor_reference
  bushing_bore_22 killed by: brep,features,stl_topology,xor_reference
  bushing_stl_flip killed by: stl_topology
  bushing_stl_gap killed by: stl_topology
  plate_hole_count_5 killed by: features,xor_reference
  plate_hole_drift killed by: features
  plate_scale_25_4 killed by: bbox,brep,stl_topology
kill rate: 7/7 = 100%
== selftest: determinism ==
  two grades identical (excluding timing)
  judge/ unchanged
selftest OK
EXIT=0   real 2m23.455s   (kill rate unchanged from Run 2: 7/7 = 100 %)
```

Step 5 — `judge/grade.sh` per part:

```
bushing  EXIT=0  wall 19.0 s   all_pass: True, 7/7 gates
plate    EXIT=0  wall  8.4 s   all_pass: True, 8/8 gates
bracket  EXIT=0  wall 10.7 s   all_pass: True, 7/7 gates
```

`python3 -m py_compile run.py` and `python3 -m py_compile
driver/drive_freecad.py`: clean. Still not done here: the end-to-end
`sbx create → … → sbx kill` wrapper itself (no `sbx` CLI inside this build
sandbox — same limitation as noted above).
