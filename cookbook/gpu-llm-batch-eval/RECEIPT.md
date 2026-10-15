# gpu-llm-batch-eval — receipt

Real output from this builder sandbox (Debian, x86-64, 2 vCPU, ~3.8 GB
RAM, no GPU, CPython 3.12.15). Commands run from
`cookbook/gpu-llm-batch-eval/`; wall times from `time` around each whole
command. The judge is CPU-only by design, so every grading number below
was measured on this machine.

**The GPU run did not happen from this sandbox and nothing below claims
it did.** Every request to the sandbox gateway (`POST /sandboxes` with
`{"accel": ...}`, `GET /v0/usage`, even `POST /mcp/v1` `tools/list`)
answered `{"code":401,"message":"invalid API key"}` with the
`$SBX_API_KEY` this sandbox was given, on every endpoint, retried over
~50 minutes (curl and Python urllib, `X-API-Key` and `Authorization:
Bearer`). The key is prefixed `e2b_` and 44 bytes long, so it is formatted
like a tenant key; the gateway just rejects it. Without a lease there is
no GPU run, and a CPU run of the real artifact was measured at **0.35
tok/s** batch-8 steady-state on this machine (pinned torch, 2 threads) —
about 20 h for 100 × 256-token problems, which does not fit any sane
budget. The lead should run `python3 cookbook/gpu-llm-batch-eval/run.py
--gpu` with a working key; it overwrites the committed good bundle.

## The committed good bundle is a fixture

Because neither path to a real bundle existed, the committed
`examples/good/bundle.json` is a **deterministic hand-written fixture**
(the standard allows the known-good example to be "written by hand"),
generated with seed 42: fabricated step-by-step generations with
intermediate numbers, whose final answers are gold for 34/100 problems.
Its `provenance` field says this inside the file itself. It is a
judge-mechanics proof, not a model result: every gate runs on it, all 11
mutants of it are killed, and two grades of it are byte-identical apart
from `timing`. `judge/floor.txt` (0.20) is the fixture's measured
accuracy (0.34) minus a margin, so the floor is measured, not quoted —
but it is measured *on the fixture*, and RECEIPT will be updated with the
GPU run's number when `--gpu` is executed with a working key.

## Run 1 (fresh venv) — bash judge/setup.sh

```
$ time bash judge/setup.sh
setup.sh: creating venv at /home/user/.venvs/gpu-llm-batch-eval
[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run 'python3 -m pip install --upgrade pip'
setup.sh: ok

real  3m59.118s
user  1m34.979s
sys   0m16.049s
exit=0
```

`judge/VERSIONS.txt` after the fresh install: python 3.12.15,
torch 2.10.0+cpu, transformers 4.57.6, and the pinned transitive set of
`judge/requirements.lock` (all enforced by pip `--require-hashes`; pip
prints `Using cached`/download lines for every wheel, trimmed here — the
full pin list with sha256 hashes is the lock file itself).

## Run 2 (venv deleted, fresh again) — setup is idempotent and re-verifiable

The venv was deleted (`rm -rf ~/.venvs/gpu-llm-batch-eval`) and setup
re-run inside a fresh `git clone --depth 1` of this branch:

```
$ time bash judge/setup.sh        # fresh clone, venv recreated
setup.sh: creating venv at /home/user/.venvs/gpu-llm-batch-eval
setup.sh: ok
real  3m39.083s

$ time bash judge/setup.sh        # second call, nothing to do
setup.sh: venv already provides the pinned toolchain
setup.sh: ok

real  0m29.205s
user  0m15.626s
sys   0m1.930s
exit=0
```

Both fresh installs produced the same `judge/VERSIONS.txt` versions.

## bash judge/selftest.sh

```
$ time bash judge/selftest.sh
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant first_number: killed (gate: judge_accuracy)
selftest: mutant inflated_accuracy: killed (gate: judge_accuracy)
selftest: mutant deflated_accuracy: killed (gate: judge_accuracy)
selftest: mutant truncated: killed (gate: generations,judge_accuracy)
selftest: mutant misaligned: killed (gate: generations,judge_accuracy,structure,token_accounting)
selftest: mutant nondeterministic: killed (gate: generations,judge_accuracy,structure,token_accounting)
selftest: mutant invented_throughput: killed (gate: token_accounting)
selftest: mutant cpu_claimed_as_gpu: killed (gate: token_accounting)
selftest: mutant gpu_rate_on_cpu: killed (gate: token_accounting)
selftest: mutant empty_generation: killed (gate: generations,judge_accuracy,structure,token_accounting)
selftest: mutant bad_hash: killed (gate: generations,judge_accuracy,structure,token_accounting)
selftest: kill rate: 11/11 = 100%
selftest: determinism check (two grades of the good bundle)
selftest: determinism: OK
selftest: ok

real  0m4.070s
user  0m1.841s
sys   0m0.656s
exit=0
```

## bash judge/grade.sh examples/good/bundle.json --json /tmp/v.json

```
$ time bash judge/grade.sh examples/good/bundle.json --json /tmp/v.json
{
  "artifact": "bundle.json",
  "floor": 0.2,
  "gates": {
    "generations": {
      "max_new_tokens": 256,
      "pass": true,
      "problems": [],
      "truncated": 0,
      "untruncated_fraction": 1.0
    },
    "judge_accuracy": {
      "correct": 34,
      "extractor_disagreements": 0,
      "judge_accuracy": 0.34,
      "n": 100,
      "pass": true,
      "problems": [],
      "reported_accuracy": 0.34,
      "unparsed": 0
    },
    "structure": {
      "pass": true,
      "problems": []
    },
    "token_accounting": {
      "derived_tok_s": 4.1676,
      "device": "cpu",
      "device_floor_tok_s": 0.2,
      "pass": true,
      "problems": [],
      "rel_error": 0.00010638,
      "reported_tok_s": 4.168
    }
  },
  "judge_changed": [],
  "judge_intact": true,
  "seed": 0,
  "timing": {
    "grade_s": 0.012
  }
}

real  0m0.235s
user  0m0.090s
sys   0m0.043s
exit=0
```

## run.py's in-sandbox command sequence, run directly

Per the build brief, `run.py` cannot create sandboxes from inside this
sandbox, so its exact `sbx exec` step sequence was run by hand against a
fresh clone of this branch (`git clone --depth 1 -b
sbx/demo-gpu-llm-batch-eval`), plus `python3 -m py_compile run.py` (OK).
All steps: clone ~3 s, setup (fresh venv) 3m39 s, selftest 0.17 s warm
/ 4.7 s cold, grade `exit=0`, verdict `all gates pass: True`,
`judge_accuracy: 0.34` — the same numbers as above, from the same
committed bundle.

## GPU path — (not done: gateway 401 on every endpoint; no lease could be created)

`python3 cookbook/gpu-llm-batch-eval/run.py --gpu` is written and ready:
pinned weights + problems downloaded locally (sha256 recorded in
`judge/MODEL.txt`; the weights digest equals the repo's LFS oid,
`X-Linked-ETag`, so the host that serves the file confirms it), chunked
upload (the files API caps one PUT at 512 MiB; `model.safetensors` is
~988 MB so it travels as <= 400 MiB parts the lease reassembles and
sha256-checks), exec, bundle download from `out/` (downloads read
`<workdir>/out`), then DELETE + GET -> 404/dead in a `finally` block.
It was verified as far as the gateway allows: `python3 -m py_compile`
and a dry read-through against the gateway's published contract
(`/llms-full.txt`). **No lease id exists to log, because no lease could
ever be created** — the first `POST /sandboxes` answered 401. When the
lead runs `--gpu` with a working key, its lease id, deletion confirmation,
GPU wall time, VRAM peak and throughput belong in this section.

## Deviations

- **No real GPU run** (gateway 401, see the header). Every grading number
  in this receipt is real measured output of the CPU judge on the
  committed fixture; no GPU number is claimed anywhere.
- **The good bundle is a hand-written fixture**, not a model output
  (standard permits a hand-written known-good example). Its provenance
  is recorded in the file and in SPEC.md.
- **vLLM not attempted**: no `sm_120` wheel is published for the lease's
  pinned torch and the lease has no network, matching the brief's
  fallback to `transformers`.
- **The floor is fixture-measured** (0.34 − margin = 0.20), not
  model-card- or GPU-run-measured; the model card states no single GSM8K
  test number.
- **Fresh-sandbox reproduction below** is one machine, two fresh venvs,
  not two fresh sandboxes: creating a second sandbox needs the same
  broken key. The full clone→setup→selftest→grade sequence was run
  against a fresh clone both times, so the cold-start path is covered.
- REPRODUCE.md's independent reproduction is still `(not done: needs a
  different agent in a fresh sandbox)`.
