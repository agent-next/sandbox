#!/usr/bin/env python3
"""size_plan.py — size the proposed scene asset set without building anything.

Reads the HuggingFace blob listing (exact sizes + sha256 of every file in the
dataset) and the transitive closure of each candidate assembly, then reports
the union.  Used to keep the shipped bundle inside SPEC.md's size budget.

  python3 size_plan.py --closure <assembly relpath> [...]
  python3 size_plan.py --catalog [regex]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

CATALOG_URL = ("https://huggingface.co/api/datasets/nvidia/"
               "PhysicalAI-SimReady-Warehouse-01?blobs=true")


def catalog(refresh: bool = False) -> dict:
    """{asset_dir_name: {"files": n, "bytes": n}} for every Props asset."""
    p = Path("/tmp/wh01_cat.json")
    if p.exists() and not refresh:
        return json.load(open(p))
    req = urllib.request.Request(CATALOG_URL,
                                 headers={"User-Agent": "agent-next-sbx/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        meta = json.load(r)
    cat: dict[str, dict] = {}
    for s in meta["siblings"]:
        parts = s["rfilename"].split("/")
        if len(parts) < 3 or parts[0] != "Props" or parts[2].startswith("."):
            continue
        c = cat.setdefault(parts[2], {"files": 0, "bytes": 0})
        c["files"] += 1
        c["bytes"] += s.get("size", 0)
    p.write_text(json.dumps(cat, indent=1))
    return cat


def closures(entries: list[str], cache: Path) -> dict:
    """Closure of each entry plus the union, in MB."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import resolve_assets as ra  # noqa: PLC0415 — owns the walk
    union: dict[str, dict] = {}
    out = []
    for e in entries:
        try:
            c = ra.closure(e, cache)
        except Exception as ex:  # noqa: BLE001
            out.append({"entry": e, "error": f"{type(ex).__name__}: {ex}"})
            continue
        miss = c.pop("_missing", {}).get("paths", [])
        for k, v in c.items():
            union.setdefault(k, v)
        out.append({
            "entry": e,
            "own_mb": round(sum(v.get("bytes", 0) for v in c.values()) / 1e6, 2),
            "files": len(c),
            "missing": miss,
        })
    return {"entries": out,
            "union_files": len(union),
            "union_mb": round(sum(v.get("bytes", 0) for v in union.values()) / 1e6, 2)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, default=Path("/tmp/hfcache"))
    ap.add_argument("--closure", nargs="+", default=[],
                    help="dataset-relative .usd paths")
    ap.add_argument("--catalog", nargs="?", const="", default=None,
                    help="list asset dirs, optionally filtered by regex")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    if a.catalog is not None:
        import re  # noqa: PLC0415
        cat = catalog(a.refresh)
        rx = re.compile(a.catalog) if a.catalog else None
        rows = sorted((v["bytes"] / 1e6, v["files"], n)
                      for n, v in cat.items() if not rx or rx.search(n))
        print(f"{len(rows)} asset dirs, "
              f"{sum(r[0] for r in rows) / 1e3:.2f} GB total")
        for b, f, n in rows[:40]:
            print(f"  {b:8.2f} MB {f:5d}f  {n}")
    if a.closure:
        print(json.dumps(closures(a.closure, a.cache), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
