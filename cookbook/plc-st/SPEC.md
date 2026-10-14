# plc-st: IEC 61131-3 Structured Text tank controller, judged in a virtual plant

## Goal

An agent writes a tank fill/drain controller in IEC 61131-3 **Structured Text**,
compiles it with an open IEC 61131-3 compiler (**MATIEC `iec2c`**, pinned
below), links it into a scan-cycle harness, and runs it against a simulated
industrial plant. A judge it cannot fool decides, with numeric rules, whether
the controller is safe and correct — including under injected sensor faults.

The point of using a sandbox: the agent installs the pinned compiler, compiles
its own Structured Text, and iterates against the judge in an isolated, disposable
environment. Nothing it does can touch the real machine, and the judge is
unmodified by anything the artifact does.

## Plant model (the controlled system)

A vertical tank with four sensors and three actuators:

| signal | kind | meaning |
|---|---|---|
| `start` | BOOL in | momentary run / restart pushbutton |
| `estop` | BOOL in | emergency stop, pressed = TRUE |
| `high_ls` | BOOL in | high level switch, TRUE = tank at/above 85 cm |
| `low_ls` | BOOL in | low level switch, TRUE = tank at/below 15 cm |
| `level` | REAL in | analog level transmitter, cm |
| `pump` | BOOL out | main drain pump |
| `inlet_valve` | BOOL out | fill valve |
| `outlet_valve` | BOOL out | discharge valve in series with the pump |
| `alarm` | BOOL out | latched fault indication |
| `running` | BOOL out | latched run-mode indicator |

The plant integrates per scan (10 ms):

- filling: `level += 2.0 cm/s × dt` while `inlet_valve` is open,
- draining: `level -= 3.0 cm/s × dt` while `pump` and `outlet_valve` are both on,
- `level` is clamped to `[0, 100]` cm,
- discrete switches are ideal: `high_ls = level >= 85.0`,
  `low_ls = level <= 15.0`.

## Non-goals (explicitly out of scope)

- No process visualization, web UI, HMI, SCADA, or networking.
- No redundant dual-channel safety architecture, certified SIL rating, or
  formal verification. This is an educational interlock exercise.
- No PID / analog control on the level transmitter; control is bang-bang
  around the discrete switches, with the analog level used only for
  independent safety interlocks and discrepancy detection.
- No device-driver layer or real I/O; the harness writes the sensor values
  and reads the actuator states directly.

## Artifact

The agent produces a single file: `tank_ctrl.st` — a PROGRAM `tank_ctrl` with
the `VAR_INPUT` / `VAR_OUTPUT` above, plus a CONFIGURATION `tank_cfg` that runs
it on a `fast` task with `INTERVAL := T#10ms`. The judge compiles this file
with the pinned `iec2c`, links it with a fixed harness, and runs scenarios.

Required behaviour of a correct controller (what the judge checks, numerically):

1. **Autocycle** — after a `start` pulse, the controller fills to the high band,
   then drains to the low band, repeating. The level must complete at least two
   full fill→drain cycles in a 120 s run.
2. **Overflow safety** — the level must never exceed **94 cm** in any scenario,
   even when the high level switch fails (jammed open). The analog overflow
   guard (`level > 88` shuts the inlet) is the independent backstop.
3. **Dry-run safety** — the pump must never run while `level < 15 cm` AND the
   low switch reports dry. If the low switch is jammed open (never trips), the
   analog dry-run interlock (`level < 15` stops the pump) must still hold.
   If the low switch falsely trips (jammed closed), the pump must stop.
4. **Emergency stop** — within one scan of `estop` asserting, `pump`,
   `inlet_valve`, and `outlet_valve` are all FALSE, and stay FALSE while
   `estop` is held.
5. **Latch / recovery** — after an E-stop is released, no actuator may run
   until a fresh `start` pulse; after that pulse the controller returns to the
   normal autocycle.
6. **Actuation discipline** — the pump must never be on together with the
   inlet valve (no "fill while draining" through the wrong valve).
7. **No spurious alarm** during a fault-free autocycle.

## Judge gates (numeric pass rules)

The judge (`judge/grade.sh` → `judge/grade.py`) runs six deterministic
scenarios, each a clocked event script against the analytic plant, and checks
the numeric properties below. Every scenario must pass for a green verdict.

| # | scenario | inputs (scan index → value) | must hold |
|---|---|---|---|
| 1 | `cycle` | start pulse at t=0, from 40 cm | ≥2 autocycles; level ≤ 94; pump never on below 15; never pump+inlet |
| 2 | `overflow_guard` | start pulse; high_ls forced 0 for all scans, from 70 cm | level ≤ 94; pump never on below 15; never pump+inlet |
| 3 | `dry_run` | start pulse from 10 cm | pump never on below 15; level ≤ 94; autocycle ≥2 |
| 4 | `dry_interlock_fault` | start pulse; low_ls forced 0 for all scans, from 40 cm | pump never on below 15; level ≤ 94; never pump+inlet |
| 5 | `lowsw_false_trip` | start pulse; from 80 cm; low_ls forced 1 from t=1000 (tank ~63 cm, pump running) | pump off within 200 scans of the trip; pump never below 15; level ≤ 94 |
| 6 | `estop` | start pulse; estop=1 at t=400, from 40 cm | from t=401 on, all three actuators off; level ≤ 94 |
| 7 | `recovery` | start; estop at 400; release at 500; start at 700 | nothing actuates 500–700; resumes autocycle after 700; level ≤ 94 |
| 8 | `random_faults` | start pulse; seeded random estop pulses + stuck sensors | pump never below 15; never pump+inlet; level ≤ 94 |

Each scenario is run against a fresh engine (controller state reset per
scenario). The judge's plant model is an independent oracle (analytic per-scan
integration), not derived from the controller's logic.

## Acceptance oracle

The judge fails (non-zero exit) if any scenario's numeric check fails. The
self-test (`judge/selftest.sh`) proves the judge can fail: the known-good
example in `examples/good/tank_ctrl.st` must pass all gates, and each of the
six single-edit mutants generated by `judge/mutate.py` must fail at least one
gate. The required kill rate is ≥ 90 % (6/6 = 100 %).

## Tools (pinned by the judge)

| tool | what | how pinned |
|---|---|---|
| MATIEC `iec2c` commit `75d6e82cce5bc8b98ce03a417b106884cbb7ebb5` | IEC 61131-3 ST → C compiler | sha256 of the GitHub tarball: `a679c8e69459c2e4a05850438e073866eeb695b598ff244029dac0ea5d8e9a08`; GPL-3.0 |
| gcc / g++ (Debian 12.2.0) | C compiler + linker for generated C + harness | Debian bookworm package |
| make (GNU 4.3) | build | Debian bookworm package |
| bison / flex / autoconf / automake / libtool | build MATIEC from source | Debian bookworm package |
| Python 3.12 (stdlib only) | judge / plant model / scenario driver | system python3 |

No tool is fetched with `latest`. Versions are pinned either by exact release
sha256 or by exact Debian package version.

## Deviations from the brief (lead's ask)

The lead's brief mentioned "dry-run interlock" and "pump never runs when level
is below low switch". Here the dry band is tied exactly to the low switch point
(15 cm) so the two statements coincide: the pump must never run at or below the
low switch, whether the switch is telling the truth or lying.