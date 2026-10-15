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
| [gpu-kernel](gpu-kernel/README.md) | Grade a Triton softmax kernel on a 1 GiB GPU slice: correctness on 10 cases, 11/11 mutants caught, lease destroyed; CPU check mode included. |
| [spice-filter](spice-filter/README.md) | Design a 4th-order active low-pass in ngspice from E24/E12 parts and grade it against a ripple/stopband mask, a closed-form cross-check and Monte-Carlo tolerance; 9/9 mutants caught, independently reproduced. |
| [fea-calculix](fea-calculix/README.md) | Design the lightest steel cantilever and grade it with CalculiX + gmsh: stress and deflection limits, mesh convergence and an Euler-Bernoulli cross-check; 9/9 mutants caught, independently reproduced. |
| [plc-st](plc-st/README.md) | Compile an IEC 61131-3 Structured Text tank controller with MATIEC and grade it against a simulated plant in 8 scenarios (overflow, dry run, E-stop, recovery, random faults); 6/6 mutants caught, independently reproduced. |
| [firmware-qemu](firmware-qemu/README.md) | Build bare-metal Cortex-M3 firmware (UART shell, ring buffer, CRC-32) and grade it in QEMU over a real UART session: 8 gates incl. a zlib CRC oracle; 14/14 mutants caught, independently reproduced. |
| [img2threejs-showcase](img2threejs-showcase/README.md) | Build the img2threejs procedural Three.js gallery in parallel 4 vCPU / 16 GB sandboxes and render all 32 demos headless: 29 fully rendered on CPU-only WebGL, every verdict checked against positive/negative controls and by eye. |

The first three prompts passed review as demo videos. They have not been
re-run from this repo, so treat them as starting points, not guarantees.
The small-GPU entry includes an executable smoke check with explicit cleanup.
