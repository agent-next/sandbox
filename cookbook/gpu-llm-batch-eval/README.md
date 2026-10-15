# gpu-llm-batch-eval — an eval a judge can check

An agent runs **batched LLM inference and an eval** on a GPU slice: a small
pinned instruct model, greedy decoding over 100 pinned GSM8K test problems,
and a JSON bundle reporting accuracy and throughput. The point of the demo
is that the machine that *generates* and the machine that *grades* are
different. The heavy step runs on an RTX 5090 VRAM slice lease; the judge
runs on plain CPU threads, reads only the bundle, and **re-extracts the
final numeric answer from every raw generation with its own extractor**
before it scores anything. A bundle whose reported accuracy is inflated, or
whose problems are misaligned against its generations, or whose throughput
is a CPU rate wearing a `"device": "cuda"` label, is caught — because the
judge never trusts a number the artifact wrote about itself.

A disposable sandbox is the right place for this: the agent needs a GPU it
can trash, a multi-gigabyte weight download it should not keep, and a
throwaway filesystem to iterate the eval script in. The graded artifact is
one small file it hands back.

## Results

Key numbers from the judge verdict on the committed good bundle
(`examples/good/bundle.json` — a hand-written fixture; see the honesty note
below and RECEIPT.md):

| gate | measured | rule |
|---|---|---|
| structure | pass | 100 problems, aligned, `temperature 0`, `greedy` |
| judge_accuracy | 0.34 (34/100) | ≥ floor 0.20, and within 0.5 pt of reported |
| generations | 100 % complete | ≥ 90 % below the token cap |
| token_accounting | 4.17 tok/s on `cpu` | within 1 % of tokens/wall, device-plausible |
| self-test kill rate | 12/12 = 100 % | ≥ 90 % |

**Honesty note.** The committed bundle is a deterministic hand-written
fixture, not a model run: the build sandbox's gateway key was rejected
(401) so no GPU lease could be created, and its 2 vCPU would need ~20 h
for 100 problems. The fixture proves the judge's mechanics end to end
(its 12 mutants are all killed); `run.py --gpu` produces the real bundle
and overwrites the fixture. Every number in the table is pasted from a
real judge run in `RECEIPT.md`.

`media/` is produced by a later task.

## Ask your agent

> Set up a sandbox and solve the demo in `cookbook/gpu-llm-batch-eval/` of
> https://github.com/agent-next/sandbox (clone it first). Run
> `bash cookbook/gpu-llm-batch-eval/judge/setup.sh`, then read
> `cookbook/gpu-llm-batch-eval/SPEC.md`. Design the artifact yourself: a
> Python file `eval.py` that loads the pinned model from a local directory,
> generates a greedy (temperature 0) continuation for each of the 100
> problems in `judge/problems.json` with `transformers` batched generation,
> and writes `bundle.json` with the fields SPEC.md lists — including
> `reported_accuracy`, which must be the accuracy your own generations
> actually support. Iterate with
> `bash cookbook/gpu-llm-batch-eval/judge/grade.sh <your-bundle.json> --json v.json`
> until it exits 0, then paste the final verdict JSON. The judge re-extracts
> every answer itself, so a bundle that reports a number its generations do
> not support will not pass. Do not edit anything under `judge/`; if you
> believe the judge is wrong, say so instead of working around it. Kill the
> sandbox when you are done.

The known-good example in `examples/good/` is a hand-written fixture (see
the honesty note above) whose generations the judge can score end to end; a
working answer does not have to match its accuracy, only clear the gates.
`examples/good/eval.py` is the real artifact to imitate: pinned model from
a local directory, transformers batched greedy generation, and a bundle
whose reported numbers its own generations support.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/gpu-llm-batch-eval/run.py          # --ref main --keep supported
```

Creates a sandbox, clones the repo, installs the pinned tools, runs the
judge self-test, grades `examples/good/bundle.json`, prints the verdict
JSON, then kills the sandbox and confirms it is gone. Stdlib only; exits
non-zero on any failure, naming the sandbox id if cleanup cannot be
confirmed.

`--gpu` runs the *generation* on an RTX 5090 VRAM slice lease instead:
it downloads and sha256-checks the pinned weights and problems locally,
uploads them through the sandbox files API, runs the batched generation on
the lease, downloads the bundle, and deletes the lease in a `finally`
block, confirming the deletion with a `GET` (`404`, or `200` with
`"phase": "dead"`).

## Measured wall time

| step | wall time |
|---|---|
| `git clone --depth 1` | ~3 s |
| `judge/setup.sh` (fresh install, CPU torch + transformers) | ~4 min on 2 vCPU |
| `judge/selftest.sh` (good + 12 mutants + determinism) | ~5 s |
| `judge/grade.sh examples/good/bundle.json` | ~0.4 s |

Grading itself is string and float work over 100 generations — it does not
touch the model, so it is seconds on any machine. `run.py` prints a
per-step timing line.

## Limits, plainly

- **The judge is CPU-only, and that is the design.** It never loads the
  model and never needs a GPU: its oracle is an independent answer
  extractor plus the pinned gold answers, so a CPU laptop can grade a GPU
  run. See SPEC non-goals.
- **vLLM is not used.** The brief allowed it only if an `sm_120` wheel
  installs offline; the lease has no network, so the whole wheel set would
  have to be uploaded, and no such wheel is published for the pinned torch.
  This demo uses `transformers` batched generation. See the Deviations
  section of `RECEIPT.md`.
- **The accuracy floor is measured, not quoted.** The model card does not
  state a single GSM8K test number, so `judge/floor.txt` is the good run's
  measured accuracy minus a margin, and the self-test's determinism gate
  makes a silent change to it visible.
- **Throughput is device-plausible, not device-verified.** The judge checks
  that the rate the bundle reports is consistent with the device it claims
  (a `"cuda"` bundle reporting a CPU rate fails, and so does the reverse),
  but it cannot prove which silicon ran the job. On the GPU lane the lease
  report records the actual device name, VRAM peak and wall time.
- **Greedy decoding is reproducible in principle, not bit-exactly in
  practice.** Different GPU architectures and library versions can pick a
  different token on a tie; the bundle records the model commit and the
  problems sha256 so a different combination is detectable, and the judge
  grades whatever generations it is handed rather than re-running them.
