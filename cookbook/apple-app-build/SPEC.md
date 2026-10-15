# apple-app-build — spec

## Goal

An agent builds an iPhone app and a Mac app from Swift source inside a Linux sandbox — no
Mac, no Xcode — and a judge that parses the artifacts byte by byte decides whether they are
real Apple apps for the platform they claim. Optionally the simulator build is then installed,
tapped and recorded on a macOS VM, and the counts it reads off the screen must match.

## Fixed problem statement (judge constants)

| quantity | value |
|---|---|
| apps | `app/Tally` (SwiftUI counter, iOS 17, bundle id `com.agentnext.tally`), `app/SbxBar` (SwiftUI menu-bar app, macOS 14) |
| artifact kinds | `ios-sim` (arm64 iOS Simulator .app, zipped, ad-hoc signed), `ios` (device .ipa, unsigned allowed), `mac` (arm64 macOS .app, zipped, ad-hoc signed) |
| toolchain (sandbox template `apple`) | Swift 6.2.3, xtool 1.22.2, Darwin SDK 26.2 (iPhoneOS / iPhoneSimulator / MacOSX), rcodesign 0.29.0 |
| Mac run | Devin macOS VM, iPhone simulator, tap `+1` x3 then `Reset` x1; expected on-screen counts 0, 3, 0 |

## Non-goals

- Device install, TestFlight, App Store review, notarization (need an Apple account).
- Running Apple binaries on Linux (impossible; that is what the Mac run is for).
- UI quality of the sample apps.

## Artifact

`<Name>-sim.zip` / `<Name>.ipa` / `<Name>-mac.zip`, as printed by `apple-build <kind> <dir>`.

## Judge gates (all must pass) — `judge/apple_judge.py`

1. **layout** — the archive is a valid zip holding exactly one `.app` bundle at the path the kind requires (`X.app/`, `Payload/X.app/`).
2. **plist** — `Info.plist` parses; `CFBundleIdentifier` set; `CFBundleExecutable` names a file in the bundle; minimum OS set; iOS kinds declare `CFBundleSupportedPlatforms` = `[iPhoneSimulator]` / `[iPhoneOS]`; mac declares `CFBundlePackageType` = `APPL`.
3. **macho** — the executable is a thin 64-bit arm64 `MH_EXECUTE`; `LC_BUILD_VERSION` platform is 7 (iossimulator) / 2 (ios) / 1 (macos) for the kind, and its minos equals the plist minimum OS.
4. **signature** — `ios-sim` and `mac` carry an embedded code signature whose CodeDirectory hashes match every code page and whose Info.plist special slot matches the bundled Info.plist (`ios` is checked the same way when signed; unsigned passes).

Mac run (`run_on_mac.py`, optional): sha256 of the downloaded zip matches, `simctl install` and `launch` succeed, counts read off the three screenshots are 0 / 3 / 0, no crash in the app's log, and the recording plus three screenshots are received.

## Acceptance oracle

The Mach-O load commands and the code-signature hashes are recomputed from the bytes by the
judge (standard library only); they are the same structures the Apple loader and
`codesign --verify` check. The Mac run is a real install on Apple's own simulator.

## Self-test

`judge/selftest.sh`: the three known-good artifacts in `examples/good` pass; all 12 single-edit
mutants from `judge/mutants.py` fail (each gate kills at least one); grading twice gives
byte-identical verdict JSON; `judge/` is unchanged after grading.
