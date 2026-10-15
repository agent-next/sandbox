#!/usr/bin/env python3
"""Grade a LoRA fine-tune artifact. See SPEC.md for the gate list.

  judge/_grade.py <artifact-dir-or-archive> [--seed N] [--json out.json]

The artifact is graded from a copy in a fresh temp dir; sha256 checksums of
judge/ before and after must match. One JSON verdict goes to stdout; exit 0
only if all gates pass and the judge is intact.

Cheap gates run first (structure, leakage, loss curve, adapter file
properties). The two eval gates — oracle-scored accuracy and the
adapter-detached control — load the pinned base model and run only when the
cheap gates pass; otherwise they are recorded as not-evaluated (the verdict
already fails). Eval passes are memoised under a sha256 key covering the
model, the adapter, the seed, the decoding parameters and the exact test
inputs, so re-grading is fast and byte-identical.
"""

import argparse
import contextlib
import csv
import datetime
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BASE_MODEL_ID = "Qwen/Qwen3-0.6B"
MODEL_DIR = os.environ.get(
    "GPU_LORA_MODEL_DIR",
    os.path.join(os.path.expanduser("~"), "models", "qwen3-0.6b"))
CACHE_DIR = os.environ.get(
    "GPU_LORA_EVAL_CACHE",
    os.path.join(os.path.expanduser("~"), ".cache", "gpu-lora-finetune",
                 "eval"))
MAX_NEW_TOKENS = 8
EVAL_BATCH = 16
EVAL_THREADS = 4          # fixed: eval numerics must not depend on core count
MAX_ADAPTER_BYTES = 64 * 1024 * 1024
MIN_ADAPTER_BYTES = 1024
ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def die(msg, code=2):
    print(f"_grade.py: {msg}", file=sys.stderr)
    raise SystemExit(code)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dir_hash(path):
    """sha256 over a directory tree: sorted names + contents."""
    h = hashlib.sha256()
    for root, dirs, files in os.walk(path):
        dirs.sort()
        for name in sorted(files):
            p = os.path.join(root, name)
            h.update(os.path.relpath(p, path).encode())
            h.update(b"\0")
            h.update(bytes.fromhex(sha256_file(p)))
    return h.hexdigest()


def unpack_artifact(src, dest):
    if os.path.isdir(src):
        shutil.copytree(src, dest)
    elif os.path.isfile(src) and tarfile.is_tarfile(src):
        with tarfile.open(src) as tf:
            tf.extractall(dest, filter="data")
    elif os.path.isfile(src) and zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as zf:
            zf.extractall(dest)
    else:
        die(f"artifact {src!r} is neither a directory nor a .tar.gz/.zip")


def qwen3_module_dims(config):
    """module name -> (in_features, out_features) for a Qwen3 config."""
    h = config["hidden_size"]
    q = config["num_attention_heads"] * config["head_dim"]
    kv = config["num_key_value_heads"] * config["head_dim"]
    inter = config["intermediate_size"]
    return {
        "q_proj": (h, q), "k_proj": (h, kv), "v_proj": (h, kv),
        "o_proj": (q, h), "gate_proj": (h, inter), "up_proj": (h, inter),
        "down_proj": (inter, h),
    }


def check_structure(art, gates, model_config):
    """Gate 1: files, adapter config, safetensors consistency, metrics, csv."""
    problems = []
    cfg_path = os.path.join(art, "adapter", "adapter_config.json")
    st_path = os.path.join(art, "adapter", "adapter_model.safetensors")
    for p in (cfg_path, st_path, os.path.join(art, "metrics.json"),
              os.path.join(art, "predictions.csv")):
        if not os.path.isfile(p):
            problems.append(f"missing {os.path.relpath(p, art)}")
    if problems:
        gates["structure"] = {"pass": False, "problems": problems}
        return None, None, None

    try:
        cfg = json.load(open(cfg_path))
        if not isinstance(cfg, dict):
            raise ValueError("not an object")
    except ValueError as exc:
        gates["structure"] = {"pass": False,
                              "problems": [f"adapter_config.json: {exc}"]}
        return None, None, None
    if cfg.get("base_model_name_or_path") != BASE_MODEL_ID:
        problems.append(f"base_model_name_or_path="
                        f"{cfg.get('base_model_name_or_path')!r}, expected "
                        f"{BASE_MODEL_ID!r}")
    if cfg.get("peft_type") != "LORA":
        problems.append(f"peft_type={cfg.get('peft_type')!r}, expected LORA")
    tm = cfg.get("target_modules")
    if not isinstance(tm, list) or not tm or \
            not all(isinstance(m, str) and m for m in tm):
        problems.append(f"target_modules={tm!r} must be a non-empty list")
        tm = []
    r = cfg.get("r")
    if not isinstance(r, int) or isinstance(r, bool) or r < 1:
        problems.append(f"r={r!r} must be a positive int")
        r = None
    if not isinstance(cfg.get("lora_alpha"), (int, float)):
        problems.append("lora_alpha missing/not numeric")
    if not isinstance(cfg.get("lora_dropout"), (int, float)):
        problems.append("lora_dropout missing/not numeric")

    # safetensors names/shapes, checked against the config without weights
    try:
        from safetensors import safe_open
        size = os.path.getsize(st_path)
        if size > MAX_ADAPTER_BYTES:
            problems.append(f"adapter file {size} bytes > {MAX_ADAPTER_BYTES}")
        dims = qwen3_module_dims(model_config) if model_config else None
        seen = {}
        with safe_open(st_path, framework="pt") as f:
            for k in f.keys():
                shape = tuple(f.get_slice(k).get_shape())
                seen[k] = shape
                m = re.search(r"self_attn\.([a-z_]+)\.lora_([AB])\.weight$",
                              k)
                if not m:
                    problems.append(f"unexpected tensor name {k!r}")
                    continue
                module, side = m.group(1), m.group(2)
                if module not in tm:
                    problems.append(f"tensor {k!r}: module {module!r} not in "
                                    f"target_modules {tm}")
                if r is not None:
                    if side == "A" and shape[0] != r:
                        problems.append(f"{k}: lora_A shape {shape}, first dim "
                                        f"!= r={r}")
                    if side == "B" and shape[-1] != r:
                        problems.append(f"{k}: lora_B shape {shape}, last dim "
                                        f"!= r={r}")
                if dims and module in dims:
                    want = dims[module]
                    if side == "A" and shape != (r, want[0]):
                        problems.append(f"{k}: shape {shape}, expected "
                                        f"({r}, {want[0]}) for {module}")
                    if side == "B" and shape != (want[1], r):
                        problems.append(f"{k}: shape {shape}, expected "
                                        f"({want[1]}, {r}) for {module}")
        for p in {re.sub(r"\.lora_[AB]\.weight$", "", k) for k in seen}:
            if f"{p}.lora_A.weight" not in seen or \
                    f"{p}.lora_B.weight" not in seen:
                problems.append(f"unpaired LoRA tensors for {p}")
        if not seen:
            problems.append("adapter safetensors has no tensors")
    except Exception as exc:                      # noqa: BLE001
        problems.append(f"adapter safetensors unreadable: {exc}")

    metrics = None
    try:
        metrics = json.load(open(os.path.join(art, "metrics.json")))
        losses = metrics.get("losses")
        if not isinstance(losses, list) or len(losses) < 8 or \
                not all(isinstance(x, (int, float)) and math.isfinite(x)
                        for x in losses):
            problems.append("metrics.json losses must be >= 8 finite floats")
        for field in ("train_accuracy", "baseline_accuracy",
                      "finetuned_accuracy"):
            v = metrics.get(field)
            if not isinstance(v, (int, float)) or not 0.0 <= v <= 1.0:
                problems.append(f"metrics.json {field}={v!r} not in [0, 1]")
    except ValueError as exc:
        problems.append(f"metrics.json: {exc}")

    rows = []
    try:
        with open(os.path.join(art, "predictions.csv"), newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            if header != ["input", "prediction"]:
                problems.append(f"predictions.csv header {header!r}, expected "
                                "['input', 'prediction']")
            rows = [row for row in reader]
        if len(rows) != 200:
            problems.append(f"predictions.csv has {len(rows)} rows, expected "
                            "200")
        bad = sum(1 for row in rows if len(row) != 2 or not ISO_RE.match(
            row[1]) or not _valid_iso(row[1]))
        if bad:
            problems.append(f"{bad} predictions not valid ISO calendar dates")
    except (OSError, csv.Error, StopIteration) as exc:
        problems.append(f"predictions.csv unreadable: {exc}")

    gates["structure"] = {"pass": not problems, "problems": problems}
    return cfg, metrics, rows


def _valid_iso(text):
    try:
        datetime.date(int(text[0:4]), int(text[5:7]), int(text[8:10]))
        return True
    except ValueError:
        return False


def check_leakage(rows, task, gates):
    """Gate 2: inputs are exactly the judge-regenerated test set, in order."""
    test = task.test_set()
    train_inputs = {x[0] for x in task.train_set()}
    problems = []
    if rows is not None:
        for i, row in enumerate(rows):
            if len(row) != 2:
                problems.append(f"row {i}: malformed")
                break
            if row[0] != test[i][0]:
                problems.append(f"row {i}: input {row[0]!r} != judge test "
                                f"input {test[i][0]!r}")
                break
            if row[0] in train_inputs:
                problems.append(f"row {i}: input {row[0]!r} is a train input")
                break
    gates["leakage"] = {"pass": not problems, "problems": problems,
                        "test_seed": task.TRAIN_SEED, "test_rows": len(test)}


def check_loss_curve(metrics, gates):
    """Gate 5: recorded losses decrease and never spike."""
    losses = (metrics or {}).get("losses")
    if isinstance(losses, list) and len(losses) >= 8 and \
            all(isinstance(x, (int, float)) and math.isfinite(x)
                for x in losses):
        problems = []
        first, last = losses[0], losses[-1]
        if last > 0.5 * first:
            problems.append(f"last loss {last} > 0.5 x first {first}")
        for i in range(1, len(losses)):
            if losses[i] - losses[i - 1] > 0.5:
                problems.append(f"loss rose {losses[i - 1]} -> {losses[i]} "
                                f"at recorded step {i}")
                break
        gates["loss_curve"] = {"pass": not problems, "problems": problems,
                               "first": first, "last": last,
                               "n": len(losses)}
    else:
        gates["loss_curve"] = {"pass": False, "problems":
                               ["losses missing/invalid (see structure)"]}


def check_adapter_file(art, gates):
    """Gate 6: non-empty, both lora prefixes present, no all-zero tensors."""
    st_path = os.path.join(art, "adapter", "adapter_model.safetensors")
    problems, size, names = [], 0, []
    try:
        size = os.path.getsize(st_path)
        if size <= MIN_ADAPTER_BYTES:
            problems.append(f"adapter file {size} bytes <= "
                            f"{MIN_ADAPTER_BYTES}")
        from safetensors import safe_open
        with safe_open(st_path, framework="pt") as f:
            names = list(f.keys())
            prefixes = {n.rsplit(".", 2)[-2] for n in names if "." in n}
            missing = {"lora_A", "lora_B"} - prefixes
            if missing:
                problems.append(f"missing LoRA prefixes: {sorted(missing)}")
            zeros = sum(1 for k in names
                        if float(f.get_tensor(k).abs().sum()) == 0.0)
        if zeros:
            problems.append(f"{zeros}/{len(names)} tensors are all-zero")
    except Exception as exc:                      # noqa: BLE001
        problems.append(f"adapter unreadable: {exc}")
    gates["adapter_file"] = {"pass": not problems, "problems": problems,
                             "bytes": size,
                             "tensors": len(names)}


class Evaluator:
    """Greedy exact-match eval over the regenerated test set, memoised."""

    def __init__(self, model, tok, task, seed, model_sha):
        self.model, self.tok, self.task = model, tok, task
        self.seed, self.model_sha = seed, model_sha

    def run(self, prompts, answers, adapter_sha, adapter_on):
        def fn():
            import torch
            torch.manual_seed(self.seed)
            out = []
            ctx = (contextlib.nullcontext() if adapter_on
                   else self.model.disable_adapter())
            with torch.no_grad(), ctx:
                for i in range(0, len(prompts), EVAL_BATCH):
                    enc = self.tok(prompts[i:i + EVAL_BATCH],
                                   return_tensors="pt", padding=True)
                    gen = self.model.generate(
                        **enc, max_new_tokens=MAX_NEW_TOKENS,
                        do_sample=False, num_beams=1,
                        pad_token_id=self.tok.pad_token_id)
                    text = self.tok.batch_decode(
                        gen[:, enc.input_ids.shape[1]:],
                        skip_special_tokens=True)
                    out.extend(self.task.normalize_prediction(t)
                               for t in text)
            acc = sum(p == a for p, a in zip(out, answers)) / len(answers)
            return out, acc

        key = self._key(prompts, adapter_sha if adapter_on else None)
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, key + ".json")
        if os.path.exists(path):
            try:
                data = json.load(open(path))
                if data.get("key") == key:
                    return data["predictions"], data["accuracy"]
            except (OSError, ValueError):
                pass
        predictions, accuracy = fn()
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump({"key": key, "predictions": predictions,
                       "accuracy": accuracy}, fh)
        os.replace(tmp, path)
        return predictions, accuracy

    def _key(self, prompts, adapter_sha):
        blob = json.dumps({"model": self.model_sha, "adapter": adapter_sha,
                           "seed": self.seed,
                           "max_new_tokens": MAX_NEW_TOKENS,
                           "batch": EVAL_BATCH, "threads": EVAL_THREADS,
                           "prompts": prompts}, sort_keys=True).encode()
        return hashlib.sha256(blob).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", metavar="OUT")
    args = ap.parse_args()

    t_total = time.monotonic()
    judge_before = dir_hash(HERE)
    sys.path.insert(0, HERE)
    import task                                      # noqa: E402

    model_config_path = os.path.join(MODEL_DIR, "config.json")
    model_weights = os.path.join(MODEL_DIR, "model.safetensors")
    model_config = None
    if os.path.isfile(model_config_path):
        model_config = json.load(open(model_config_path))
    else:
        print(f"_grade.py: note: {MODEL_DIR} missing; eval gates need the "
              "pinned base model (run judge/setup.sh)", file=sys.stderr)

    work = tempfile.mkdtemp(prefix="grade-")
    gates = {}
    try:
        art = os.path.join(work, "artifact")
        unpack_artifact(args.artifact, art)

        cfg, metrics, rows = check_structure(art, gates, model_config)
        check_leakage(rows, task, gates)
        check_loss_curve(metrics, gates)
        check_adapter_file(art, gates)

        adapter_sha = None
        st_path = os.path.join(art, "adapter", "adapter_model.safetensors")
        if os.path.exists(st_path):
            adapter_sha = sha256_file(st_path)

        eval_error = fin_acc = base_acc = None
        eval_wall = {"finetuned_s": None, "baseline_s": None}
        cheap_ok = all(gates[g]["pass"] for g in
                       ("structure", "leakage", "adapter_file"))
        if cheap_ok:
            if not model_config:
                eval_error = (f"pinned base model missing at {MODEL_DIR}; "
                              "run judge/setup.sh")
            else:
                try:
                    import torch                             # noqa: PLC0415
                    from transformers import (               # noqa: PLC0415
                        AutoModelForCausalLM, AutoTokenizer)
                    torch.manual_seed(args.seed)
                    torch.set_num_threads(EVAL_THREADS)
                    model = AutoModelForCausalLM.from_pretrained(
                        MODEL_DIR, dtype=torch.float32, local_files_only=True)
                    tok = AutoTokenizer.from_pretrained(
                        MODEL_DIR, local_files_only=True)
                    if tok.pad_token is None:
                        tok.pad_token = tok.eos_token
                    tok.padding_side = "left"
                    from peft import PeftModel               # noqa: PLC0415
                    try:
                        model = PeftModel.from_pretrained(
                            model, os.path.join(art, "adapter"))
                        gates["adapter_file"]["peft_load"] = "ok"
                    except Exception as exc:                 # noqa: BLE001
                        eval_error = f"peft could not load adapter: {exc}"
                        gates["adapter_file"]["peft_load"] = f"error: {exc}"
                        gates["adapter_file"]["pass"] = False
                    model.eval()
                    test = task.test_set()
                    prompts = [task.prompt(x) for x, _ in test]
                    answers = [a for _, a in test]
                    if eval_error is None:
                        ev = Evaluator(model, tok, task, args.seed,
                                       sha256_file(model_weights))
                        t0 = time.monotonic()
                        _, fin_acc = ev.run(prompts, answers, adapter_sha,
                                            True)
                        eval_wall["finetuned_s"] = round(
                            time.monotonic() - t0, 1)
                        t0 = time.monotonic()
                        _, base_acc = ev.run(prompts, answers, None, False)
                        eval_wall["baseline_s"] = round(
                            time.monotonic() - t0, 1)
                except Exception as exc:                     # noqa: BLE001
                    eval_error = f"eval could not run: {exc}"
            gates["accuracy"] = {
                "pass": fin_acc is not None and fin_acc >= 0.90
                        and fin_acc - base_acc >= 0.30,
                "finetuned_accuracy": fin_acc,
                "baseline_accuracy": base_acc,
                "rule": "finetuned >= 0.90 and finetuned - baseline >= 0.30",
                "eval_error": eval_error,
            }
            gates["adapter_control"] = {
                "pass": fin_acc is not None and base_acc is not None
                        and base_acc <= fin_acc - 0.30,
                "detached_accuracy": base_acc,
                "rule": "detached <= finetuned - 0.30",
                "eval_error": eval_error,
            }
        else:
            failed = [g for g in ("structure", "leakage", "adapter_file")
                      if not gates[g]["pass"]]
            for g in ("accuracy", "adapter_control"):
                gates[g] = {"pass": False, "evaluated": False,
                            "reason": f"not evaluated: gate(s) {failed} "
                                      "failed; the verdict already fails"}

        judge_intact = dir_hash(HERE) == judge_before
        gate_ok = all(v.get("pass") is True
                      for v in gates.values())
        verdict = {
            "artifact": os.path.basename(os.path.normpath(args.artifact)),
            "artifact_adapter_sha256": adapter_sha,
            "seed": args.seed,
            "base_model": {
                "id": BASE_MODEL_ID,
                "safetensors_sha256": sha256_file(model_weights)
                if os.path.isfile(model_weights) else None},
            "gates": gates,
            "accuracy": {
                "baseline_accuracy": base_acc,
                "finetuned_accuracy": fin_acc,
                "gain": (fin_acc - base_acc)
                        if fin_acc is not None and base_acc is not None
                        else None,
                "claimed_in_metrics": {
                    k: (metrics or {}).get(k) for k in
                    ("train_accuracy", "baseline_accuracy",
                     "finetuned_accuracy")},
            },
            "judge_intact": judge_intact,
            "timing": {"total_s": round(time.monotonic() - t_total, 1),
                       **eval_wall},
            "pass": gate_ok and judge_intact,
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(json.dumps(verdict, indent=2, sort_keys=True))
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    raise SystemExit(0 if verdict["pass"] else 1)


if __name__ == "__main__":
    main()
