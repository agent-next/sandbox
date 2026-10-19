#!/usr/bin/env python3
"""Judge an Apple app artifact built on Linux, standard library only.

Usage: apple_judge.py <artifact> <kind> [--json OUT]
  kind: ios-sim  (<Name>-sim.zip holding <Name>.app for the arm64 iOS Simulator)
        ios      (<Name>.ipa holding Payload/<Name>.app for iPhone/iPad)
        mac      (<Name>-mac.zip holding <Name>.app for arm64 macOS)

Gates (all must pass):
  layout     the archive holds exactly one .app bundle at the path the kind requires
  plist      Info.plist parses; bundle id, executable name, platform list and minimum OS set
  macho      the executable is a thin arm64 MH_EXECUTE whose LC_BUILD_VERSION platform
             matches the kind and whose minos equals the plist's minimum OS
  signature  ios-sim/mac: an embedded code signature whose CodeDirectory page hashes match
             every code page and whose Info.plist slot matches the bundled Info.plist
             (ios: checked the same way when present; unsigned is allowed)
Prints one JSON verdict; exits 0 only on PASS.
"""

import hashlib
import io
import json
import plistlib
import struct
import sys
import zipfile

PLATFORM = {"mac": 1, "ios": 2, "ios-sim": 7}
PLATFORM_NAME = {1: "macos", 2: "ios", 7: "iossimulator"}
PLIST_PLATFORMS = {"ios": ["iPhoneOS"], "ios-sim": ["iPhoneSimulator"]}
CPU_ARM64 = 0x0100000C
MH_MAGIC_64 = 0xFEEDFACF
MH_EXECUTE = 2
LC_CODE_SIGNATURE = 0x1D
LC_BUILD_VERSION = 0x32
CSMAGIC_EMBEDDED = 0xFADE0CC0
CSMAGIC_CODEDIRECTORY = 0xFADE0C02
CS_ADHOC = 0x2
HASHES = {1: hashlib.sha1, 2: hashlib.sha256}


def gate(ok, measured, threshold):
    return {"pass": bool(ok), "measured": measured, "threshold": threshold}


def version(v):
    """Packed xxxx.yy.zz -> 'X.Y' (patch dropped when 0)."""
    major, minor, patch = v >> 16, (v >> 8) & 0xFF, v & 0xFF
    return f"{major}.{minor}" + (f".{patch}" if patch else "")


def norm(v):
    parts = [int(p) for p in str(v).split(".")] + [0, 0]
    return tuple(parts[:3])


def find_app(names, kind):
    """Return the .app prefix (with trailing '/') or an error string."""
    apps = set()
    for n in names:
        parts = n.split("/")
        if kind == "ios":
            if len(parts) >= 3 and parts[0] == "Payload" and parts[1].endswith(".app"):
                apps.add("Payload/" + parts[1] + "/")
        elif len(parts) >= 2 and parts[0].endswith(".app"):
            apps.add(parts[0] + "/")
    if len(apps) != 1:
        return None, f"{len(apps)} .app bundles: {sorted(apps)}"
    return apps.pop(), None


def load_commands(data):
    magic, cpu, _sub, ftype, ncmds, _size, _flags, _res = struct.unpack_from("<8I", data, 0)
    off, cmds = 32, []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<2I", data, off)
        cmds.append((cmd, off, size))
        off += size
    return magic, cpu, ftype, cmds


def check_signature(data, cmds, plist_bytes):
    """Verify the primary-or-SHA256 CodeDirectory against the binary. Returns (ok, detail, adhoc)."""
    sig = [c for c in cmds if c[0] == LC_CODE_SIGNATURE]
    if not sig:
        return None, "no LC_CODE_SIGNATURE", False
    dataoff, datasize = struct.unpack_from("<2I", data, sig[0][1] + 8)
    blob = data[dataoff:dataoff + datasize]
    if len(blob) < 12 or struct.unpack_from(">I", blob, 0)[0] != CSMAGIC_EMBEDDED:
        return False, "signature superblob magic missing", False
    _m, _len, count = struct.unpack_from(">3I", blob, 0)
    dirs = []
    for i in range(count):
        stype, soff = struct.unpack_from(">2I", blob, 12 + 8 * i)
        if (stype == 0 or 0x1000 <= stype < 0x1005) and struct.unpack_from(">I", blob, soff)[0] == CSMAGIC_CODEDIRECTORY:
            dirs.append(soff)
    if not dirs:
        return False, "no CodeDirectory", False
    best = None
    for soff in dirs:
        hash_type = blob[soff + 37]
        if hash_type in HASHES and (best is None or hash_type == 2):
            best = soff
    if best is None:
        return False, "no supported hash type", False
    cd = best
    (_magic, _length, _ver, flags, hash_off, _ident, n_special, n_code, code_limit) = struct.unpack_from(">9I", blob, cd)
    hash_size, hash_type, _plat, page_log = blob[cd + 36], blob[cd + 37], blob[cd + 38], blob[cd + 39]
    page = 1 << page_log if page_log else code_limit
    h = HASHES[hash_type]
    bad = 0
    for i in range(n_code):
        start = i * page
        chunk = data[start:min(start + page, code_limit)]
        want = blob[cd + hash_off + i * hash_size: cd + hash_off + (i + 1) * hash_size]
        if h(chunk).digest()[:hash_size] != want:
            bad += 1
    detail = f"{n_code - bad}/{n_code} code pages match ({h().name}, {'adhoc' if flags & CS_ADHOC else 'cert'})"
    if n_special >= 1:
        slot = blob[cd + hash_off - hash_size: cd + hash_off]
        if any(slot):
            plist_ok = h(plist_bytes).digest()[:hash_size] == slot
            detail += f"; Info.plist slot {'matches' if plist_ok else 'MISMATCH'}"
            bad += 0 if plist_ok else 1
    return bad == 0 and n_code > 0, detail, bool(flags & CS_ADHOC)


def judge(path, kind):
    gates = {}
    try:
        z = zipfile.ZipFile(path)
        names = z.namelist()
    except (OSError, zipfile.BadZipFile) as e:
        gates["layout"] = gate(False, f"not a zip: {e}", "valid zip with one .app")
        return gates
    app, err = find_app(names, kind)
    gates["layout"] = gate(app is not None, err or app, "exactly one .app bundle")
    if app is None:
        return gates

    contents = app + ("Contents/" if kind == "mac" else "")
    plist_name = contents + "Info.plist"
    try:
        plist_bytes = z.read(plist_name)
        info = plistlib.loads(plist_bytes)
    except (KeyError, plistlib.InvalidFileException, ValueError) as e:
        gates["plist"] = gate(False, f"Info.plist unreadable: {e}", "parseable Info.plist")
        return gates
    exe = info.get("CFBundleExecutable", "")
    exe_path = contents + ("MacOS/" if kind == "mac" else "") + exe
    min_key = "LSMinimumSystemVersion" if kind == "mac" else "MinimumOSVersion"
    problems = []
    if not info.get("CFBundleIdentifier"):
        problems.append("CFBundleIdentifier missing")
    if not exe or exe_path not in names:
        problems.append(f"executable {exe_path!r} not in bundle")
    if not info.get(min_key):
        problems.append(f"{min_key} missing")
    if kind in PLIST_PLATFORMS and info.get("CFBundleSupportedPlatforms") != PLIST_PLATFORMS[kind]:
        problems.append(f"CFBundleSupportedPlatforms={info.get('CFBundleSupportedPlatforms')}")
    if kind == "mac" and info.get("CFBundlePackageType") != "APPL":
        problems.append("CFBundlePackageType != APPL")
    gates["plist"] = gate(not problems, "; ".join(problems) or
                          f"{info.get('CFBundleIdentifier')} exe={exe} {min_key}={info.get(min_key)}",
                          f"bundle id, executable, {min_key}" + (f", platforms {PLIST_PLATFORMS[kind]}" if kind in PLIST_PLATFORMS else ""))
    if problems:
        return gates

    data = z.read(exe_path)
    try:
        magic, cpu, ftype, cmds = load_commands(data)
    except struct.error as e:
        gates["macho"] = gate(False, f"truncated Mach-O: {e}", "thin arm64 MH_EXECUTE")
        return gates
    build = [c for c in cmds if c[0] == LC_BUILD_VERSION]
    plat = minos = None
    if build:
        plat, minos = struct.unpack_from("<2I", data, build[0][1] + 8)
    measured = (f"magic={magic:#x} cpu={cpu:#x} filetype={ftype} "
                f"platform={PLATFORM_NAME.get(plat, plat)} minos={version(minos) if minos is not None else None}")
    ok = (magic == MH_MAGIC_64 and cpu == CPU_ARM64 and ftype == MH_EXECUTE and plat == PLATFORM[kind]
          and minos is not None and norm(version(minos)) == norm(info[min_key]))
    gates["macho"] = gate(ok, measured, f"arm64 MH_EXECUTE, platform={PLATFORM_NAME[PLATFORM[kind]]}, minos={info[min_key]}")

    sig_ok, detail, _adhoc = check_signature(data, cmds, plist_bytes)
    if sig_ok is None:
        sig_ok = kind == "ios"
    gates["signature"] = gate(sig_ok, detail, "every code page hash matches" + (" (unsigned allowed)" if kind == "ios" else ""))
    return gates


def main():
    args = sys.argv[1:]
    out = None
    if "--json" in args:
        i = args.index("--json")
        out = args[i + 1]
        del args[i:i + 2]
    if len(args) != 2 or args[1] not in PLATFORM:
        sys.exit(__doc__)
    path, kind = args
    gates = judge(path, kind)
    for name in ("layout", "plist", "macho", "signature"):
        gates.setdefault(name, gate(False, "not reached", "earlier gate must pass"))
    verdict = {
        "verdict": "PASS" if all(g["pass"] for g in gates.values()) else "FAIL",
        "kind": kind,
        "artifact_sha256": hashlib.sha256(open(path, "rb").read()).hexdigest() if path and _exists(path) else None,
        "gates": gates,
    }
    text = json.dumps(verdict, indent=1, sort_keys=True)
    if out:
        with open(out, "w") as f:
            f.write(text + "\n")
    print(text)
    sys.exit(0 if verdict["verdict"] == "PASS" else 1)


def _exists(path):
    try:
        with open(path, "rb"):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    main()
