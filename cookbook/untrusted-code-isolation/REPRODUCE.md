# REPRODUCE: independent reproduction

Per `cookbook/DEMO-STANDARD.md`, this demo merges only after a **different
agent, from a different model family than the builder, follows only
README.md in a fresh sandbox** and records its numbers here. The numbers
must match `RECEIPT.md` within the tolerances SPEC.md states (the
deterministic set: the 15 verdicts and reasons, the gate pass vector, the
benign sha256 set, the mutant kill list, effect booleans, capped byte
counts; wall times, load, memory and process counts are reported, never
gated).

## Status: not yet done

No independent reproduction has been run as of 2026-10-15T19:30Z. The two
runs in `RECEIPT.md` were both made by the builder. This file is a
placeholder for the required independent run, deliberately left blank
rather than filled with numbers nobody measured.

## What the independent run must do

1. Get an `SBX_API_KEY` (it is an environment variable, not a repo file).
2. Install the CLI: `pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`.
3. In a fresh sandbox — no pre-warmed box, no state from the builder —
   from the repository root run only what README.md says:

   ```bash
   python3 cookbook/untrusted-code-isolation/run.py --ref main
   ```

4. Record here: the run.py exit code, the per-step wall times, the gate
   vector, the 15 verdict/reason pairs, the benign sha256 set, the mutant
   kill list, and the measured-effect numbers.
5. Compare with RECEIPT.md: every deterministic number must match
   exactly; the measured numbers must stay inside their stated bounds.

## What to do if the numbers do not match

Do not adjust the numbers to fit. A mismatch means either the judge is
non-deterministic beyond the declared noisy keys (a real bug in the
judge — fix the judge, do not widen the scrub list), or the run environment
differs (a different sandbox template, kernel, or account limits — record
the difference and re-run). Either way, the honest outcome is to leave
this file describing the mismatch and block the merge.
