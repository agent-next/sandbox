# apple-app-build — an iPhone app and a Mac app built on Linux, proven byte by byte and run on a Mac

An agent writes Swift, then builds an iOS Simulator app, an iPhone `.ipa` and a macOS `.app`
inside a disposable agent-next Linux sandbox — no Mac, no Xcode — using the `apple` template
(Swift 6.2.3 + [xtool](https://github.com/xtool-org/xtool) + Darwin SDK 26.2 + rcodesign). A
standard-library judge re-parses every artifact: zip layout, Info.plist, the Mach-O platform
and minimum OS, and every code-signature page hash. "It compiled" is not enough to pass — a
simulator app labelled as iPhone, a flipped code byte or a wiped signature all fail. With
`--run-on-mac`, the simulator build is then installed on a Devin macOS VM, tapped and
recorded, and the counts it reads off the screen must be 0 -> 3 -> 0.

**Hero result:** __HERO__

## Results

__MEDIA__

## Ask your agent

> Create an agent-next sandbox from the `apple` template, clone
> https://github.com/agent-next/sandbox, and run `bash cookbook/apple-app-build/judge/setup.sh`.
> Write a SwiftUI iOS app (SwiftPM library + `xtool.yml`, see `cookbook/apple-app-build/app/Tally`),
> build it with `apple-build ios-sim <dir>` and `apple-build ios <dir>`, then run
> `bash cookbook/apple-app-build/judge/grade.sh <artifact> <kind>` and iterate until it prints `"PASS"`.

## One-command run

```bash
python3 run.py                 # build + judge in a fresh `apple` sandbox
python3 run.py --run-on-mac    # + install, tap and record on a Devin macOS VM
python3 run.py --ref my-branch --keep
```

Needs the `sbx` CLI (`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` (or `E2B_API_KEY`). `--run-on-mac` also needs `DEVIN_API_KEY` and
`DEVIN_ORG_ID` for a Devin organization with macOS sessions; each run is capped at
`DEVIN_MAX_ACU` (default 2) and the session is always terminated.

__TIMINGS__

## How the judge works

- `judge/setup.sh` — checks Python 3.9+ and records the toolchain versions (`judge/VERSIONS.txt`); the judge itself is standard library only and grades anywhere.
- `judge/grade.sh <artifact> <ios-sim|ios|mac>` — four gates (layout, plist, macho, signature), rules in `SPEC.md`; one JSON verdict, exit 0 only on PASS.
- `judge/selftest.sh` — the three known-good artifacts pass, all 12 single-edit mutants from `judge/mutants.py` fail (each gate kills at least one), grading is byte-identical twice, `judge/` is unchanged.
- `run_on_mac.py` — serves the zip from the sandbox on a token URL (checked by sha256 through the public URL before any Mac time is spent), runs the Devin session with a structured-output schema, pulls the recording and screenshots back, and gates on sha / install / launch / counts 0-3-0 / no crash / files received.

## Limits

- Device install, TestFlight and notarization need an Apple account; the `.ipa` is unsigned and Mac apps are ad-hoc signed (a browser download of one is quarantined: `xattr -dr com.apple.quarantine`).
- The `apple` template carries Apple SDK content and is a private agent-next template; outside it, build the SDK yourself with `xtool sdk build <Xcode.xip>`.
- Linux cannot run the apps; the Mac run needs a macOS machine (here a Devin macOS VM).
- `ld64.lld` warns that iOS linking is unsupported; the judge's Mach-O and signature checks are what show the output is valid.
