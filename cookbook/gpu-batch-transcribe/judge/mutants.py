#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the
good transcriber. Each mutant is the known-good artifact with exactly one
scripted edit; the self-test expects every mutant to fail at least one
gate (SPEC.md). Mutants cover the failure classes the judge exists for:

  decode-time bugs   - wrong onset lag, dead VAD threshold, skewed burst
                       clock, wrong edge trim, wrong frequency order
  output bugs        - empty transcripts, one letter dropped per utterance
  cheating           - pasted oracle tokens (hardcoding), delegating to an
                       external recogniser via subprocess
"""

import os
import sys

# (name, must-exist literal, replacement)
EDIT = [
    ("onset_lag_wrong", "ONSET_LAG = 8", "ONSET_LAG = 800"),
    ("vad_threshold_dead", "ONSET_THRESH = 0.12", "ONSET_THRESH = 0.99"),
    ("burst_clock_skew", "start = max(0, crossing - ONSET_LAG)",
     "start = max(0, crossing - ONSET_LAG + 720)"),
    ("edge_trim_all", 'skip = int(round(burst * EDGE_FRACTION))',
     'skip = int(round(burst * 0.5))'),
    ("row_col_swapped", 'r_hz = rows[int(torch.argmax(power[i, :len(rows)]))]',
     'r_hz = rows[int(torch.argmax(power[i + 1, :len(rows)]))]'),
    ("empty_transcripts", 'transcripts[uid] = " ".join(toks)',
     'transcripts[uid] = ""'),
    ("drop_last_letter", "for _ in range(n_tok):",
     "for _ in range(max(0, n_tok - 1)):"),
    ("hardcoded_token", 'MANIFEST = "manifest.json"',
     'MANIFEST = "manifest.json"\nHINT = "alpha"  # first letter, pasted'),
    ("delegate_subprocess", 'MANIFEST = "manifest.json"',
     'MANIFEST = "manifest.json"; import subprocess'),
    ("argmax_off_by_one",
     'r_hz = rows[int(torch.argmax(power[i, :len(rows)]))]',
     'r_hz = rows[(int(torch.argmax(power[i, :len(rows)])) + 1) % len(rows)]'),
]


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    good = open(os.path.join(src_dir, "transcriber.py")).read()
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, old, new in EDIT:
        if old not in good:
            raise SystemExit(f"mutant {name}: edit anchor not found in good artifact")
        mutant = good.replace(old, new, 1)
        if mutant == good:
            raise SystemExit(f"mutant {name}: edit produced no change")
        with open(os.path.join(out_dir, name + ".py"), "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
