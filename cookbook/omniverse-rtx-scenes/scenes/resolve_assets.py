"""resolve_assets.py — walk and localise the transitive asset closure of a
dataset USD file.

The Warehouse-01 assemblies (Props/assembly/*.usd) are pure composition
layers: they payload files from Props/general/ and Props/modular/ by
relative path.  Rendering one offline therefore needs its whole closure, so
this module walks that closure with UsdUtils.ComputeAllDependencies and
downloads every file from the dataset's official HuggingFace URL, verifying
each one's sha256.

Only stdlib + pxr are used.  Every fetch is retried (HF rate-limits parallel
requests with transient 404s) and downloads are resumed per-file so a rerun
is cheap.
"""
from __future__ import annotations

import hashlib
import json
import threading
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


# --------------------------------------------------------------------------
# URL / path helpers
# --------------------------------------------------------------------------
def dataset_rel(asset_path: str, anchor: Path | None = None) -> str:
    """Normalise a USD asset path to a dataset-relative path.

    ComputeAllDependencies *resolves* each asset path before reporting it,
    so a `@../../general/X/X.usd@` reference from
    `Props/assembly/Asm/Asm.usd` comes back as an absolute filesystem path
    rooted at whatever directory that layer was opened from
    (`<cache>/Props/general/X/X.usd`).  Anchor stripping (dropping everything
    up to and including a leading `Props/`) recovers the dataset-relative
    path.  Passing `anchor=<cache>` makes the strip exact.
    """
    p = str(asset_path).replace("\\", "/")
    if p.startswith("@"):
        p = p[1:]
    if anchor is not None:
        a = str(anchor).replace("\\", "/").rstrip("/") + "/"
        if p.startswith(a):
            return p[len(a):].lstrip("/")
    idx = p.find("Props/")
    if idx >= 0:
        return p[idx:]
    while p.startswith("/"):
        p = p[1:]
    first, _, _ = p.partition("/")
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

    with ThreadPoolExecutor(max_workers=max(1, 8)) as ex:
        list(ex.map(one, enumerate(rels)))
    return [p for p in out if p is not None]


# --------------------------------------------------------------------------
# Closure walking
# --------------------------------------------------------------------------
def _deps_of(usd_path: Path, cache: Path) -> list[str]:
    """Dataset-relative asset paths referenced by usd_path (unresolved ones)."""
    from pxr import UsdUtils

    _, _, unresolved = UsdUtils.ComputeAllDependencies(str(usd_path))
    out = []
    for u in unresolved:
        u = str(u)
        if not (u.endswith(".usd") or u.endswith(".usda")
                or u.endswith(".usdc")):
            continue
        rel = dataset_rel(u, anchor=cache)
        if rel:
            out.append(rel)
    return out


def _asset_inputs_of(usd_path: Path, cache: Path) -> list[str]:
    """Non-USD assets (textures, MDL) a layer references by relative path.

    ComputeAllDependencies only *reports* an asset as unresolved when it
    cannot be located at all, so files that sit next to the layer (the
    common SimReady layout: `<asset>/materials/textures/*.png`) never show
    up there.  Read the shader inputs directly to catch them; UDIM
    placeholders are expanded to the tiles the dataset actually ships.
    """
    from pxr import Sdf, Usd, UsdShade

    out: list[str] = []
    try:
        st = Usd.Stage.Open(str(usd_path), load=Usd.Stage.LoadAll)
    except Exception:  # noqa: BLE001
        return out
    rel_layer = dataset_rel(str(usd_path), anchor=cache)
    layer_dir = rel_layer.rsplit("/", 1)[0] if "/" in rel_layer else ""
    for prim in st.Traverse(Usd.TraverseInstanceProxies()):
        for name in ("outputs:mdl:surface", "outputs:surface"):
            attr = prim.GetAttribute(name)
            if not attr:
                continue
            for path in attr.GetConnections():
                sp = st.GetPrimAtPath(path.GetPrimPath())
                if not sp:
                    continue
                sa = sp.GetAttribute("info:mdl:sourceAsset")
                if sa and sa.Get():
                    add_rel(out, layer_dir, str(sa.Get()))
                for inp in UsdShade.Shader(sp).GetInputs():
                    v = inp.Get()
                    if isinstance(v, Sdf.AssetPath):
                        add_rel(out, layer_dir, str(v.path))
    return out


UDIM_TILES = ("1001",)


def add_rel(out: list[str], layer_dir: str, path_str: str) -> None:
    """Append the dataset-relative form of one asset path.

    USD asset paths are written `@...@`; the delimiters are stripped here.
    A UDIM placeholder is expanded to the tiles that exist in the dataset —
    the SimReady packs author `<UDIM>` but ship only `1001..1003`, and the
    rendered geometry uses tile 1001, so pulling just that keeps the bundle
    small (the caller rewrites the remaining `<UDIM>` refs to 1001 anyway).
    """
    if not path_str:
        return
    s = path_str.strip()
    if s.startswith("@") and s.endswith("@") and len(s) > 1:
        s = s[1:-1]
    if not s or s.startswith("<"):
        return
    for tile in UDIM_TILES:
        expanded = s.replace("<UDIM>", tile)
        base = expanded.lstrip("./")
        rel = f"{layer_dir}/{base}" if layer_dir else base
        parts = []
        for seg in rel.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                if parts:
                    parts.pop()
                continue
            parts.append(seg)
        out.append("/".join(parts))


def closure(entry_rel: str, cache: Path,
            shas: dict[str, str] | None = None,
            max_depth: int = 8) -> dict[str, dict]:
    """Download the transitive closure of a dataset file.

    Returns {dataset_rel_path: {"bytes": n, "sha256": s}} for every file
    fetched, including the entry itself, plus a "_missing" key holding the
    paths that 404 in the public dataset (a few assemblies reference assets
    NVIDIA did not publish) — the caller decides whether that is fatal.
    """
    shas = shas or {}
    entry = entry_rel.lstrip("/")
    seen: dict[str, dict] = {}
    missing: set[str] = set()
    frontier = [entry]
    seen[entry] = {}

    for _ in range(max_depth):
        nxt: list[str] = []
        # fetch the frontier's USD deps first, then each layer's own assets
        for rel in frontier:
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
            if rel.endswith((".usd", ".usda", ".usdc")):
                for dep in list(_deps_of(p, cache)) + \
                        _asset_inputs_of(p, cache):
                    if dep not in seen:
                        seen[dep] = {}
                        nxt.append(dep)
        frontier = nxt
        if not frontier:
            break

    # everything still unseen was either enqueued or missing; fetch once more
    pending = [r for r, v in seen.items() if "bytes" not in v and r != "_missing"]
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
