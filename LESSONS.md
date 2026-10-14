<!-- reviewed-through: a07e93887d21973e22a5aa204e82ce0bff4d8821 (2026-10-14) -->

Agents write, review and merge this repo's code. A nightly review
(`.claude/skills/nightly-review/SKILL.md`) records what went wrong here. A
lesson seen on 3 or more distinct days moves into `docs/acceptance.md`.

## Verify, don't claim

**A lost reply is not a confirmation: verify, and report failure instead of claiming success.**
- 616b07c (#6): a runner kill that hit the same 503 as the blip was logged as done, and the sandbox held a quota slot until its lifetime ended, so the pool stalled on 429s. Fixed in 616b07c (retry with backoff, emit kill_failed).
- d877345 (#3): a GPU destroy reply lost to a timeout was treated as cleanup; run.py now GETs the lease and raises, naming the sandbox id, when it cannot confirm. Fixed in d877345.
- e08022b (#11): run.py exited 0 when it could not confirm the sandbox was gone, contrary to cookbook/DEMO-STANDARD.md. Fixed in e08022b.
- Seen 2× (2026-10-13, 2026-10-14).

**A transport error is not a process exit: reattach before you kill.**
- bbae8c3 (#5): a gateway restart broke the runner's command stream; boot() took that for the runner's exit and killed a sandbox still running a job. Fixed in 616b07c.
- 114975e (#7): a stream that drops right after each reattach looped without sleeping, and its outage window restarted on every drop; a slot retired mid-outage and a runner that exited while disconnected were reported as errors. Fixed in 114975e.
- Seen 1× (2026-10-13).

## Fail loudly, don't misreport

**An error must keep its identity through cleanup, and invalid input is rejected before it is clamped.**
- 2ba7914 (#9): a non-404 alias lookup and an import error masked by a failed cleanup surfaced as other errors; SandboxNotFoundException read as a clean runner exit; the quota cap turned an invalid --warm > --max into a silent fit; a boolean max_concurrent counted as 1. Fixed in 2ba7914.
- Seen 1× (2026-10-14).

**Validate the whole response before printing any rows.**
- 60b2634 (#3): a malformed sandbox inventory printed as a successful empty or partial list; the entire response is now validated first and malformed data raises. Fixed in 60b2634.
- acbcedf (#3): invalid JSON and non-printable id or column values were accepted; both now raise. Fixed in acbcedf.
- Seen 1× (2026-10-12).

## The judge is part of the demo

**The judge must accept every valid form of the input it claims to grade.**
- e08022b (#11): parse_scalar_entry and the viscosity mutant only matched `nu <value>;`, so a valid dimensioned `nu [0 2 -1 0 0 0 0] <value>;` case was rejected. Fixed in e08022b.
- Seen 1× (2026-10-14).

## Docs match reality

**Docs must match what a cold-start agent or CI can actually do.**
- 1a793d8 (#8): the quickstart pointed at the web console, which a cold-start agent or CI job cannot open; there is no `sbx login` — the key comes from the environment. Fixed in 1a793d8.
- Done right: 5a1f0c3 (#3) kept the CLI's idle deletion and the plugin's pause semantics distinct in the docs.
- Seen 1× (2026-10-14).

**Error text at the shell must name the flag the user just set.**
- 1a793d8 (#8): `sbx exec` leaked SDK exceptions — a timeout said to pass 'timeout' or 'request_timeout' "when making the request", never naming --timeout, and hid that the command may still be running; a wrong or dead id answered "Paused sandbox <id> not found" even when the id never existed. Fixed in 1a793d8.
- Seen 1× (2026-10-14).

## Tests prove the change

**A behavior change ships a test that fails without the change.**
- 60b2634 (#3): ten malformed inventory payloads, each asserted to exit non-zero with no partial output.
- 9c9a8e5 (#6): runners survive a gateway blip without killing the job or leaking the sandbox.
- d5fc63a (#9): template aliases, lookup/cleanup errors, gone sandboxes and quota-cap validation.
- 1a793d8 (#8): exec timeout and not-found errors address the CLI user.
- Done right: bbae8c3 (#5) shipped 954 lines of runner tests with the feature.
- Seen 3× (2026-10-12, 2026-10-13, 2026-10-14). Promoted to docs/acceptance.md.

## A standard nobody checks

**A standard that nothing checks is violated on first use.**
- 67d2023 (#10): cookbook/DEMO-STANDARD.md merged 2026-10-14T10:19:30Z.
- e08022b (#11): the first demo built against it merged 20 s later with review findings — its run.py exited 0 on unconfirmed cleanup, contrary to the standard. Fixed in e08022b.
- Seen 1× (2026-10-14).

## Real runs catch what checklists miss

**A real sandbox run is the only check that finds missing system libraries.**
- 46b9f16 (#7): a real run failed on libGL.so.1, a missing system library no static checklist had caught.
- Done right: 9e89ad8 (#7) replaced anecdote with a measured real-CI comparison (135/135 jobs passed, median and worst queue waits per job type).
- Seen 1× (2026-10-13).

## Small edits with quiet blast radius

**Appending to a config file must not clobber what is already there.**
- aafc261 (#7): `echo ... > .env` would have clobbered an existing .env; changed to `>>`.
- Seen 1× (2026-10-13).
