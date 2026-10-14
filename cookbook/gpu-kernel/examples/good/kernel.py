"""Fused row-wise softmax, one Triton kernel.

Row-wise softmax over the last dimension of a 2-D fp32 tensor, computed in
one fused kernel pass: load the row, subtract the row max (numerical
stability), exponentiate, sum, normalise, store. Adapted from the official
Triton "Fused Softmax" tutorial
https://triton-lang.org/main/getting-started/tutorials/02-fused-softmax.html
(Triton 3.8.0 docs; the tutorial code is MIT-licensed, Triton LICENSE,
(c) Philippe Tillet 2018-2020, OpenAI 2020-2022).

The public API is `softmax(x)`. `KERNEL`, `SIGNATURE` and `CONSTEXPRS` are
the offline device-compile probes the judge uses (see SPEC.md).
"""

import torch
import triton
import triton.language as tl

SIGNATURE = {"X": "*fp32", "Y": "*fp32", "n_cols": "i32", "BLOCK": "constexpr"}
CONSTEXPRS = {"BLOCK": 1024}


@triton.jit
def KERNEL(X, Y, n_cols, BLOCK: tl.constexpr):
    row = tl.program_id(0)
    cols = tl.arange(0, BLOCK)
    mask = cols < n_cols
    # masked lanes load -inf, so exp(x - x_max) is exactly 0 for them and
    # the denominator is unaffected; no separate where() is needed
    x = tl.load(X + row * n_cols + cols, mask=mask, other=float("-inf"))
    x_max = tl.max(x, axis=0)
    e = tl.exp(x - x_max)
    denom = tl.sum(e, axis=0)
    tl.store(Y + row * n_cols + cols, e / denom, mask=mask)


def softmax(x: torch.Tensor) -> torch.Tensor:
    """Row-wise softmax of `x` (2-D fp32, contiguous), as one kernel launch."""
    rows, n_cols = x.shape
    y = torch.empty_like(x)
    block = triton.next_power_of_2(n_cols)
    KERNEL[(rows,)](x, y, n_cols, BLOCK=block)
    return y
