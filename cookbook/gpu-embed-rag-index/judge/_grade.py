#!/usr/bin/env python3
"""Judge driver for the gpu-embed-rag-index demo. Invoked by grade.sh; see SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure          - size, byte-compile, API surface, model name present
  gate 2 embedding-equality - artifact embeddings vs judge's independent CPU
                              reference (same pinned model, separate subprocess)
  gate 3 index-correctness  - recall@10 vs brute-force gold; exact index props
  gate 4 throughput          - reported (CUDA full mode only); gates only with
                              --speed-target

Prints one JSON verdict on stdout; exit 0 only if every gated pass rule holds.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
JUDGE_VENV_PY = os.path.join(os.path.expanduser("~"), ".venvs",
                             "gpu-embed-rag-index", "bin", "python")

MAX_BYTES = 128 * 1024

# embedding-equality case: (n_passages, seed)
EMB_CASES = [(200, 0)]
EMB_COSINE_MIN = 0.999

# index-correctness case: (n_queries, n_corpus, seed, gold_top10_min)
INDEX_CASES = [(20, 2000, 0, 0.90)]
RECALL_MIN = 0.90
TOPK = 10

# throughput case: (n_passages, seed)
THROUGHPUT_CASES = [(20000, 0)]

# reference corpus: seeded random passages (deterministic)
CORPUS_SEED = 42
N_CORPUS = 20000
N_QUERIES = 200
DIM = 384  # all-MiniLM-L6-v2 output dimension


def die(msg):
    print(json.dumps({"error": msg}))
    sys.exit(2)


def check_shas(judge_dir):
    """sha256 of every judge/ source file, before and after the run."""
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            path = os.path.join(root, name)
            with open(path, "rb") as fh:
                digests[os.path.relpath(path, judge_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return digests


def load_artifact(path):
    if os.path.getsize(path) > MAX_BYTES:
        raise ValueError("artifact exceeds 128 KiB")
    with open(path, "rb") as fh:
        source = fh.read()
    compile(source, path, "exec")
    text = source.decode("utf-8", "replace")
    spec = importlib.util.spec_from_file_location(
        "artifact_under_test", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, text


def gate_structure(mod, text):
    problems = []
    for fn in ("embed_passages", "build_index", "search", "main"):
        if not callable(getattr(mod, fn, None)):
            problems.append(f"{fn} is not callable")
    if "all-MiniLM-L6-v2" not in text:
        problems.append("artifact text does not contain 'all-MiniLM-L6-v2'")
    return problems


def compute_reference_embeddings(passages):
    """Compute reference embeddings in a subprocess with the pinned model."""
    code = (
        "import sys, json, numpy as np;"
        "from sentence_transformers import SentenceTransformer;"
        "model = SentenceTransformer('all-MiniLM-L6-v2');"
        "emb = model.encode(sys.argv[1], batch_size=64, "
        "convert_to_numpy=True, normalize_embeddings=True);"
        "np.save(sys.argv[2], emb)"
    )
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        json.dump(passages, f)
        passages_path = f.name
    emb_path = passages_path + ".npy"
    try:
        r = subprocess.run(
            [JUDGE_VENV_PY, "-c", code, passages_path, emb_path],
            capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(f"reference embedding failed: {r.stderr[-300:]}")
        return np.load(emb_path)
    finally:
        os.unlink(passages_path)
        if os.path.exists(emb_path):
            os.unlink(emb_path)


def cosine_similarity(a, b):
    """Per-row cosine similarity between two 2-D arrays."""
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return np.sum(a_norm * b_norm, axis=1)


def gate_embedding_equality(mod, passages):
    """Compare artifact embeddings vs judge's independent reference."""
    import numpy as np
    ref = compute_reference_embeddings(passages)
    art = mod.embed_passages(passages)
    if art.shape != ref.shape:
        return {"pass": False,
                "problems": [f"shape mismatch: artifact {art.shape} vs ref {ref.shape}"]}
    cos = cosine_similarity(art, ref)
    worst = float(np.min(cos))
    return {"pass": worst >= EMB_COSINE_MIN,
            "problems": [] if worst >= EMB_COSINE_MIN else
            [f"worst cosine similarity {worst:.6f} < {EMB_COSINE_MIN}"],
            "worst_cosine": worst,
            "n_passages": len(passages)}


def compute_gold_ids(query_embeddings, corpus_embeddings, k=TOPK):
    """Brute-force exact top-k gold ids (judge's own oracle)."""
    import numpy as np
    # corpus_embeddings: (n_corpus, dim) L2-normalized
    # query_embeddings: (n_queries, dim) L2-normalized
    scores = query_embeddings @ corpus_embeddings.T  # (n_queries, n_corpus)
    # exact top-k
    idx = np.argpartition(-scores, k, axis=1)[:, :k]
    # sort those k by score descending
    rows = np.arange(len(query_embeddings))[:, None]
    order = np.argsort(-scores[rows, idx], axis=1)
    gold = idx[rows, order]
    return gold


def gate_index_correctness(mod, corpus_embeddings, query_embeddings, gold_ids):
    """Check recall@10 and index properties."""
    import numpy as np
    import faiss

    index = mod.build_index(corpus_embeddings)
    if not isinstance(index, faiss.Index):
        return {"pass": False, "problems": ["build_index did not return a faiss.Index"]}

    problems = []
    if index.metric_type != faiss.METRIC_INNER_PRODUCT:
        problems.append(f"metric_type {index.metric_type} != METRIC_INNER_PRODUCT")
    if not index.is_trained:
        problems.append("index is not trained")

    distances, indices = mod.search(index, query_embeddings, k=TOPK)
    if indices.shape != (len(query_embeddings), TOPK):
        problems.append(f"indices shape {indices.shape} != ({len(query_embeddings)}, {TOPK})")
    if np.any(indices < 0) or np.any(indices >= len(corpus_embeddings)):
        problems.append("indices out of range")

    if not problems:
        # recall@10: fraction of queries whose gold top-1 passage is in top-10
        recall = float(np.mean([gold_ids[i, 0] in indices[i] for i in range(len(gold_ids))]))
        if recall < RECALL_MIN:
            problems.append(f"recall@10 {recall:.3f} < {RECALL_MIN}")
        return {"pass": recall >= RECALL_MIN, "problems": problems,
                "recall_at_10": recall, "n_queries": len(query_embeddings)}

    return {"pass": False, "problems": problems}


def gate_throughput(mod, passages):
    """Time artifact embed_passages on GPU and CPU."""
    import torch
    import numpy as np

    # GPU timing
    if torch.cuda.is_available():
        t0 = time.monotonic()
        _ = mod.embed_passages(passages)
        torch.cuda.synchronize()
        gpu_time = time.monotonic() - t0
    else:
        gpu_time = None

    # CPU timing (force cpu)
    device = torch.device("cpu")
    t0 = time.monotonic()
    _ = mod.embed_passages(passages)
    cpu_time = time.monotonic() - t0

    result = {"cpu_time_s": cpu_time, "cpu_passages_per_s": len(passages) / cpu_time}
    if gpu_time is not None:
        result["gpu_time_s"] = gpu_time
        result["gpu_passages_per_s"] = len(passages) / gpu_time
        result["speedup"] = cpu_time / gpu_time
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--cpu-check", action="store_true")
    ap.add_argument("--speed-target", type=float)
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    if args.cpu_check:
        mode = "cpu-check"
    else:
        probe = subprocess.run(
            [sys.executable, "-c", "import torch; print(int(torch.cuda.is_available()))"],
            capture_output=True, text=True, timeout=60)
        mode = ("full" if probe.returncode == 0 and probe.stdout.strip() == "1"
                else "cpu-check")

    global np
    import numpy as np

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    sha_before = check_shas(judge_dir)

    tmp = tempfile.mkdtemp(prefix="rag-artifact-")
    art_path = os.path.join(tmp, "rag.py")
    shutil.copy(args.artifact, art_path)

    verdict = {"artifact": os.path.basename(args.artifact), "mode": mode,
               "seed": args.seed, "gates": {}, "timing": {}, "cases": []}
    rc = 0
    try:
        try:
            mod, text = load_artifact(art_path)
        except Exception as exc:
            verdict["gates"]["structure"] = {"pass": False,
                                             "problems": [str(exc)[:300]]}
            rc = 1
        else:
            verdict["gates"]["structure"] = {
                "pass": True, "problems": gate_structure(mod, text)}
            if verdict["gates"]["structure"]["problems"]:
                verdict["gates"]["structure"]["pass"] = False
                rc = 1

        if rc == 0:
            # embedding-equality gate
            for n_passages, seed in EMB_CASES:
                # generate deterministic passages
                import random
                rng = random.Random(CORPUS_SEED + seed + args.seed)
                passages = [f"passage {i} " + " ".join(
                    rng.choice(["the", "quick", "brown", "fox", "jumps", "over",
                                "lazy", "dog", "hello", "world", "embedding",
                                "vector", "search", "index", "gpu", "cpu"])
                    for _ in range(20)) for i in range(n_passages)]
                result = gate_embedding_equality(mod, passages)
                verdict["cases"].append({"gate": "embedding-equality",
                                          "n_passages": n_passages, "seed": seed,
                                          **result})
                if not result["pass"]:
                    verdict["gates"]["embedding-equality"] = result
                    rc = 1
                    break
            else:
                verdict["gates"]["embedding-equality"] = {
                    "pass": True,
                    "worst_cosine": min(c.get("worst_cosine", 1.0)
                                       for c in verdict["cases"]
                                       if c["gate"] == "embedding-equality")}

        if rc == 0:
            # index-correctness gate
            for n_queries, n_corpus, seed, recall_min in INDEX_CASES:
                import random
                rng = random.Random(CORPUS_SEED + seed + args.seed)
                corpus_passages = [f"corpus passage {i} " + " ".join(
                    rng.choice(["the", "quick", "brown", "fox", "jumps", "over",
                                "lazy", "dog", "hello", "world", "embedding",
                                "vector", "search", "index", "gpu", "cpu"])
                    for _ in range(20)) for i in range(n_corpus)]
                query_passages = [f"query passage {i} " + " ".join(
                    rng.choice(["the", "quick", "brown", "fox", "jumps", "over",
                                "lazy", "dog", "hello", "world", "embedding",
                                "vector", "search", "index", "gpu", "cpu"])
                    for _ in range(20)) for i in range(n_queries)]

                # judge computes reference embeddings for corpus and queries
                corpus_emb = compute_reference_embeddings(corpus_passages)
                query_emb = compute_reference_embeddings(query_passages)
                gold_ids = compute_gold_ids(query_emb, corpus_emb)

                result = gate_index_correctness(mod, corpus_emb, query_emb, gold_ids)
                verdict["cases"].append({"gate": "index-correctness",
                                          "n_queries": n_queries, "n_corpus": n_corpus,
                                          "seed": seed, **result})
                if not result["pass"]:
                    verdict["gates"]["index-correctness"] = result
                    rc = 1
                    break
            else:
                verdict["gates"]["index-correctness"] = {
                    "pass": True,
                    "recall_at_10": min(c.get("recall_at_10", 1.0)
                                        for c in verdict["cases"]
                                        if c["gate"] == "index-correctness")}

        if rc == 0 and mode == "full":
            # throughput gate (reported, not gated unless --speed-target)
            for n_passages, seed in THROUGHPUT_CASES:
                import random
                rng = random.Random(CORPUS_SEED + seed + args.seed)
                passages = [f"passage {i} " + " ".join(
                    rng.choice(["the", "quick", "brown", "fox", "jumps", "over",
                                "lazy", "dog", "hello", "world", "embedding",
                                "vector", "search", "index", "gpu", "cpu"])
                    for _ in range(20)) for i in range(n_passages)]
                timing = gate_throughput(mod, passages)
                verdict["timing"].update(timing)
                if args.speed_target is not None:
                    verdict["gates"]["throughput"] = {
                        "pass": timing.get("speedup", 0) >= args.speed_target,
                        "target": args.speed_target,
                        "speedup": timing.get("speedup")}
                    if not verdict["gates"]["throughput"]["pass"]:
                        rc = 1

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
