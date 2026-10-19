#!/usr/bin/env python3
"""Write single-edit known-bad copies of the known-good artifacts.

Usage: mutants.py <good_dir> <out_dir>
Prints one line per mutant: <file> <kind> <what was broken>. Deterministic (no randomness).
"""

import plistlib
import struct
import sys
import zipfile
from pathlib import Path

LC_BUILD_VERSION = 0x32
LC_CODE_SIGNATURE = 0x1D


def rewrite(src, dst, edit):
    """Copy zip src to dst, passing (name, bytes) through edit(name, data) -> bytes | None (drop)."""
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = edit(info.filename, zin.read(info.filename))
            if data is not None:
                zout.writestr(info, data)


def load_cmd_offset(data, wanted):
    ncmds = struct.unpack_from("<I", data, 16)[0]
    off = 32
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        if cmd == wanted:
            return off
        off += size
    raise ValueError(f"load command {wanted:#x} not found")


def is_exe(name, exe):
    return name.endswith("/" + exe) and "/_CodeSignature/" not in name


def mutants(good, out):
    sim, ipa, mac = good / "Tally-sim.zip", good / "Tally.ipa", good / "SbxBar-mac.zip"
    exe_sim, exe_mac = "Tally.app/Tally", "SbxBar.app/Contents/MacOS/SbxBar"

    def patch_exe(target, fn):
        return lambda n, d: fn(bytearray(d)) if n == target else d

    def set_platform(p):
        def fn(d):
            off = load_cmd_offset(d, LC_BUILD_VERSION)
            struct.pack_into("<I", d, off + 8, p)
            return bytes(d)
        return fn

    def set_cpu_x86(d):
        struct.pack_into("<I", d, 4, 0x01000007)
        return bytes(d)

    def flip_code_byte(d):
        d[0x4000 + 0x100] ^= 0xFF  # a byte inside the second code page (__TEXT)
        return bytes(d)

    def drop_signature_magic(d):
        off = load_cmd_offset(d, LC_CODE_SIGNATURE)
        dataoff = struct.unpack_from("<I", d, off + 8)[0]
        d[dataoff:dataoff + 4] = b"\0\0\0\0"
        return bytes(d)

    def plist_edit(fn):
        def edit(n, d):
            if n.endswith("Info.plist") and "/_CodeSignature/" not in n:
                p = plistlib.loads(d)
                fn(p)
                return plistlib.dumps(p)
            return d
        return edit

    cases = [
        ("m01-sim-platform-ios.zip", sim, "ios-sim", patch_exe(exe_sim, set_platform(2)), "simulator app whose Mach-O says platform ios"),
        ("m02-sim-x86_64.zip", sim, "ios-sim", patch_exe(exe_sim, set_cpu_x86), "cputype rewritten to x86_64"),
        ("m03-sim-code-byte.zip", sim, "ios-sim", patch_exe(exe_sim, flip_code_byte), "one code byte flipped after signing"),
        ("m04-sim-no-bundle-id.zip", sim, "ios-sim", plist_edit(lambda p: p.pop("CFBundleIdentifier")), "CFBundleIdentifier removed"),
        ("m05-sim-minos-16.zip", sim, "ios-sim", plist_edit(lambda p: p.update(MinimumOSVersion="16.0")), "plist minimum OS 16.0 vs binary 17.0"),
        ("m06-sim-wrong-exe-name.zip", sim, "ios-sim", plist_edit(lambda p: p.update(CFBundleExecutable="Talley")), "CFBundleExecutable names a missing file"),
        ("m07-ipa-sim-platforms.ipa", ipa, "ios", plist_edit(lambda p: p.update(CFBundleSupportedPlatforms=["iPhoneSimulator"])), "device ipa declaring the simulator platform"),
        ("m08-ipa-platform-macos.ipa", ipa, "ios", patch_exe("Payload/Tally.app/Tally", set_platform(1)), "device ipa whose Mach-O says platform macos"),
        ("m09-mac-signature-wiped.zip", mac, "mac", patch_exe(exe_mac, drop_signature_magic), "code signature superblob magic zeroed"),
        ("m10-mac-not-appl.zip", mac, "mac", plist_edit(lambda p: p.update(CFBundlePackageType="BNDL")), "CFBundlePackageType BNDL, not an app"),
        ("m11-mac-two-apps.zip", mac, "mac", None, "a second .app bundle in the archive"),
        ("m12-mac-not-a-zip.zip", mac, "mac", "truncate", "archive truncated to half"),
    ]
    out.mkdir(parents=True, exist_ok=True)
    for name, src, kind, edit, what in cases:
        dst = out / name
        if edit == "truncate":
            raw = src.read_bytes()
            dst.write_bytes(raw[: len(raw) // 2])
        elif edit is None:
            rewrite(src, dst, lambda n, d: d)
            with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "a") as zout:
                for info in zin.infolist():
                    zout.writestr(info.filename.replace("SbxBar.app/", "SbxBar2.app/", 1), zin.read(info.filename))
        else:
            rewrite(src, dst, edit)
        print(f"{dst} {kind} {what}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    mutants(Path(sys.argv[1]), Path(sys.argv[2]))
