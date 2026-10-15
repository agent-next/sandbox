"""Asset manifest helpers for the omniverse-rtx-scenes build.

Each scene is assembled from official NVIDIA SimReady assets.  Every file
that ends up in a scene's localised bundle is fetched here from its official
source URL, sha256-verified against the lock, and recorded in
assets.lock.json (url, sha256, bytes, source, licence line).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

# Official source roots ------------------------------------------------
HF_WAREHOUSE = ("https://huggingface.co/datasets/nvidia/"
                "PhysicalAI-SimReady-Warehouse-01/resolve/main/")
HF_ASSETS = "https://huggingface.co/datasets/nvidia/simready-assets/resolve/main/"
S3_ISAAC = "http://omniverse-content-production.s3.us-west-2.amazonaws.com/"

# Licence lines for each source (verbatim from the source's licence text / page).
LICENCES = {
    "hf-warehouse-01": "CC-BY-4.0 (NVIDIA Physical AI SimReady Warehouse OpenUDS "
                       "Dataset, https://huggingface.co/datasets/nvidia/"
                       "PhysicalAI-SimReady-Warehouse-01, version 1.1.0, "
                       "https://choosealicense.com/licenses/cc-by-4.0/)",
    "hf-assets": "NVIDIA SimReady Assets (simready-assets) dataset, CC0 / "
                 "per-file licence; OmniPBR.mdl is BSD-3-Clause (c) 2022 "
                 "NVIDIA Corporation, SPDX BSD-3-Clause",
    "s3-isaac-4.1": "NVIDIA Isaac Sim 4.1 asset library, NVIDIA Omniverse "
                    "Content Production S3 (omniverse-content-production), "
                    "CC-BY-4.0 / NVIDIA sample content licence",
}

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: Path, expected_sha256: str | None = None) -> str:
    """Download url to dest, verifying sha256. Returns the sha256."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and expected_sha256 is not None:
        if sha256_file(dest) == expected_sha256:
            return expected_sha256
    req = urllib.request.Request(url, headers={"User-Agent": "agent-next-sbx/1.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    if expected_sha256 is not None:
        got = sha256_file(dest)
        if got != expected_sha256:
            raise RuntimeError(f"sha256 mismatch for {url}:\n  want {expected_sha256}\n  got  {got}")
        return got
    return sha256_file(dest)
