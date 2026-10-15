# Desktop computer-use: LibreOffice Calc driven by scripted actions

An agent performs a real **computer-use** task on a graphical Linux desktop:
it drives LibreOffice Calc through a window manager with scripted mouse and
keyboard actions — exactly as a computer-use agent would — to open a CSV, add
a computed `total` column (`qty * price`), add a `SUM` total row, and save the
result as `.xlsx`. A judge it cannot fool then opens the saved workbook with a
different library (`openpyxl`) and compares every number against its own
arithmetic from the fixture. The point of the sandbox: the whole desktop stack
(X server, window manager, LibreOffice) is installed from nothing on a machine
the agent does not control, the GUI is driven for real on a real display, and
the desktop is thrown away afterwards — nothing about the host leaks into the
verdict.

## Ask your agent

> Clone this repo, then in `cookbook/desktop-computer-use/` read `SPEC.md`.
> Your artifact is `examples/good/actions.py`. Improve it (or write your own)
> until `bash judge/grade.sh examples/good/actions.py` exits 0, then run
> `bash judge/selftest.sh` and confirm the judge still fails every known-bad
> mutant.

## One command

Needs Python 3.10+, the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` (or `E2B_API_KEY`) in the environment:

```bash
python3 cookbook/desktop-computer-use/run.py --ref main
```

The command creates a disposable sandbox, clones this repo at `--ref` into it,
installs the pinned desktop stack, runs the judge self-test, grades the
known-good artifact, prints the verdict JSON, and always kills the sandbox
(confirmed via `sbx list`). It exits non-zero if any step fails. `--keep`
leaves the sandbox up and prints its id. Measured wall times per step are in
[RECEIPT.md](RECEIPT.md); the gates and their numeric pass rules are in
[SPEC.md](SPEC.md).

## Limits, plainly

- The judge grades the *values* the workbook holds, not the keystrokes: a
  script that writes the file without touching the GUI is caught only by the
  screenshot gates, which prove a real GUI ran and changed.
- No network, no clipboard, no multi-monitor; the fixture and the seed are
  fixed by the judge, so every number it expects is known before the agent
  runs.
- A judge run takes minutes, not seconds — see RECEIPT.md for the measured
  per-step wall times.
