# Desktop computer-use demo — LibreOffice Calc driven by scripted actions

## Goal

Show an agent performing a real **computer-use** task on a graphical Linux
desktop: it drives LibreOffice Calc through a window manager, using scripted
mouse/keyboard actions exactly as a computer-use agent would, to open a CSV,
add a computed column, add a `SUM` row, and save the result as `.xlsx`. A
judge it cannot fool then decides whether the result is right — not by
watching the script run, but by opening the saved workbook with `openpyxl`
and comparing every number against an independent computation.

The point of the sandbox: the desktop stack (X server, window manager,
LibreOffice, screenshot tools) is installed from nothing on a machine the
agent does not control, the GUI is driven for real on a real display, and the
whole desktop is thrown away afterwards. Nothing about the host leaks into the
verdict.

## Non-goals

- Not a LibreOffice feature demo, not a test of the Calc GUI, and not a test of
  the `xdotool`/screenshot tools. They are the environment, not the subject.
- No layout/pixel-perfect grading of the spreadsheet. We grade the *stored
  values* the workbook holds after the agent is done, read back through a
  different library than the one that wrote them.
- No network, no real files beyond the two fixtures the judge ships, no
  multi-monitor, no clipboard, no dialogue-localisation concerns.
- Not a benchmark. Wall time is reported because a judge that takes an hour is
  useless, not because speed is graded.

## The artifact

The agent produces a single Python file, `actions.py`, that performs the whole
task when run with `python3 actions.py` inside the sandbox. It must:

1. Start from the fixture the judge provides: a CSV at
   `/tmp/desktop-cu/input.csv`.
2. Drive LibreOffice Calc on a real X display to open that CSV.
3. Add a computed column (see the *task contract* below).
4. Add a `SUM` row.
5. Save the workbook as `/tmp/desktop-cu/report.xlsx` in true OOXML (`.xlsx`)
   format.
6. Exit `0` on success, non-zero on failure.

`examples/good/actions.py` is the reference artifact. The judge copies whatever
directory it is given to a scratch location, places the fixture, and runs
`actions.py` from there — so the artifact is a drop-in replacement for
`examples/good/`.

### Task contract (what the columns mean)

The fixture `input.csv` has a header row and at least two numeric columns.
With the seed fixed by the judge, the reference fixture is:

```
item,qty,price
apple,3,0.50
banana,2,0.25
cherry,5,1.00
```

The workbook the agent must produce, *once openpyxl reads it back*, is:

| | A | B | C | D |
|---|---|---|---|---|
| 1 | item | qty | price | total |
| 2 | apple | 3 | 0.50 | **1.50** |
| 3 | banana | 2 | 0.25 | **0.50** |
| 4 | cherry | 5 | 1.00 | **5.00** |
| 5 | **total** | **10** | | **7.00** |

- Column `D` is the computed column. `D{n}` holds `B{n} * C{n}` for every data
  row `n` in `2..N`.
- Row `N+1` is the total row. `A{N+1}` is the literal text `total`,
  `B{N+1}` is `SUM(B2:B{N})`, `C{N+1}` is empty, and `D{N+1}` is
  `SUM(D2:D{N})`.

The judge fixes the fixture contents and seed, so every number above is
deterministic and known to the judge *before* the agent runs. The agent (or its
author) may read the same `SPEC.md`; the judge does not take the agent's word
for any of these values.

## The desktop the agent runs on

The judge starts the agent on a private X display with a real window manager,
exactly as a user's desktop would be:

- **X server**: `Xvfb` (virtual framebuffer), a single display per grade.
- **Window manager**: `fluxbox`, so windows get real frames, focus and
  activation — the agent must manage a real WM, not a bare X server.
- **Application**: LibreOffice Calc, installed from the OS package manager.
- **Action/screenshot tools**: `xdotool` (mouse + keyboard) and ImageMagick
  `import` (screenshots).

The agent's `actions.py` receives the display on which it must work via the
`DISPLAY` environment variable and must use that display. It may drive the GUI
with `xdotool`, with `pyautogui`, or with anything else that ends with the right
workbook on disk — the judge only inspects the resulting file, never the method.

## Acceptance oracle

The judge never trusts the artifact to report about itself. Four independent
oracles:

1. **The saved workbook, read back by `openpyxl`** — a *different* library from
   the one that produced it. Every required cell is compared, value and
   position, against the judge's own arithmetic from the fixture.
2. **Screenshot non-blankness** — before and after screenshots of the display,
   taken by the judge (not the artifact), must differ and must not be blank.
   This proves a real GUI ran and changed, not a headless file write.
3. **The file format** — `report.xlsx` must be a real ZIP/OOXML workbook, so an
   artifact that wrote a CSV, an `.xls`, or a renamed file cannot pass.
4. **Checksums of the judge directory** — taken before and after each grade, so
   no artifact can edit its own judge.

Gates are numeric, deterministic, and pass/fail. There is no partial credit and
no "the script ran" gate standing alone: every gate compares against something
outside the artifact.

## Gates

The judge prints exactly one verdict JSON object. All gates must pass for exit
code 0. `P` = measured value, `R` = rule.

| # | gate | what is measured | pass rule |
|---|---|---|---|
| 1 | `artifact_ran` | exit status of `python3 actions.py` on the private display | exit `0` **and** stderr contains no Python traceback |
| 2 | `screenshot_before` | PNG the judge captures of the display before the agent runs | decodes, `>= 100 x 100` px, and is not a single flat colour |
| 3 | `screenshot_after` | PNG the judge captures after the agent finishes | decodes, `>= 100 x 100` px, not flat, and **differs from the before shot** in at least `DIFF_PIXELS_MIN` pixels |
| 4 | `report_exists` | `/tmp/desktop-cu/report.xlsx` | exists, is a regular file, and is readable as a ZIP (true OOXML, not CSV/xls/renamed) |
| 5 | `data_column_present` | header row of the workbook read back by openpyxl | `A1 == "item"`, `B1 == "qty"`, `C1 == "price"`, `D1 == "total"` |
| 6 | `computed_column_values` | `D2..D{N}` vs `qty * price` per row | every `D{n}` equals `round(B{n} * C{n}, 2)` to within `0.005`, and `D1` is not counted |
| 7 | `total_row_label` | cell `A{N+1}` | equals the literal text `total` |
| 8 | `total_row_qty` | cell `B{N+1}` | equals `sum(qty)` within `0.005` |
| 9 | `total_row_total` | cell `D{N+1}` | equals `sum(D2:D{N})` within `0.005` |
| 10 | `total_row_col_c` | cell `C{N+1}` | empty / `None` |
| 11 | `no_extra_rows` | the used range of the sheet | no data row beyond `N+1` (a stray extra row means the SUM range or the row count is wrong) |
| 12 | `judge_intact` | sha256 of every file under `judge/`, before vs after | identical |

Numeric constants. `grade.sh` takes only `--seed` and `--json` on the command
line; the values below are environment variables:

| constant | default | meaning |
|---|---|---|
| `DIFF_PIXELS_MIN` | `2000` | after-shot must differ from before-shot by at least this many pixels |
| `SHOT_W` | `1024` | screenshot width in pixels |
| `SHOT_H` | `768` | screenshot height in pixels |
| `SOFFICE_READY_S` | `30` | seconds the judge waits for Calc's window to appear |
| `AGENT_S` | `240` | seconds allowed for `actions.py` to finish |
| `ROW_TOL` | `0.005` | absolute tolerance on every numeric comparison |

The fixture is fixed in `judge/fixtures.py` and the seed selects it; the
reference fixture above is the one used for the default seed. The judge computes
its expected values from the fixture directly — never from the artifact — so a
wrong seed or a hand-edited fixture cannot make a wrong workbook pass.

### Screenshot rules

The screenshots are taken with ImageMagick's `import` against the judge's own
`DISPLAY`, *before* the judge starts the agent and *after* the agent's process
has exited. The before-shot is taken once the Calc window is up and showing the
CSV (the judge opens the CSV itself, so the "before" state is the same for every
artifact); the after-shot is taken once `actions.py` has exited. The diff is a
plain pixel count over the two PNGs. This is a coarse, honest check: it cannot
be fooled by a script that writes the file without touching the GUI, and it does
not require the GUI to look any particular way.

## Known-bad artifact family

`judge/mutants.py` generates ≥ 5 single-edit mutants of `examples/good/actions.py`
by exact string edit, so each mutant differs from the reference by one
localised change:

| mutant | edit | gate that must fail |
|---|---|---|
| `wrong-cell` | computed column targets `C * C` instead of `B * C` | `computed_column_values` |
| `wrong-format` | saves with a `.csv`/CSV filter name | `report_exists` (not a ZIP) |
| `wrong-sum-range` | `SUM` over `B2:B{N-1}` instead of `B2:B{N}` | `total_row_qty` |
| `no-save` | skips the save step entirely | `report_exists` |
| `crash-midway` | raises after opening the CSV but before saving | `artifact_ran` / `report_exists` |

Every mutant must fail at least one gate. `judge/selftest.sh` runs all of them,
prints the kill rate, and exits non-zero if the kill rate is below 90 %.

## What this demo does not prove

- That LibreOffice renders this workbook prettily, that the columns are wide
  enough, or that the numbers are formatted to two decimals — we grade values,
  not cosmetics.
- That the agent's actions are the *only* way to produce the file. The judge
  grades the workbook, so a clever agent that writes the workbook directly
  (bypassing the GUI) would still be checked by the screenshot gates only to
  the extent that a real GUI must have run. This is the honest limit of any
  computer-use judge: it verifies the environment was used, not the keystrokes.
- Anything about timing, throughput, or how many screenshots per second the
  agent consumes.
