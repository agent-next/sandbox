#!/usr/bin/env python3
"""Known-good artifact for the gpu-llm-batch-eval demo.

Batched greedy generation with `transformers` over the 100 pinned GSM8K
problems, then a self-report of accuracy and throughput. The judge does not
trust any of the reported numbers: it re-extracts the final answer from
every raw generation with its own extractor and recomputes accuracy,
completeness and throughput.

Environment the judge supplies:

    LLM_EVAL_MODEL_DIR   directory holding the pinned model + tokenizer
                         (default: $LLM_EVAL_MODEL_DIR or ./model)
    LLM_EVAL_PROBLEMS    problems.json (default: ./problems.json)
    LLM_EVAL_DEVICE      "cuda" or "cpu" (default: "cuda")
    LLM_EVAL_SEED        integer seed (greedy decoding ignores it, but the
                         bundle records it)
    LLM_EVAL_BATCH       batch size (default: 8)
    LLM_EVAL_MAX_NEW     max_new_tokens (default: 256)

Writes `bundle.json` next to itself. Nothing here reaches the network: the
model is loaded from a local directory with local_files_only=True.
"""

import json
import os
import re
import sys
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_COMMIT = "7ae557604adf67be50417f59c2c2f167def9a775"
PROMPT_SUFFIX = ("\nSolve the problem step by step. End your answer with the "
                 "line 'Final answer: <number>'.")

# The artifact's own extractor. It is allowed to differ from the judge's;
# the judge re-extracts regardless. This one mirrors the prompt's request.
FINAL_RE = re.compile(r"final\s*answer\s*[:\-]?\s*\**\s*([-+]?[\d,]+(?:\.\d+)?)",
                      re.IGNORECASE)
ANY_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def extract_answer(text):
    """The final numeric answer, or None."""
    if not text:
        return None
    hits = FINAL_RE.findall(text) or ANY_RE.findall(text)
    if not hits:
        return None
    raw = hits[-1].replace(",", "")
    try:
        value = float(raw)
    except ValueError:
        return None
    return str(int(value)) if value == int(value) else repr(round(value, 6))


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.environ.get("LLM_EVAL_MODEL_DIR", os.path.join(here, "model"))
    problems_path = os.environ.get("LLM_EVAL_PROBLEMS",
                                   os.path.join(here, "problems.json"))
    device = os.environ.get("LLM_EVAL_DEVICE", "cuda")
    seed = int(os.environ.get("LLM_EVAL_SEED", "0"))
    batch_size = int(os.environ.get("LLM_EVAL_BATCH", "8"))
    max_new = int(os.environ.get("LLM_EVAL_MAX_NEW", "256"))

    if device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("eval.py: LLM_EVAL_DEVICE=cuda but CUDA is "
                         "unavailable on this machine")

    with open(problems_path) as fh:
        problems_doc = json.load(fh)
    rows = problems_doc["problems"]

    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    model = AutoModelForCausalLM.from_pretrained(
        model_dir, dtype=torch.bfloat16, local_files_only=True)
    model.to(device)
    model.eval()

    prompts = [
        tokenizer.apply_chat_template(
            [{"role": "user", "content": r["question"] + PROMPT_SUFFIX}],
            tokenize=False, add_generation_prompt=True)
        for r in rows
    ]

    generations = [None] * len(rows)
    generated_tokens = 0
    started = time.monotonic()
    for start in range(0, len(rows), batch_size):
        chunk = list(range(start, min(start + batch_size, len(rows))))
        enc = tokenizer([prompts[i] for i in chunk], return_tensors="pt",
                        padding=True).to(device)
        with torch.no_grad():
            out = model.generate(
                **enc, max_new_tokens=max_new, do_sample=False,
                pad_token_id=tokenizer.eos_token_id)
        new = out[:, enc["input_ids"].shape[1]:]
        lengths = (new != tokenizer.pad_token_id).sum(dim=1).tolist()
        for j, i in enumerate(chunk):
            generated_tokens += int(lengths[j])
            ids = new[j][:int(lengths[j])]
            generations[i] = {
                "i": rows[i]["i"],
                "question": rows[i]["question"],
                "generation": tokenizer.decode(ids, skip_special_tokens=True),
                "max_new_tokens": int(lengths[j]),
            }
        print(f"eval.py: batch {start // batch_size + 1}/"
              f"{(len(rows) + batch_size - 1) // batch_size}", flush=True)
    wall_time_s = time.monotonic() - started

    for g in generations:
        g["extracted_answer"] = extract_answer(g["generation"])

    correct = sum(1 for g, r in zip(generations, rows)
                  if g["extracted_answer"] == r["gold"])

    import hashlib
    with open(problems_path, "rb") as fh:
        problems_sha = hashlib.sha256(fh.read()).hexdigest()

    bundle = {
        "model": MODEL_ID,
        "model_commit": MODEL_COMMIT,
        "problems_sha256": problems_sha,
        "n_problems": len(rows),
        "batch_size": batch_size,
        "max_new_tokens": max_new,
        "temperature": 0.0,
        "greedy": True,
        "seed": seed,
        "dtype": "bfloat16",
        "device": device,
        "generated_tokens": generated_tokens,
        "wall_time_s": round(wall_time_s, 3),
        "throughput_tok_s": round(generated_tokens / wall_time_s, 3),
        "reported_accuracy": round(correct / len(rows), 6),
        "generations": generations,
    }
    out_path = os.path.join(here, "bundle.json")
    with open(out_path, "w") as fh:
        json.dump(bundle, fh, indent=1, sort_keys=True)
    print(f"eval.py: wrote {out_path}: accuracy "
          f"{bundle['reported_accuracy']:.3f}, "
          f"{bundle['throughput_tok_s']:.1f} tok/s, "
          f"{wall_time_s:.1f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
