# Independent reproduction, 2026-10-14

**MATCH.** An agent from a different model family (OpenCode, `step-5-preview-free`)
followed only README.md and SPEC.md, then compared with RECEIPT.md.

- Source: fresh `git clone --depth 1 -b sbx/demo-render-pathtrace`, HEAD
  `a4effc75004c8ab44ebaeea5db0dd3bc9b6a66c7`, no files edited. The lease recorded
  the same judge, scene and runner SHA-256s as the receipt runs.
- Command, from `cookbook/render-pathtrace`: `python3 run.py --output <dir>`,
  run once, exit 0, final line `PASS: selftest and five physical gates on NVIDIA WebGPU`.
- Fresh GPU `browser` lease, 2 GiB slice, seed 17; adapter `nvidia` / `blackwell`,
  WebGPU; versions identical to `judge/VERSIONS.txt` in RECEIPT.md.
- Cleanup: `DELETE 200; GET 404`.

| item | RECEIPT.md | reproduction | result |
| --- | --- | --- | --- |
| G1 means, rho 0.18 / 0.5 / 0.8 | 0.17946 / 0.49849 / 0.79764 | 0.179464 / 0.498493 / 0.797643 | identical |
| G2 max channel, clay / coat / floor / metal / velvet | 0.617 / 0.305 / 0.621 / 0.942 / 0.347 | 0.617429 / 0.305026 / 0.621138 / 0.941999 / 0.346672 | identical |
| G3 slope | −0.48463 | −0.484631 | identical |
| G4 / final HDR SHA-256 | `b82318c7…55e4` | `b82318c76632e81d9e27cc5fabcc8907e101efa46a97edf8f1c752210d8355e4` | byte-identical |
| G5 median / clipped / floor noise | 0.61611 / 0.00486 / 0.02046 | 0.616107 / 0.004856 / 0.020464 | identical |
| self-test | 8/8 killed, wrong albedo rejected, verdict deterministic | same | identical |

The complete verdict JSON, with `timing` removed, is identical to receipt lease A,
and the downloaded `studio.npy` files hash the same in all three leases.

Only wall times differed, which SPEC.md allows:

| step | receipt A / B (s) | reproduction (s) |
| --- | --- | --- |
| upload, since start | 37.7 / 38.3 | 75.3 |
| self-test | 31.8 / 29.6 | 33.5 |
| grade | 6.2 / 5.8 | 6.8 |
| caller total | 100.2 / 124.4 | 272.7 |

The longer total comes from the files route (upload and the output download),
not from rendering.
