# gpu-embed-rag-index: GPU embedding + vector index demo — SPEC

An agent works inside a disposable sandbox on a real RAG-index engineering
problem: embed a corpus of passages with a pinned sentence-transformers
model on a GPU slice, build a FAISS vector index, answer queries with known
gold passages, and iterate against a judge it cannot fool. The judge never
accepts "it ran": it recomputes embeddings with an independent CPU reference,
checks recall@10 against gold, verifies GPU/CPU embedding equality, and
reports throughput honestly.

## Goal

- Artifact: one Python file (`rag.py`) that loads a pinned
  `sentence-transformers/all-MiniLM-L6-v2` model, embeds a corpus of passages
  on GPU, builds a FAISS index, embeds queries, and writes a results JSON
  with per-query top-10 passage ids. It must pass every judge gate below.
- Judge: `judge/grade.sh` with numeric, deterministic pass rules, runnable on
  GPU machines (full path: GPU embeddings, FAISS index, recall, throughput)
  and on CPU-only machines (`--cpu-check`: CPU embeddings, same gates minus
  GPU throughput).
- Self-test: `judge/selftest.sh` proves the judge fails known-bad artifacts.

## Non-goals

- Approximate nearest-neighbour recall tuning beyond exact search (the judge
  uses exact `IndexFlatIP` so recall is deterministic and oracle-checkable).
- Other embedding models, other index types (IVF, HNSW), or quantization.
- GPU execution as a gate on CPU-only machines; the GPU throughput path needs
  a CUDA sandbox (see `README.md`).
- Streaming, batching strategies beyond a fixed batch size, or distributed
  indexing.

## The artifact contract

`rag.py` must define:

| name | what |
|---|---|
`embed_passages(passages: list[str], batch_size: int = 64) -> np.ndarray` | embed a list of passages; return a 2-D float32 numpy array of shape `(len(passages), dim)`, L2-normalized rows |
`build_index(embeddings: np.ndarray) -> faiss.Index` | build and return a FAISS index over the given embeddings; must be exact inner-product search |
`search(index: faiss.Index, queries: np.ndarray, k: int = 10) -> tuple[np.ndarray, np.ndarray]` | search the index; return `(distances, indices)` where indices has shape `(len(queries), k)` |
`main()` | CLI entry: reads `corpus.jsonl` and `queries.jsonl` from the current directory, embeds, indexes, searches, writes `results.json` |

- The judge calls `embed_passages`, `build_index`, and `search` directly with
  controlled inputs, and also runs `main()` end-to-end on a small fixture.
- `embed_passages` must use the pinned model
  `sentence-transformers/all-MiniLM-L6-v2` and must not delegate to a
  different model or a cached/precomputed embedding file.
- The model name string `all-MiniLM-L6-v2` must appear in the artifact text
  (the judge checks this).

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--cpu-check]`
exits 0 only if gates 1–4 all pass. `--seed` (default 0) offsets every case
seed, keeping runs deterministic. Modes: auto — full mode when
`torch.cuda.is_available()`, otherwise cpu-check; `--cpu-check` forces the
CPU path. The artifact is graded from a copy in a fresh temp dir; sha256
checksums of `judge/` before and after must match, else the run fails.

1. **structure** — the artifact is a Python file of at most 128 KiB; it
   byte-compiles; it defines callables `embed_passages`, `build_index`,
   `search`, and `main`; its text contains the model name
   `all-MiniLM-L6-v2`.
2. **embedding-equality** — for a fixed 200-passage sample (seeded), the
   artifact's `embed_passages` output must match the judge's independent CPU
   reference embeddings (computed with the same pinned model in the judge's
   own venv) within cosine similarity ≥ 0.999 for every passage. The judge
   computes its reference embeddings in a separate subprocess with the same
   pinned model and compares.
3. **index-correctness** — for a fixed set of 20 queries (seeded) with known
   gold passage ids:
   - `search` returns indices of shape `(20, 10)` with all indices in
     `[0, len(corpus))`;
   - recall@10 ≥ 0.90 (at least 18 of 20 queries have their gold passage in
     the top-10);
   - the index is exact: `index.metric_type == faiss.METRIC_INNER_PRODUCT`
     and `index.is_trained is True`.
4. **throughput (reported)** — full mode only: wall time of `embed_passages`
   over the full 20k-passage corpus on GPU vs CPU (the judge times both);
   the verdict JSON reports `gpu_passages_per_s`, `cpu_passages_per_s`, and
   `speedup = cpu_time / gpu_time`. Throughput never affects the exit code.

The judge uses an independent oracle: it computes reference embeddings with
the same pinned model in its own subprocess (never trusting the artifact's
output), computes gold passage ids by brute-force exact search over the
corpus, and compares the artifact's search results against that gold.

## Acceptance oracle

The judge never trusts the artifact's own idea of correct. Correctness is
decided by: (a) cosine similarity of artifact embeddings vs independently
computed reference embeddings (same model, same passages, judge's own
subprocess); (b) recall@10 of artifact search results vs brute-force gold
ids computed by the judge; (c) FAISS index properties (exact inner-product,
trained). An artifact that merely "runs" without matching the oracles fails.

## Known-bad examples (self-test)

`judge/mutants.py` derives ≥ 5 known-bad artifacts from the known-good one by
scripted single edits:

1. **wrong-normalization** — embeddings not L2-normalized (raw model output).
2. **shuffled-ids** — search returns indices shuffled (off-by-one or random
   permutation).
3. **truncated-corpus** — embed_passages silently drops the last 10% of
   passages.
4. **different-model** — uses `all-MiniLM-L12-v2` instead of `all-MiniLM-L6-v2`.
5. **topk-off-by-one** — search returns k=9 instead of k=10.
6. **cpu-only** — embed_passages forces `device='cpu'` even when CUDA is
   available (killed by throughput gate in full mode; in cpu-check mode it
   survives throughput but is caught by a structure check that the artifact
   does not hard-code `device='cpu'`).

`judge/selftest.sh` grades the known-good (must pass) and every mutant (each
must fail ≥ 1 gate), prints the kill rate, and checks determinism (two grades
of the good artifact produce byte-identical verdicts except the `timing` key).
It exits non-zero unless the kill rate is ≥ 90 %.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/gpu-embed-rag-index/` exactly
what the judge needs and nothing else: `sentence-transformers==2.7.0`,
`faiss-cpu==1.8.0`, `torch==2.3.1`, `numpy==1.26.4`, and the full transitive
closure, every package pinned and sha256-verified through pip's
`--require-hashes` mode. One lock file, generated by `judge/genlock.py` from
live PyPI hashes:

- `judge/requirements.lock` — the CPU closure (torch 2.3.1+cpu wheel for the
  supported CPython plus the small CPU closure); the default on CPU-only
  machines (incl. this builder sandbox).

Wheels are covered for CPython 3.10–3.13 on x86-64 Linux. Every pinned
release predates 2026-09-30 (nothing published in the two weeks before this
demo was built). `setup.sh` is idempotent: it skips installation when the
venv already provides the pinned versions, and it refuses to run on other
platforms. `judge/VERSIONS.txt` records what it actually installed.

## Reproducibility

Grading is deterministic given `--seed`: two runs produce byte-identical
verdict JSON except the `timing` key (wall-clock timing is inherently noisy)
— enforced by `selftest.sh`. RECEIPT.md carries real pasted output of setup,
selftest and grade with exit codes, kill rate, key numbers and wall time of
each, plus a Deviations section. Demo media under `media/` is generated from
committed run data by `media/make_media.sh`; the judge itself produces no
media.

## GPU path (lead's run)

The GPU path uses a 1 GiB VRAM slice lease created via the agent-next REST
API (exactly like `cookbook/small-gpu/run.py`):

```
POST /sandboxes {"accel":{"vram_gb":1,"reserve":"exec"}}
→ returns lease id (gl-...)
POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": N}
→ runs the full judge: structure + embedding-equality + index-correctness + throughput + mutants
DELETE /sandboxes/{id}
GET /sandboxes/{id} → 404 (or phase=dead)
```

The lease image already has Python 3.13, torch 2.10.0+cu128, numpy 1.26.4 on
an RTX 5090 slice (cc 12.0); no nvcc, no pip needed. The pinned model weights
and faiss-cpu wheel are uploaded to the lease via the files API before the
judge runs.
