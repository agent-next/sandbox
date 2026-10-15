# HANDOFF — apple-app-build (2026-10-15, wrap-up on owner request)

Goal: launch-ready "build iPhone/Mac apps on Linux in our sandbox" — `apple` template +
this cookbook demo + a closed loop that runs the build on a Devin macOS VM.

## State

| piece | status | where |
|---|---|---|
| `apple` template (Swift 6.2.3 + xtool 1.22.2 + Darwin SDK 26.2 + rcodesign + `apple-build`) | built, `check_apple.sh` OK, pushed private | agent-infra PR #1014; image `ghcr.io/agent-next/apple@sha256:0b9ea65b20b1dd050e4d9a26c314589eb5bac228c5988f8184e68e2be098e9a1` (9.48 GB) |
| SDK archive (Xcode content, not in git) | kept | img-build-do1 `/root/xtool-assets/darwin-xcode26.2-17C52.xtoolsdk.tgz` sha256 `33b07733…576f4` |
| prod-1 registry copy | done (crane, root disk untouched) | `localhost:5000/apple:v0.0.1` on prod-1 |
| prod registration (`aenv pull` + `PLATFORM_TEMPLATES` alias) | NOT done | next step 1 |
| judge (`judge/apple_judge.py`, stdlib) | done; good 3/3 PASS, mutants 12/12 killed, deterministic | this dir |
| `run.py` (template `apple`, build 3 kinds, grade) | written, NOT run end to end (needs the alias) | this dir |
| `run_on_mac.py` (Devin macOS closed loop) | PASS 6/6 in 133 s (session cf675a20, acct devin2); first try failed on my port bug, fixed | `media/mac-run/` holds that run's video + screenshots |
| README / SPEC | written; README has `__HERO__`/`__MEDIA__`/`__TIMINGS__` placeholders | this dir |
| RECEIPT, REPRODUCE, pitch, STORYBOARD, media (result.png, loop.png, demo.mp4), result.json | template stubs, NOT done | this dir |

Evidence: `agent-next/task-runs/20261015-xtool-apple-build/` (RECEIPT.md spike, LOOP1.md loops 1-2, loop1 media).

## Next steps (in order)

1. **Register on prod-1** (`ssh root@161.35.176.224`): `aenv pull localhost:5000/apple@sha256:40f024c1da6949822d7a4c9c65d6fdcbe3b161ad8fc8f70e282fee4be21ee530 --name apple-v0-0-1 --cpu 4 --memory 8192 --timeout 3600` (platform manifest digest; the index is 0b9ea65b…). Then add `apple=<template id>` to `PLATFORM_TEMPLATES` in agent-infra `ops/gateway.env.example` (on PR #1014, else the next deploy reverts it) and `/etc/sbx/gateway.env` (back up first), restart the gateway. prod-1 root disk is 87 % used (52 GB free): never `docker pull` big images there; use crane registry-to-registry (recipe in RECEIPT/LOOP notes).
2. Run `python3 run.py` twice in fresh sandboxes -> fill RECEIPT.md, README placeholders, `media/result.json` (TODOs in `write_result_manifest`).
3. `python3 run.py --run-on-mac` once (DEVIN_API_KEY = devin2 `windsurf_api_key` from `~/.local/share-devin2/devin/credentials.toml`, DEVIN_ORG_ID `org-e2f13c34001a41eda72dd84b5f789de3`; account 3 / cwang75 org is `out_of_quota`). Owner approved Devin Mac runs 2026-10-15; cap stays 2 ACU.
4. Media: demo.mp4 in Remotion or HyperFrames inside a sandbox from real footage only — the sandbox build terminal + the simulator recording (convert VFR -> CFR first: `simctl recordVideo` writes frames only on change). Pass `cookbook/tools/video_gate.py`, open frames, cross-model frame review.
5. REPRODUCE.md by a different model family; review both PRs (cross-model), merge #1014 then this PR; add to the demos gallery.

## Pitfalls found

- Public port edge: 413 above ~200 MB per request; upload into a sandbox ~0.85 MB/s vs 43 MB/s download (agent-infra#1008).
- `xtool new` needs `--skip-setup` without a TTY; `xtool dev build --ipa` needs `zip`.
- AppImage extract is 0700 (chmod a+rX); a Docker ARG named `RCODESIGN_*` is read by rcodesign as config.
- xtool 1.20.1 (SDK epoch 2) rejects the epoch-3 SDK; 1.22.2 pinned deliberately.
