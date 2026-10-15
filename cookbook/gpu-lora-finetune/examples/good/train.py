#!/usr/bin/env python3
"""Produce the known-good LoRA fine-tune artifact (runs on a GPU lease).

  python3 train.py --model-dir <pinned base model> --out <artifact-dir>

Fine-tunes Qwen/Qwen3-0.6B with PEFT LoRA on judge/task.py's seeded
date-normalization train split (2000 examples), then writes the artifact
contract from SPEC.md into --out:

  adapter/adapter_config.json + adapter_model.safetensors  (PEFT save)
  metrics.json       losses + accuracy summaries for the record
  predictions.csv    held-out inputs with the fine-tuned model's answers

The run reads its exact hyperparameters from run_cfg.json next to this
file, so the committed config is the single record of the run. Everything
is seeded; the judge never re-runs training, it grades the artifact.
"""

import argparse
import csv
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "judge"))
import task                                      # noqa: E402


def set_seed(seed):
    import torch
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def build_batches(items, tokenizer, batch_size, seed, epoch):
    """Prompt-masked causal LM batches, reshuffled per epoch with a seed."""
    import torch
    rng = random.Random(seed * 1000 + epoch)
    order = list(range(len(items)))
    rng.shuffle(order)
    for i in range(0, len(order), batch_size):
        idx = order[i:i + batch_size]
        texts = [task.prompt(items[j][0]) for j in idx]
        targets = [task.target(items[j][1]) for j in idx]
        enc = tokenizer(texts, return_tensors="pt", padding=True)
        tgt = tokenizer(targets, return_tensors="pt", padding=True,
                        add_special_tokens=False)
        input_ids = torch.cat(
            [enc.input_ids, tgt.input_ids], dim=1)
        labels = torch.full_like(input_ids, -100)
        labels[:, enc.input_ids.shape[1]:] = tgt.input_ids
        # mask padding in the target part too
        labels[input_ids == tokenizer.pad_token_id] = -100
        attn = torch.cat(
            [enc.attention_mask, tgt.attention_mask], dim=1)
        yield input_ids, attn, labels


def generate_predictions(model, tokenizer, items, device, batch_size=32):
    """Greedy batched generation, judge-identical normalization."""
    import torch
    tokenizer.padding_side = "left"
    preds = []
    model.eval()
    with torch.no_grad():
        for i in range(0, len(items), batch_size):
            batch = [task.prompt(x) for x, _ in items[i:i + batch_size]]
            enc = tokenizer(batch, return_tensors="pt", padding=True)
            enc = {k: v.to(device) for k, v in enc.items()}
            gen = model.generate(**enc, max_new_tokens=8, do_sample=False,
                                 num_beams=1,
                                 pad_token_id=tokenizer.pad_token_id)
            text = tokenizer.batch_decode(
                gen[:, enc["input_ids"].shape[1]:],
                skip_special_tokens=True)
            preds.extend(task.normalize_prediction(t) for t in text)
    return preds


def accuracy(preds, items):
    return sum(p == a for p, (_, a) in zip(preds, items)) / len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    with open(os.path.join(HERE, "run_cfg.json")) as fh:
        cfg = json.load(fh)
    seed = cfg["seed"]
    set_seed(seed)

    import torch
    from torch.optim import AdamW
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model

    t0 = time.time()
    device = args.device if torch.cuda.is_available() else "cpu"
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir,
                                              local_files_only=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir, dtype=torch.bfloat16, attn_implementation="sdpa",
        local_files_only=True).to(device)
    model.config.use_cache = False

    lora_cfg = LoraConfig(
        r=cfg["lora"]["r"], lora_alpha=cfg["lora"]["lora_alpha"],
        lora_dropout=cfg["lora"]["lora_dropout"],
        target_modules=cfg["lora"]["target_modules"],
        task_type="CAUSAL_LM",
        base_model_name_or_path=cfg["base_model"])
    model = get_peft_model(model, lora_cfg)
    # train the LoRA delta in fp32 on top of the bf16 base
    for name, p in model.named_parameters():
        if "lora_" in name:
            p.data = p.data.float()
    model.print_trainable_parameters()

    train = task.train_set()
    test = task.test_set()
    eval_train = train[:200]

    opt = AdamW([p for n, p in model.named_parameters() if "lora_" in n],
                lr=cfg["lr"], weight_decay=0.0)
    steps_per_epoch = (len(train) + cfg["batch_size"] - 1) // cfg["batch_size"]
    total_steps = steps_per_epoch * cfg["epochs"]
    warmup = cfg["warmup_steps"]

    def lr_at(step):
        if step < warmup:
            return cfg["lr"] * (step + 1) / warmup
        prog = (step - warmup) / max(1, total_steps - warmup)
        return cfg["lr"] * 0.5 * (1 + pow(1 - prog, 2))  # cosine-ish decay

    losses = []
    step = 0
    model.train()
    for epoch in range(cfg["epochs"]):
        for input_ids, attn, labels in build_batches(
                train, tokenizer, cfg["batch_size"], seed, epoch):
            for g in opt.param_groups:
                g["lr"] = lr_at(step)
            input_ids = input_ids.to(device)
            attn = attn.to(device)
            labels = labels.to(device)
            out = model(input_ids=input_ids, attention_mask=attn,
                        labels=labels)
            out.loss.backward()
            opt.step()
            opt.zero_grad()
            step += 1
            if step % cfg["record_every"] == 0 and step > warmup // 2:
                losses.append(round(float(out.loss.item()), 5))
    model.eval()
    model.config.use_cache = True

    os.makedirs(os.path.join(args.out, "adapter"), exist_ok=True)
    # save the LoRA delta in float16 (small file; loads into any base dtype)
    for name, p in model.named_parameters():
        if "lora_" in name:
            p.data = p.data.half()
    model.save_pretrained(os.path.join(args.out, "adapter"),
                          safe_serialization=True)
    cfg_path = os.path.join(args.out, "adapter", "adapter_config.json")
    adapter_cfg = json.load(open(cfg_path))
    adapter_cfg["base_model_name_or_path"] = cfg["base_model"]
    with open(cfg_path, "w") as fh:
        json.dump(adapter_cfg, fh, indent=2, sort_keys=True)

    train_preds = generate_predictions(model, tokenizer, eval_train, device)
    fin_preds = generate_predictions(model, tokenizer, test, device)
    with model.disable_adapter():
        base_preds = generate_predictions(model, tokenizer, test, device)

    metrics = {
        "losses": losses,
        "train_accuracy": round(accuracy(train_preds, eval_train), 4),
        "baseline_accuracy": round(accuracy(base_preds, test), 4),
        "finetuned_accuracy": round(accuracy(fin_preds, test), 4),
        "seed": seed,
        "epochs": cfg["epochs"],
        "batch_size": cfg["batch_size"],
        "lr": cfg["lr"],
        "lora": cfg["lora"],
        "base_model": cfg["base_model"],
        "n_train": len(train),
        "n_test": len(test),
        "device": torch.cuda.get_device_name(0)
        if device == "cuda" else "cpu",
        "train_wall_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(args.out, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2, sort_keys=True)

    with open(os.path.join(args.out, "predictions.csv"), "w",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["input", "prediction"])
        for (inp, _), pred in zip(test, fin_preds):
            w.writerow([inp, pred])

    print(json.dumps({k: v for k, v in metrics.items()
                      if k != "losses"}, indent=2, sort_keys=True))
    print(f"train.py: artifact written to {args.out} "
          f"({time.time() - t0:.0f} s total)")


if __name__ == "__main__":
    main()
