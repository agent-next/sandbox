# Omniverse RTX scenes

## Goal
Flagship media + cookbook demo: an agent assembles NVIDIA official SimReady assets into photoreal scenes and renders with ovrtx on the agent-next GPU sandbox.

## Non-goals
No toy primitives; no matplotlib; no committed large assets.

## Asset sources
Omniverse downloadable packs, HuggingFace nvidia/PhysicalAI-SimReady-Warehouse-01, Isaac Sim 5.1 S3 root, NVIDIA-Omniverse/PhysicalAI-SimReady-Materials.

## Acceptance oracle
Silhouette vs projected bbox >= 0.9; no missing textures; temporal consistency; PhysX energy checks; >= 5 mutants killed.

## Status
BLOCKED 2026-10-15: gpu-omniverse template PR agent-infra#987 is open pending droid-opus review; accel.template "omniverse" is not yet registered on the live GPU lease. Stage-1/2 workers (fleet2 task "flagship-scenes") have not landed committed output on any branch. Branch sbx/omniverse-rtx-scenes-20261015 initialized as baseline only.
