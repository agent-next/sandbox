"""resolve_assets.py — walk and localise the transitive asset closure of a
dataset USD file.

The Warehouse-01 assemblies (Props/assembly/*.usd) are pure composition
layers: they payload files from Props/general/ and Props/modular/ by
relative path.  Rendering one offline therefore needs its whole closure, so
this module walks that closure and downloads every file it references from
the dataset's official HuggingFace URL, verifying each one's sha256.

Only stdlib + pxr are used.  Every fetch is retried (HF rate-limits parallel
requests with transient 404s) and downloads are resumed per-file so a rerun
is cheap.

The walk uses `UsdUtils.ComputeAllDependencies`, whose three returns cover
everything a layer needs:
  * layers     — every USD layer reached (transitively, so depth 1 suffices)
  * assets     — every non-USD file it resolved (textures, MDL)
  * unresolved — the paths it could not locate (bare `@OmniPBR.mdl@`, and a
                 few assets NVIDIA never published in the dataset)
A warm cache makes a path "resolved" rather than "unresolved", so the walk
must read the union of layers + assets, not just the unresolved list.
"""
from __future__ import annotations

import hashlib
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
HF_ROOT = ("https://huggingface.co/datasets/nvidia/"
           "PhysicalAI-SimReady-Warehouse-01/resolve/main/")
USER_AGENT = "agent-next-sbx/1.0 (omniverse-rtx-scenes build)"
RETRIES = 5
BACKOFF = 1.5
TOP_LEVEL = {"Props", "SubLayers", "Environments", "Scenes", "images"}
# extensions that are a file to localise rather than a USD layer
NON_USD = (".png", ".jpg", ".jpeg", ".tga", ".tif", ".tiff", ".exr",
           ".hdr", ".mdl", ".usdz", ".mtlx", ".mb")
USD_EXT = (".usd", ".usda", ".usdc")


# --------------------------------------------------------------------------
# URL / path helpers
# --------------------------------------------------------------------------
def dataset_rel(asset_path: str, anchor: Path | None = None) -> str:
    """Normalise a USD asset path to a dataset-relative path.

    ComputeAllDependencies *resolves* each asset path before reporting it,
    so a `@../../general/X/X.usd@` reference from
    `Props/assembly/Asm/Asm.usd` comes back as an absolute filesystem path
    rooted at whatever directory that layer was opened from.  Anchoring the
    strip at the cache root recovers the dataset-relative path.
    """
    p = str(asset_path).replace("\\", "/")
    if p.startswith("@"):
        p = p[1:]
    if anchor is not None:
        a = str(anchor).replace("\\", "/").rstrip("/") + "/"
        if p.startswith(a):
            p = p[len(a):].lstrip("/")
    # Some assemblies reference props dataset-root-relative
    # (`@Props/general/X/X.usd@`) instead of `@../../general/...@`, so
    # ComputeAllDependencies resolves them to
    # `Props/assembly/Asm/Props/general/X/X.usd`.  Only assembly layers can
    # produce that double-`Props/` shape, so truncate at the LAST `Props/`
    # there.  Other trees legitimately contain a second `Props/` in their
    # real path (Props/modular/Modular_Warehouse/Props/Source/...) and must
    # be kept whole.
    if p.startswith("Props/assembly/") and p.count("Props/") > 1:
        return p[p.rfind("Props/"):]
    idx = p.find("Props/")
    if idx >= 0:
        return p[idx:]
    while p.startswith("/"):
        p = p[1:]
    first, _, _ = p.partition("/")
    if first in TOP_LEVEL:
        return p
    if first in ("assembly", "general", "materials", "modular", "skies"):
        return "Props/" + p
    return p


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------
def fetch_to_cache(rel: str, cache: Path, expected_sha256: str | None = None,
                   force: bool = False) -> Path:
    """Download rel into cache/rel, retrying; returns the local path."""
    dest = cache / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        if expected_sha256 is None or sha256_file(dest) == expected_sha256:
            return dest
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(HF_ROOT + rel,
                                         headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=300) as r, \
                    open(part, "wb") as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
            part.replace(dest)
            if expected_sha256 is not None:
                got = sha256_file(dest)
                if got != expected_sha256:
                    raise RuntimeError(
                        f"sha256 mismatch for {rel}: want {expected_sha256} "
                        f"got {got}")
            return dest
        except Exception as e:  # noqa: BLE001 — retried below
            if isinstance(e, urllib.error.HTTPError) and e.code == 404:
                raise  # genuinely absent from the dataset: no point retrying
            if attempt == RETRIES:
                raise
            time.sleep(BACKOFF * attempt)
    return dest


def fetch_many(rels: list[str], cache: Path,
               shas: dict[str, str] | None = None) -> list[Path]:
    """Parallel fetch with a bounded pool; order preserved."""
    shas = shas or {}
    out: list[Path | None] = [None] * len(rels)

    def one(i_rel):
        i, rel = i_rel
        out[i] = fetch_to_cache(rel, cache, shas.get(rel))

    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, enumerate(rels)))
    return [p for p in out if p is not None]


# --------------------------------------------------------------------------
# Closure walking
# --------------------------------------------------------------------------
def closure(entry_rel: str, cache: Path,
            shas: dict[str, str] | None = None) -> dict[str, dict]:
    """Download the transitive closure of a dataset file.

    Returns {dataset_rel_path: {"bytes": n, "sha256": s}} for every file
    fetched, plus a "_missing" key listing paths that 404 in the public
    dataset — expected for the bare `@OmniPBR.mdl@` refs (the build supplies
    the MDL chain) and for the handful of assets NVIDIA never published.
    """
    from pxr import UsdUtils

    shas = shas or {}
    entry = entry_rel.lstrip("/")
    seen: dict[str, dict] = {}
    missing: set[str] = set()
    frontier = [entry]
    seen[entry] = {}

    for _ in range(4):
        nxt: list[str] = []
        for rel in list(frontier):
            if rel in missing:
                continue
            try:
                p = fetch_to_cache(rel, cache, shas.get(rel))
            except Exception:  # noqa: BLE001 — absence is recorded, not fatal
                missing.add(rel)
                continue
            if "bytes" not in seen.get(rel, {}):
                seen[rel] = {"bytes": p.stat().st_size,
                             "sha256": sha256_file(p)}
            try:
                layers, assets, unresolved = UsdUtils.\
                    ComputeAllDependencies(str(p))
            except Exception:  # noqa: BLE001
                continue
            for layer in list(layers or []):
                dep = dataset_rel(layer.identifier, anchor=cache)
                if dep and dep.endswith(USD_EXT) and dep not in seen:
                    seen[dep] = {}
                    nxt.append(dep)
            # assets + unresolved are the non-USD deps.  ComputeAllDependencies
            # reports a UDIM tile even when it exists locally, so the paths
            # already in `seen` are skipped by the membership test above.
            for u in list(assets or []) + list(unresolved or []):
                dep = dataset_rel(str(u), anchor=cache)
                if not dep or dep in seen:
                    continue
                # A <UDIM> placeholder expands to the concrete tiles that
                # exist in the dataset (tile 1001 is the only one the build
                # pins); keep the placeholder out of the lock.
                if "<UDIM>" in dep:
                    dep = dep.replace("<UDIM>", "1001")
                first = dep.split("/", 1)[0]
                # A *bare* reference (`@OmniPBR.mdl@`) carries no directory
                # information, so dataset_rel cannot place it; it resolves
                # relative to the layer that referenced it.  A resolved path
                # always keeps a dataset top-level prefix (Props/, SubLayers/,
                # …), so anything without one is bare and needs re-anchoring.
                if first not in TOP_LEVEL:
                    # a bare @OmniPBR.mdl@ etc.: re-anchor at the layer that
                    # referenced it so it lands next to that layer.
                    anchor_dir = dataset_rel(str(p), anchor=cache)
                    folder = anchor_dir.rsplit("/", 1)[0] if \
                        "/" in anchor_dir else ""
                    dep = f"{folder}/{dep}" if folder else dep
                if dep in seen:
                    continue
                seen[dep] = {}
                nxt.append(dep)
        frontier = nxt
        if not frontier:
            break

    pending = [r for r, v in seen.items()
               if "bytes" not in v and r != "_missing"]
    for rel in pending:
        try:
            p = fetch_to_cache(rel, cache, shas.get(rel))
            seen[rel] = {"bytes": p.stat().st_size,
                         "sha256": sha256_file(p)}
        except Exception:  # noqa: BLE001
            missing.add(rel)
            seen.pop(rel, None)

    seen["_missing"] = {"paths": sorted(missing)}
    return seen
