"""Inside a GPU lease: render the good scene at doubling spp for the convergence video.

Every frame is a real MuTracer render with the judge's own driver; RMSE is measured
against a 1024-spp reference of the same scene with a different sample stream.
"""
import json
from pathlib import Path
import sys

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "judge"))
from driver import Renderer  # noqa: E402
from grade import save_outputs  # noqa: E402

LEVELS = [1, 2, 4, 8, 16, 32, 64, 128, 256]
REFERENCE_SPP = 1024


def main(out, seed):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    scene = json.loads((HERE.parent / "examples/good/scene.json").read_text())
    with Renderer("gpu") as renderer:
        reference = renderer.render(scene, REFERENCE_SPP, seed + 100)
        rows = []
        for spp in LEVELS:
            image = renderer.render(scene, spp, seed)
            rmse = float(np.sqrt(np.mean((image[..., :3].astype(np.float64)
                                          - reference[..., :3]) ** 2)))
            save_outputs(out / f"frame-{spp:04d}.npy", image)
            (out / f"frame-{spp:04d}.npy").unlink()
            rows.append({"spp": spp, "rmse": rmse, "png": f"frame-{spp:04d}.png"})
        info = renderer.info
    (out / "frames.json").write_text(json.dumps({
        "seed": seed, "reference_spp": REFERENCE_SPP, "levels": rows,
        "adapter_info": info.get("adapter_info"), "backend": info.get("backend"),
    }, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
