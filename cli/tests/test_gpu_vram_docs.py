"""GPU docs must say what a vram_gb slice actually holds (#81).

Measured on a 1 GiB gpu-lease-v06 lease (2026-10-15): the vGPU baseline
(~756 MiB at rest) and each CUDA process's context (~0.3 GiB) sit inside
the requested slice, so only ~0.3-0.6 GiB is allocatable. Every doc that
tells a user to request a `vram_gb` slice must also state that rule.
"""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SKILL = REPO / "plugins/sandbox/skills/sandbox/SKILL.md"
SLICE_DOCS = [
    SKILL,
    REPO / "cookbook/small-gpu/README.md",
    REPO / "cookbook/gpu-kernel/README.md",
    REPO / "cookbook/gpu-sim-sweep/README.md",
    REPO / "cookbook/sim-engine-arena/README.md",
]

# Measured rule of thumb (1 GiB lease -> ~0.6 GiB free to the first process, ~0.3 GiB to a second):
# `vram_gb − ~0.4 GiB` for the first CUDA process, ~0.3 GiB less per additional one.
RULE = re.compile(r"vram_gb\s*[−-]\s*~0\.4\s*GiB`\s+for the first CUDA\s+process\s+and\s+~0\.3\s*GiB\s+less\s+per\s+additional")


@pytest.mark.parametrize("doc", SLICE_DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_slice_docs_state_the_allocatable_rule(doc):
    text = doc.read_text(encoding="utf-8")
    assert RULE.search(text), (
        f"must state the effective-allocatable rule for a vram_gb slice: "
        "`vram_gb − ~0.4 GiB` for the first CUDA process and ~0.3 GiB less per "
        "additional CUDA process (issue #81)"
    )


def test_skill_states_the_measured_baseline():
    text = SKILL.read_text(encoding="utf-8")
    assert "756 MiB" in text, (
        "SKILL.md must record the measured at-rest vGPU baseline (756 MiB) "
        "that sits inside a vram_gb slice (issue #81)"
    )


def test_skill_says_capacity_refusal_while_resuming_is_retried():
    text = SKILL.read_text(encoding="utf-8")
    window = re.search(r"GPU plane at capacity.{0,240}", text, re.S)
    assert window and "retry" in window.group(), (
        "SKILL.md must tell agents that an HTTP 503 'GPU plane at capacity' "
        "refusal while a suspended lease takes its seat again is retryable "
        "after the suggested delay (issue #81)"
    )
