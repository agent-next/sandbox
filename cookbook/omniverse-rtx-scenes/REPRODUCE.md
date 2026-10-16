# REPRODUCE.md — independent reproduction

> **Who:** a different agent from the builder, following **only** README.md,
> working in a fresh sandbox (no repo context, no build state).
> **Numbers must match RECEIPT.md** within the tolerances in SPEC.md §8.4.

State at the time of writing: **pending** — the reproduction run is the
second of the two receipt runs and needs the account's single RTX 5090
seat, which another lease (`gl-cafaec-2`, not created by this agent) has
been holding idle since 2026-10-16T04:11Z with no exec activity and no
idle reaper (PRODUCT-FRICTION.md F3). This file is filled in from the
reproduction run's verbatim output before the demo is declared done.

---

## 1. Environment (fresh sandbox, cold start)

```
# the only inputs the README names
export SBX_API_KEY=<key>
bash judge/setup.sh          # pinned venv, --require-hashes
python3 run.py
```

Recorded on entry (COPY IN VERBATIM):

```
# paste here: python3 -VV, uname -a, pip freeze for the judge venv,
# git rev-parse HEAD, and the build_scenes.py version lines
```

## 2. Steps followed (only what the README states)

<!-- tick each; if a step needed a hint NOT in the README, stop and file it
     against the README per DEMO-STANDARD "Launch" — the README is wrong,
     not the agent. -->

- [ ] `bash judge/setup.sh` completed (pinned, hashed)
- [ ] `python3 run.py` reached a GPU lease (attempt N of the 409 retries)
- [ ] render + download + judge + delete all ran
- [ ] `python3 run.py` exited 0 with `verdict PASS`

## 3. Reproduction numbers vs RECEIPT.md

| number | RECEIPT.md | reproduction | tolerance | match |
|--------|-----------|--------------|-----------|-------|
| build_scenes wall (s) | | | ±20 % (CPU) | |
| bundle bytes (max) | | | exact (same git SHA) | |
| create seconds (s) | | | no tolerance (contended 409s allowed) | |
| upload MB/s | | | ±25 % | |
| render seconds (s) | | | see SPEC.md §8.4 (GPU clock) | |
| billed_s | | | ±5 % (meter latency) | |
| G1 IoU min per scene | | | ≥ same as RECEIPT | |
| judge verdict | PASS | | exact | |
| mutants killed | 7/7 | | exact | |

## 4. Deviations / surprises

(Anything the README did not cover, verbatim.)

## 5. Verdict

<!-- fill in only after the run: MATCH / MISMATCH with the deltas. -->
