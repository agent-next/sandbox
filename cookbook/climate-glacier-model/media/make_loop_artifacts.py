#!/usr/bin/env python3
"""Write the artifacts that the agent-loop figure replays.

The loop figure (media/fig_loop.py) shows the judge's verdict per iteration
of a plausible fix sequence: an agent starts from a model with four real
bugs, fixes one per iteration, and passes on the fifth.  Every iteration is
generated here as a *cumulative single edit* of examples/good/model.py, so
each one is a real artifact that grade.sh grades for real -- the figure
plots measured verdicts, not an illustration.

The bugs are ordered so the judge's first failing gate (it reports the
earliest gate in SPEC order: artifact, determinism, zero_melt, crossing,
final_volume, shape, figure) changes every iteration:

  iter1  stray write outside --out, ignored --zero-melt, unit slip, tiny figure
  iter2  stray write fixed                       -> zero_melt
  iter3  --zero-melt honoured                    -> final_volume (unit slip)
  iter4  unit fixed                              -> figure (tiny figure)
  iter5  figure fixed                            -> all gates pass

Usage: make_loop_artifacts.py <good-dir> <outdir>
Writes <outdir>/iter<N>/model.py and prints one line per iteration.
"""

import sys
from pathlib import Path

# (label, old line, new line) applied cumulatively to build each iteration.
STRAY_BUG = ('    write_csv(os.path.join(args.out, "volumes.csv"), series)',
             '    open("volumes.csv.bak", "w").write("scratch\\n")\n'
             '    write_csv(os.path.join(args.out, "volumes.csv"), series)')
ZEROMELT_BUG = ("    amp = 0.0 if zero_melt else a2",
                "    amp = a2")
UNIT_BUG = ("    return float(W * H[X < length].sum() * DX / 1e9)",
            "    return float(W * H[X < length].sum() * DX / 1e6)")
FIGURE_BUG = ("    fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=200)",
              "    fig, ax = plt.subplots(figsize=(3.0, 2.0), dpi=200)")

# iteration -> the bugs still present at that iteration
ITERATIONS = [
    (1, [STRAY_BUG, ZEROMELT_BUG, UNIT_BUG, FIGURE_BUG]),
    (2, [ZEROMELT_BUG, UNIT_BUG, FIGURE_BUG]),
    (3, [UNIT_BUG, FIGURE_BUG]),
    (4, [FIGURE_BUG]),
    (5, []),
]


def apply(good: str, edits) -> str:
    text = good
    for old, new in edits:
        if text.count(old + "\n") != 1:
            raise SystemExit(f"make_loop_artifacts: anchor {old!r} found "
                             f"{text.count(old + chr(10))} times")
        text = text.replace(old + "\n", new + "\n")
    return text


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: make_loop_artifacts.py <good-dir> <outdir>",
              file=sys.stderr)
        return 2
    good = (Path(sys.argv[1]) / "model.py").read_text()
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)
    for n, edits in ITERATIONS:
        text = apply(good, edits)
        d = outdir / f"iter{n}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "model.py").write_text(text)
        labels = ", ".join(name for name, _ in
                           [( "stray-write", STRAY_BUG),
                            ("zero-melt-ignored", ZEROMELT_BUG),
                            ("unit-slip", UNIT_BUG),
                            ("tiny-figure", FIGURE_BUG)] if _ in edits) \
            or "none"
        print(f"loop: iter{n}/model.py  remaining bugs: {labels}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
