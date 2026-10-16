"""Fetch the OSMesa closure MuJoCo needs to render headlessly.

MuJoCo's offscreen renderer needs a GL context. make_media.sh probes EGL
first and only falls back to this on a host with no GPU and no display.
There the choice of packages is not free: Ubuntu noble's libosmesa6 wants
GLIBC_2.38 and will not load on a Debian 12 / glibc 2.36 host, and mixing
distributions loads some libraries and then dies on others. So the whole
closure comes from one release: Debian bookworm, amd64.

The set of packages is not hand-picked. It is resolved the way the loader
resolves: start from the soname mujoco asks for (libOSMesa.so.8), read
the DT_NEEDED entries of every library as it lands, and stop wherever the
host already provides a soname - so the closure is exactly the missing
software-GL chain, never the host's own libc. Package names come from the
bookworm Contents index (path -> package) and download URLs from the
bookworm Packages index, both pinned to the frozen release; the resolved
list is written to <dest>/lib/CLOSURE.txt.

Libraries are unpacked flat into <dest>/lib (gitignored) and loaded with
MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa LD_LIBRARY_PATH=<dest>/lib.

Usage:
    python -I gl_tooling.py --dest media/.tools [--verify-only]
"""

import argparse
import gzip
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = "http://deb.debian.org/debian"
PACKAGES_INDEX = f"{BASE}/dists/bookworm/main/binary-amd64/Packages.gz"
CONTENTS_INDEX = f"{BASE}/dists/bookworm/main/Contents-amd64.gz"
ROOT_SONAME = "libOSMesa.so.8"          # what mujoco's osmesa backend loads

LIBDIRS = ("usr/lib/x86_64-linux-gnu", "usr/lib", "lib/x86_64-linux-gnu")


def log(msg: str) -> None:
    print(f"gl_tooling: {msg}", flush=True)


def get(url: str) -> bytes:
    log(f"GET {url.rsplit('/', 1)[-1]}")
    return urllib.request.urlopen(url, timeout=120).read()


def system_sonames() -> set[str]:
    """Every shared object the host already provides, straight from the
    directories the loader searches - ldconfig is not always on PATH in
    a container, and its cache says nothing the directories do not."""
    found: set[str] = set()
    for d in (Path("/lib/x86_64-linux-gnu"), Path("/usr/lib/x86_64-linux-gnu"),
              Path("/usr/lib"), Path("/lib")):
        if not d.is_dir():
            continue
        for item in d.iterdir():
            name = item.name
            if item.is_file() and ".so." in name:
                found.add(name)
            elif item.is_symlink() and ".so." in name:
                found.add(name)
    return found


def needed_sonames(path: Path) -> list[str]:
    out = subprocess.run(["objdump", "-p", str(path)],
                         capture_output=True, text=True).stdout
    return re.findall(r"^\s*NEEDED\s+(\S+)", out, re.M)


def parse_packages(raw: str) -> dict[str, str]:
    """package -> pool filename, from the Packages index."""
    mapping: dict[str, str] = {}
    for stanza in raw.split("\n\n"):
        name = filename = None
        for line in stanza.splitlines():
            if line.startswith("Package: "):
                name = line[len("Package: "):].strip()
            elif line.startswith("Filename: "):
                filename = line[len("Filename: "):].strip()
        if name and filename:
            mapping[name] = filename
    return mapping


def parse_contents(raw: str) -> dict[str, str]:
    """soname -> package, from the Contents index (path -> package)."""
    mapping: dict[str, str] = {}
    for line in raw.splitlines():
        match = re.match(r"^\S*/([^/\s]+)\s+(\S+)$", line)
        if match and ".so." in match.group(1):
            mapping.setdefault(match.group(1), match.group(2).split("/")[-1])
    return mapping


def install(filename: str, packages: dict[str, str], debs: Path, libdir: Path) -> None:
    deb = debs / filename.rsplit("/", 1)[-1]
    if not deb.exists() or deb.stat().st_size < 65536:
        urllib.request.urlretrieve(f"{BASE}/{filename}", deb)
        if deb.stat().st_size < 65536:
            raise RuntimeError(f"{filename} is {deb.stat().st_size} bytes, not a package")
    unpack = libdir / f".unpack-{deb.stem}"
    shutil.rmtree(unpack, ignore_errors=True)
    unpack.mkdir(parents=True)
    subprocess.run(["dpkg-deb", "-x", str(deb), str(unpack)], check=True)
    placed = 0
    for sub in LIBDIRS:
        d = unpack / sub
        if not d.is_dir():
            continue
        for item in d.iterdir():
            if ".so" in item.name and item.is_file() and not (libdir / item.name).exists():
                shutil.copy2(item, libdir / item.name)
                placed += 1
    shutil.rmtree(unpack, ignore_errors=True)
    log(f"{deb.name}: {placed} libs")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dest", required=True, type=Path,
                    help="write lib/ inside this directory (media/.tools)")
    ap.add_argument("--verify-only", action="store_true",
                    help="render one frame with the existing closure; download nothing")
    args = ap.parse_args()

    libdir = (args.dest / "lib").resolve()
    if args.verify_only:
        probe = ("import mujoco;"
                 "m=mujoco.MjModel.from_xml_string('<mujoco/>');"
                 "r=mujoco.Renderer(m,64,64);r.close()")
        env = {"MUJOCO_GL": "osmesa", "PYOPENGL_PLATFORM": "osmesa",
               "LD_LIBRARY_PATH": str(libdir), "PATH": "/usr/bin:/bin"}
        subprocess.run([sys.executable, "-I", "-c", probe], check=True, env=env)
        log("existing closure renders")
        return 0

    have = system_sonames()
    log(f"host already provides {len(have)} shared objects")
    packages = parse_packages(gzip.decompress(get(PACKAGES_INDEX)).decode())
    contents = parse_contents(gzip.decompress(get(CONTENTS_INDEX)).decode())
    log(f"index: {len(packages)} packages, {len(contents)} shared objects")

    debs = (args.dest / "debs")
    debs.mkdir(parents=True, exist_ok=True)
    libdir.mkdir(parents=True, exist_ok=True)

    queue = [ROOT_SONAME]
    resolved: list[str] = []
    seen: set[str] = set()
    while queue:
        soname = queue.pop(0)
        if soname in seen or soname in have:
            continue
        seen.add(soname)
        pkg = contents.get(soname)
        if pkg is None:
            raise RuntimeError(f"bookworm Contents has no {soname}; "
                               f"the host does not provide it either")
        filename = packages.get(pkg)
        if filename is None:
            raise RuntimeError(f"bookworm Packages has no {pkg} (for {soname})")
        resolved.append(filename)
        install(filename, packages, debs, libdir)
        queue.extend(needed_sonames(libdir / soname))

    shutil.rmtree(debs, ignore_errors=True)
    (libdir / "CLOSURE.txt").write_text(
        f"# resolved from {PACKAGES_INDEX} and {CONTENTS_INDEX}\n"
        f"# root soname: {ROOT_SONAME}\n"
        f"# {len(resolved)} packages, host-provided sonames skipped\n"
        + "".join(f"{f.rsplit('/', 1)[-1]}\n" for f in resolved))
    log(f"closure complete: {len(list(libdir.iterdir()))} files in {libdir}")
    log("use: MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa "
        f"LD_LIBRARY_PATH={libdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
