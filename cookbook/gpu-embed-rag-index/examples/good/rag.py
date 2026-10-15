"""GPU embedding + FAISS vector index for RAG.

Embeds passages with the pinned sentence-transformers/all-MiniLM-L6-v2 model,
builds an exact FAISS inner-product index, and answers queries by exact
top-k search. L2-normalized embeddings make inner-product equivalent to
cosine similarity.

Public API (used by the judge):
  embed_passages(passages, batch_size=64) -> np.ndarray  (L2-normalized)
  build_index(embeddings) -> faiss.Index
  search(index, queries, k=10) -> (distances, indices)
  main()  — CLI: reads corpus.jsonl + queries.jsonl, writes results.json
"""

import json
import os
import sys

import numpy as np
import torch
import faiss
from sentence_transformers import SentenceTransformer

MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 64
TOPK = 10


def _device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def embed_passages(passages, batch_size=BATCH_SIZE):
    """Embed passages with the pinned model; return L2-normalized float32 array."""
    model = SentenceTransformer(MODEL_NAME, device=_device())
    emb = model.encode(
        passages,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return np.asarray(emb, dtype=np.float32)


def build_index(embeddings):
    """Build an exact FAISS inner-product index over L2-normalized embeddings."""
    embeddings = np.ascontiguousarray(embeddings, dtype=np.float32)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings)
    return index


def search(index, queries, k=TOPK):
    """Exact top-k search; returns (distances, indices)."""
    distances, indices = index.search(queries, k)
    return distances, indices


def main():
    """CLI: read corpus.jsonl + queries.jsonl, write results.json."""
    corpus_path = os.environ.get("CORPUS_PATH", "corpus.jsonl")
    queries_path = os.environ.get("QUERIES_PATH", "queries.jsonl")
    output_path = os.environ.get("OUTPUT_PATH", "results.json")

    with open(corpus_path) as f:
        passages = [json.loads(line)["text"] for line in f if line.strip()]
    with open(queries_path) as f:
        queries = [json.loads(line)["text"] for line in f if line.strip()]

    print(f"embedding {len(passages)} passages on {_device()}...", flush=True)
    corpus_emb = embed_passages(passages)
    print(f"building FAISS index (dim={corpus_emb.shape[1]})...", flush=True)
    index = build_index(corpus_emb)

    print(f"embedding {len(queries)} queries...", flush=True)
    query_emb = embed_passages(queries)

    print(f"searching top-{TOPK}...", flush=True)
    distances, indices = search(index, query_emb, k=TOPK)

    results = {
        "n_passages": len(passages),
        "n_queries": len(queries),
        "topk": TOPK,
        "results": [
            {
                "query_id": i,
                "top_ids": indices[i].tolist(),
                "top_scores": distances[i].tolist(),
            }
            for i in range(len(queries))
        ],
    }
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"wrote {output_path}", flush=True)


if __name__ == "__main__":
    main()
