# examples/good — the known-good artifact

| file | what |
|---|---|
| `make_dataset.py` | writes `dataset.csv` from a documented generator (seed 987654321, 1600 rows, exact `W_TRUE`, noise σ = 0.30) |
| `dataset.csv` | the pinned dataset (sha256 `83029ea238f4cda3b2eec9e5a9f6518547f8edb226574520a3785ff7cdae799c`) |
| `build_notebook.py` | builds `analysis.ipynb` from its cell sources (single place to edit; the mutants in `judge/mutants.py` anchor on these lines) |
| `analysis.ipynb` | the graded artifact — ridge fit on the log target, three figures, `report.html`, tagged `metrics` JSON |

Everything here was written for this demo; no third-party code is copied.
The column names (`MED_INC`, `HOUSEHOLDS`, `AVE_ROOMS`, `AVE_BEDRMS`,
`POPULATION`, `AVE_OCCUPANCY`, `LAT`, `LONG`, `MED_VALUE`) deliberately
echo the classic California housing dataset — R. K. Pace & R. L. Barry
(1997), "Sparse Spatial Autoregressions", Statistics & Probability
Letters 33(3), as shipped by scikit-learn's `fetch_california_housing`
(BSD-3-Clause, https://scikit-learn.org/stable/datasets/real_world.html#california-housing-dataset,
version 1.9.1) — but **every row is synthetic**, drawn by `make_dataset.py`
from the documented generator above; no real data is used or included.

To rebuild the artifact after editing:

```bash
python3 examples/good/make_dataset.py   # only if the generator changed
python3 examples/good/build_notebook.py
```

The judge refuses a notebook that ships execution counts or outputs:
`build_notebook.py` always writes a clean, un-executed notebook.
