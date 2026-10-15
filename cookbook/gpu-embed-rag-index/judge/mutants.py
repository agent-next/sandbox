#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Each mutant is the good rag.py with exactly one scripted edit; the self-test
expects every mutant to fail at least one gate (SPEC.md). Mutants cover the
failure classes from the brief: wrong normalization, shuffled ids, truncated
corpus, different model, top-k off by one, and cpu-only hard-coding.
"""

import os
import sys

# (name, must-exist-literal, replacement)
EDITS = [
    ("wrong_normalization",
     "        normalize_embeddings=True,",
     "        normalize_embeddings=False,"),
    ("shuffled_ids",
     "    distances, indices = index.search(queries, k)\n    return distances, indices",
     "    distances, indices = index.search(queries, k)\n"
     "    indices = np.roll(indices, 1, axis=1)\n"
     "    return distances, indices"),
    ("truncated_corpus",
     "    emb = model.encode(\n        passages,",
     "    passages = passages[:-max(1, len(passages) // 10)]\n"
     "    emb = model.encode(\n        passages,"),
    ("different_model",
     'MODEL_NAME = "all-MiniLM-L6-v2"',
     'MODEL_NAME = "all-MiniLM-L12-v2"'),
    ("topk_off_by_one",
     "def search(index, queries, k=TOPK):",
     "def search(index, queries, k=TOPK - 1):"),
    ("cpu_only",
     '    return "cuda" if torch.cuda.is_available() else "cpu"',
     '    return "cpu"'),
]


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    good = open(os.path.join(src_dir, "rag.py")).read()
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, old, new in EDITS:
        if old not in good:
            raise SystemExit(f"mutant {name}: edit anchor not found in good rag.py")
        mutant = good.replace(old, new, 1)
        if mutant == good:
            raise SystemExit(f"mutant {name}: edit produced no change")
        path = os.path.join(out_dir, name + ".py")
        with open(path, "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
