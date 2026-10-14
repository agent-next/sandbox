# Cookbook

Each entry is a prompt for your agent (with the `sandbox` plugin installed)
and the command to run it. Entries are added only after they pass review.

| entry | prompt |
| --- | --- |
| [webgl-game-builder](webgl-game-builder/README.md) | Build a neon synthwave racing game and serve it from a sandbox. |
| [browser-agent](browser-agent/README.md) | Drive a real browser in a sandbox to find and compare items. |
| [gpu-sim-sweep](gpu-sim-sweep/README.md) | Time a robot simulation across many parallel worlds (CPU here; the video used a GPU). |
| [small-gpu](small-gpu/README.md) | Run a CUDA smoke check in a 1 GiB VRAM slice and destroy it. |
| [github-ci-runners](github-ci-runners/README.md) | Run GitHub Actions jobs in disposable sandboxes with Docker, from a warm pool. |
| [cfd-openfoam](cfd-openfoam/README.md) | Run OpenFOAM channel and cavity flows and grade them against the analytic profile and Ghia 1982; one command, independently reproduced. |

The first three prompts passed review as demo videos. They have not been
re-run from this repo, so treat them as starting points, not guarantees.
The small-GPU entry includes an executable smoke check with explicit cleanup.
