# Batch LLM inference + eval on a GPU slice — SPEC

An agent works on a real ML-engineering problem inside a disposable
agent-next sandbox: run **batched generation** with a small pinned instruct
model over 100 pinned GSM8K test problems, and produce an eval bundle whose
reported numbers a judge on CPU can check. The judge never accepts "the
model ran": it **re-extracts the final numeric answers from the raw
generations itself**, scores them against the official gold answers, and
compares its own accuracy with the accuracy the artifact reports.

The distinguishing feature of this demo is that the grading machine and the
inference machine are different. The heavy step — a batched forward pass over
100 problems — runs on an RTX 5090 VRAM slice lease. The judge runs on plain
CPU threads, reads only the JSON bundle the artifact wrote, and recomputes
accuracy, throughput and every claimed number from the generations
themselves. An artifact that reports an inflated accuracy, or that
misaligns its problems and generations, is caught because the judge's
extraction is independent.

## Goal

- **Artifact**: one Python file, `eval.py`, plus the JSON bundle it writes.
  `eval.py` loads the pinned model from a local directory, generates
  greedy (temperature 0) continuations for the prompt of each of the 100
  problems in `judge/problems.json` with **`transformers` batched
  generation**, and writes `bundle.json`:
  ```json
  {
    "model": "Qwen/Qwen2.5-0.5B-Instruct",
    "problems_sha256": "<sha256 of judge/problems.json>",
    "n_problems": 100,
    "batch_size": 8,
    "max_new_tokens": 256,
    "temperature": 0.0,
    "greedy": true,
    "device": "cuda",
    "throughput_tok_s": 412.3,
    "generated_tokens": 24813,
    "wall_time_s": 60.2,
    "reported_accuracy": 0.31,
    "generations": [
      {"i": 0, "question": "...", "generation": "...", "extracted_answer": "18",
       "max_new_tokens": 254}
    ]
  }
  ```
  Every field is required unless marked optional; extra fields are ignored.
- **Judge**: `judge/grade.sh` validates the bundle's structure, re-extracts
  each final numeric answer from the raw generation text with its own
  extractor, and compares to the gold answer in `judge/problems.json`.
- **Self-test**: `judge/selftest.sh` proves the judge fails known-bad
  bundles: the five failure classes named in the brief plus a
  structure-invalid one.

## Non-goals

- **vLLM.** The brief allows it, but only if a `sm_120` wheel installs
  offline; the lease has no internet, so the whole wheel set would have to
  be uploaded, and no such wheel is published for the pinned torch. This
  demo uses `transformers` batched generation only (see Deviations in
  RECEIPT.md).
- **Training, fine-tuning, quantisation, or speculative decoding.** Greedy
  decoding only; `temperature` must be 0 so a re-run is byte-identical.
- **Any network access from the artifact.** It loads weights from a local
  directory the judge supplies; a bundle produced with the network is not
  reproducible.
- **Grading on GPU.** The judge is CPU-only by construction — it reads a
  JSON bundle and does string work and float compares. This is what keeps
  the grade cheap and the judge's oracle independent of the model.

## The pinned inputs (the agent never sees the answers)

| input | source | licence |
|---|---|---|
| model weights + tokenizer | `Qwen/Qwen2.5-0.5B-Instruct` at commit `7ae557604adf67be50417f59c2c2f167def9a775` (pinned per-file sha256 in `judge/MODEL.txt`) | Apache-2.0 |
| 100 problems | first 100 test rows of GSM8K; the committed `judge/problems.json` *is* the pin (its `source`/`source_commit`/`source_sha256` record the upstream file), and every bundle must echo its sha256 under `problems_sha256` | MIT |
| judge toolchain | `judge/requirements.lock`, hashes enforced by pip | — |

The model card reports GSM8K-style maths results only through the base model
family and does not state a single GSM8K test accuracy number, so the
"sanity floor" gate below is a **measured** floor taken from the good run,
not a claim from the card: see "The good run" below and RECEIPT.md. Because
the committed good bundle is the fixture described there, the floor in
`judge/floor.txt` (0.20) is the fixture's measured accuracy (0.34) minus a
margin; a real GPU bundle that clears the gates must simply exceed it.

## Gates

`judge/grade.sh <artifact-or-bundle> [--seed N] [--json out.json]` prints
one JSON verdict and exits 0 only if every gate passes. All numeric rules
are deterministic and seed-independent except where `--seed` is named.

### Gate 1 — `structure`

The bundle is one JSON object; every required field is present with the
right type; `n_problems == 100`; `len(generations) == 100`; `i` values are
exactly 0..99 with no duplicates; `problems_sha256` equals the sha256 of
`judge/problems.json`; `temperature == 0` and `greedy is true`; each
generation is a non-empty string; each `question` matches the problem text
at index `i` **exactly** (this is the misalignment gate). `generated_tokens`,
`wall_time_s` and `throughput_tok_s` are finite and positive.

### Gate 2 — `judge_accuracy` (the independent oracle)

The judge re-extracts the final numeric answer from each raw generation
with **its own** extractor (`judge/extract.py`), which never reads the
artifact's `extracted_answer` field, and compares it to the gold answer
with numeric equality of the last number in each string (commas stripped,
a trailing `.0` treated as equal to the integer).

Pass rules:
- `judge_accuracy` ≥ **0.20** (measured floor; see below),
- `judge_accuracy ≥ reported_accuracy − 0.5 pt`: the artifact may not claim
  more than half a percentage point of accuracy its own generations do not
  support,
- `judge_accuracy ≤ reported_accuracy + 0.5 pt`: the artifact may not
  understate by more than half a point either (a bundle whose reported
  number is arbitrary in either direction is rejected).

The agreement band is two-sided so that "reported accuracy inflated" and
"reported accuracy deflated" are both failures; the floor is one-sided
because the floor is a property of the model, not of the bundle.

### Gate 3 — `generations` (not truncated, not tampered)

For at least **90 %** of problems the generation must (a) declare a length
strictly below the bundle's `max_new_tokens` — i.e. it ended at the model's
stop condition, not at the cap — and (b) yield an answer under the judge's
extractor. A bundle where the answer was cut off mid-sentence by a tiny
`max_new_tokens` fails, and the gate complains loudly about truncation
rather than silently scoring a short answer as wrong.

**Limit.** The per-generation length is the artifact's own claim: the
judge has no tokenizer, so it cannot recompute the token count and must
trust `max_new_tokens` per generation. This is the one gate where a number
the judge reads is not one it can recompute — an artifact that declares a
small length for a truncated generation can pass gate 3 while its text is
still scored (correctly) by gate 2. It is a completeness signal, not a
tamper-proof one.

### Gate 4 — `token_accounting`

The judge recomputes throughput from the bundle's own numbers:
`generated_tokens / wall_time_s` must equal `throughput_tok_s` within
**1 %**, and the rate must be plausible for the device the bundle claims.
The check is two-sided so both directions of a fabricated timing fail:

- `device` starting with `cuda`/`gpu`: the rate must be **> 50 tok/s**. A
  CPU-rate number on a GPU run means the artifact did not use the
  accelerator, or the timing is invented.
- `device` starting with `cpu`: the rate must be **> 0.2 tok/s** and
  **≤ 1000 tok/s**. A CPU run cannot reach GPU rates, so a rate above the
  ceiling is an invented timing wearing a `"cpu"` label.

This is the one gate whose rule depends on the artifact's own claim, which
is why it is two-sided: a bundle can lie about the device in either
direction, and only one of the two lies is caught by a floor alone.

### Gate 5 — `judge_intact`

sha256 of every file in `judge/` is unchanged across the grade (the artifact
cannot edit its own judge), and the artifact is graded from a copy in a
fresh temp directory so it cannot see or write `judge/`.

## The acceptance oracle

There is no "the tool ran" pass anywhere. The oracle chain is:

1. **Independent extraction.** The judge's extractor is written from the
   task definition (the final numeric answer of a GSM8K solution), not from
   the artifact's answer field. Two extractors disagreeing is itself a
   signal the judge reports as a per-problem field.
2. **Gold answers from the pinned data file**, not from the model.
3. **A measured floor, not a model-card claim.** The floor in gate 2 is the
   accuracy measured on the good run in RECEIPT.md, minus a margin. It is
   recorded in `judge/floor.txt` and checked by the self-test's determinism
   gate, so a silent change of the floor is visible.
4. **Self-consistency** of the reported numbers (gates 2 and 4).

## The good run

`examples/good/` contains `eval.py` and a `bundle.json`. `eval.py` is the
real artifact: it loads the pinned model from a local directory, runs
batched greedy generation with `transformers`, and writes the bundle.
`run.py --gpu` runs it on a VRAM slice lease end to end (pinned downloads,
sha256-checked uploads, exec, bundle download, lease destroyed and
confirmed gone) and overwrites `examples/good/bundle.json` with the result.

The committed `bundle.json` is a **hand-written fixture** (the standard
allows the known-good example to be "written by hand or from a cited
public source"), because the build sandbox could not reach a GPU lease
(gateway 401 on every endpoint) and its 2 vCPU generate at ~0.35 tok/s,
so a real run would take ~20 h. The fixture is generated by a
deterministic script and is a judge-mechanics proof, not a model result:
its generations are fabricated step-by-step solutions whose final answers
are gold for 34/100 problems, with intermediate numbers so the
`first_number` mutant genuinely disagrees. Its `provenance` field says so
in the file itself. The judge ignores that field; a real GPU bundle
overwrites the fixture wholesale. RECEIPT.md records the whole story.

## Determinism

Greedy decoding with temperature 0 on a fixed model and fixed prompts is
deterministic given the same library versions and the same GPU
architecture; fp32 matmuls on the same shape are reproducible run to run on
the same device. The bundle records the model commit sha and the problems
sha256 so a different combination is detectable. `grade.sh` is itself
deterministic: it does only string and float work, so two grades of the same
bundle give byte-identical verdicts. `selftest.sh` checks that.

Wall time and throughput are **not** required to reproduce exactly — they
are reported under the `timing` key, which the determinism check excludes.
