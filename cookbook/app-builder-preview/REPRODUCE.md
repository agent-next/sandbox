# app-builder-preview — independent reproduction

Status: **pending**. This file is filled in by a different agent (a model
family other than the builder's) following only `README.md` in a fresh
sandbox, before this demo is merged.

The independent reproducer must, per `cookbook/DEMO-STANDARD.md`:

- work from a **fresh shallow clone** at the merged ref, reading only
  `README.md` (and `SPEC.md` where the README points to it) to drive the
  run — not the builder's notes, not the judge source;
- run the README's one-command run end to end and record its **exit code
  and measured wall time**;
- report the numbers it actually measured — gates, flow pass count, build
  size, console errors, self-test kill rate — side by side with the
  `RECEIPT.md` values, and state whether they agree within the tolerances
  in `SPEC.md` (this demo's tolerances are **none**: every assertion is an
  exact DOM equality, so the verdict must be identical);
- record every command it ran, and any deviation from the README;
- confirm its own sandbox(es) are killed and gone (`sbx list` omits them).

The builder does not edit this section's findings; the reproducer's
recorded numbers stand as written.

## Reproduction record

_(to be completed by the independent reproducer)_
