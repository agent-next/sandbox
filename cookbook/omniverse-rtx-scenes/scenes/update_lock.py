#!/usr/bin/env python3
"""update_lock.py — extend assets.lock.json with the stage-1b asset set.

Merges the transitive closure of each Warehouse-01 entry (via
resolve_assets.closure, which records every file's sha256 as it downloads)
plus the Isaac Sim 5.1 robot files (Leatherback, UR10) into the lock.  Each
entry keeps the same shape as the stage-1 lock: {url, sha256, bytes, license}.

Idempotent: existing entries are verified, not re-fetched.

  python3 update_lock.py [--entries a.txt] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resolve_assets as ra  # noqa: E402
from asset_types import LICENCES  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOCK = ROOT / "assets.lock.json"
CACHE = ROOT / "assets"

S3 = "http://omniverse-content-production.s3.us-west-2.amazonaws.com/"
ISAAC_51 = "Assets/Isaac/5.1/Isaac/Robots/"

# Warehouse-01 entries whose full closure ships with the scenes.
HF_ENTRIES = [
    # racks (each composition = a filled rack: shelves + boxes + pallets)
    "Props/assembly/sm_rackcomposition_s57_01/sm_rackcomposition_s57_01.usd",
    "Props/assembly/sm_rackcomposition_s58_01/sm_rackcomposition_s58_01.usd",
    "Props/assembly/sm_rackcomposition_s60_01/sm_rackcomposition_s60_01.usd",
    "Props/assembly/sm_rackcomposition_s63_01/sm_rackcomposition_s63_01.usd",
    # pallet stacks (crates / boxes on pallets)
    "Props/assembly/sm_palletcomposition_a100_01/sm_palletcomposition_a100_01.usd",
    "Props/assembly/sm_palletcomposition_a101_01/sm_palletcomposition_a101_01.usd",
    "Props/assembly/sm_palletcomposition_a143_01/sm_palletcomposition_a143_01.usd",
    "Props/assembly/sm_palletcomposition_a144_01/sm_palletcomposition_a144_01.usd",
    # floor prop categories: forklift, signage, safety, drums
    "Props/general/SM_Forklift_A01_Orange_01/SM_Forklift_A01_Orange_01.usd",
    "Props/general/SM_WarningSign_A04_01/SM_WarningSign_A04_01.usd",
    "Props/general/SM_DeluxeSafetyTape4M10CM_B02_Yellow_01/"
    "SM_DeluxeSafetyTape4M10CM_B02_Yellow_01.usd",
    "Props/general/SM_SteelDrum_A01_01/SM_SteelDrum_A01_01.usd",
    "Props/general/SM_SolidTopRackablePallet_A02_BlueA_01/"
    "SM_SolidTopRackablePallet_A02_BlueA_01.usd",
    "Props/general/SM_BlockPallet_A01_WoodNewA_01/"
    "SM_BlockPallet_A01_WoodNewA_01.usd",
]

# Isaac Sim 5.1 robots: closure of each root .usd (downloaded from the S3
# root, deps resolved relative to it).
ISAAC_ENTRIES = {
    "leatherback": ISAAC_51 + "NVIDIA/Leatherback/leatherback.usd",
    "ur10": ISAAC_51 + "UniversalRobots/ur10/ur10.usd",
}


def hf_lock_entries(cache: Path) -> dict:
    out = {}
    for e in HF_ENTRIES:
        c = ra.closure(e, cache)
        miss = c.pop("_missing", {}).get("paths", [])
        for rel, v in c.items():
            if "bytes" not in v:
                continue
            out[rel] = {
                "url": ra.HF_ROOT + rel,
                "sha256": v["sha256"],
                "bytes": v["bytes"],
                "license": LICENCES["hf-warehouse-01"],
            }
        for m in miss:
            if m.endswith(".mdl"):
                continue  # supplied by the build's MDL chain
            print(f"  ! {e}: absent from dataset: {m}", file=sys.stderr)
    return out


def isaac_lock_entries(cache: Path, s3_cache: Path) -> dict:
    """Download + hash the Isaac 5.1 closure of each robot root."""
    import hashlib  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    from pxr import UsdUtils  # noqa: PLC0415

    def fetch(key: str) -> Path:
        dest = s3_cache / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return dest
        with urllib.request.urlopen(S3 + key, timeout=300) as r, \
                open(dest, "wb") as f:
            for chunk in iter(lambda: r.read(1 << 20), b""):
                f.write(chunk)
        return dest

    def to_key(s, anchor=s3_cache):
        p = str(s).replace("\\", "/")
        a = str(anchor).rstrip("/") + "/"
        if p.startswith(a):
            p = p[len(a):]
        return p if p.startswith("Assets/Isaac/5.1/") else None

    out = {}
    for name, rootkey in ISAAC_ENTRIES.items():
        fetch(rootkey)
        seen = {rootkey}
        frontier = [rootkey]
        for _ in range(8):
            nxt = []
            for key in frontier:
                layers, assets, unres = UsdUtils.ComputeAllDependencies(
                    str(s3_cache / key))
                for u in list(layers) + list(assets) + list(unres):
                    k = to_key(u.identifier if hasattr(u, "identifier") else u)
                    if not k or k in seen:
                        continue
                    seen.add(k)
                    nxt.append(k)
            for k in nxt:
                try:
                    fetch(k)
                except Exception as e:  # noqa: BLE001
                    print(f"  ! isaac: absent {k} ({e})", file=sys.stderr)
            frontier = nxt
            if not frontier:
                break
        for k in sorted(seen):
            p = s3_cache / k
            if not p.exists():
                continue
            h = hashlib.sha256()
            with open(p, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            # key under the lock mirrors the stage-1 convention: robot-local
            # path prefixed by the robot's name (ur10/..., leatherback/...)
            rel = k[len(ISAAC_51):]
            out[f"{name}/{rel}"] = {
                "url": S3 + k,
                "sha256": h.hexdigest(),
                "bytes": p.stat().st_size,
                "license": LICENCES["s3-isaac-4.1"].replace(
                    "Isaac Sim 4.1", "Isaac Sim 5.1"),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cache", type=Path, default=None,
                    help="override the download cache (default: <demo>/assets)")
    a = ap.parse_args()

    lock = json.loads(LOCK.read_text())
    cache = a.cache if a.cache else CACHE
    s3_cache = Path("/tmp/isaac51")
    new_hf = hf_lock_entries(cache)
    new_isaac = isaac_lock_entries(cache, s3_cache)

    added, kept, changed = 0, 0, 0
    for k, v in {**new_hf, **new_isaac}.items():
        if k not in lock:
            added += 1
        elif lock[k]["sha256"] == v["sha256"]:
            kept += 1
            continue
        else:
            changed += 1
        lock[k] = v
    total_mb = sum(v.get("bytes", 0) for v in lock.values()) / 1e6
    print(f"lock: +{added} added, {changed} changed, {kept} verified, "
          f"{len(lock)} entries, {total_mb:.2f} MB total")
    if not a.dry_run:
        LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
