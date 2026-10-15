# gpu-batch-transcribe — batch callsign transcription, judged

An agent writes a batch transcriber for a simulated tower-logs channel —
20 flights spelling their callsigns letter by letter in the ICAO
alphabet over a noisy FSK tone channel — and a judge it cannot fool
decides whether the transcripts are right. The transcriber never sees
the answer key: the judge hands it only the audio and the signal
parameters, and the oracle texts live in `judge/manifest.json`, which
never leaves the judge's directory.

Why a sandbox helps: the whole thing is disposable and reproducible.
`run.py` creates a fresh agent-next sandbox, clones the repo at your
`--ref`, installs the pinned judge toolchain (torch 2.14.0, numpy 2.4.3,
sha256-checked), regenerates and digest-verifies the audio corpus, runs
the judge self-test (known-good passes, 10/10 scripted mutants killed),
then grades the known-good transcriber and prints the verdict JSON — and
always kills the sandbox afterwards. The same artifact runs on CPU or on
a GPU lease (`--gpu`): the decode is one batched complex matmul over
every burst of every utterance, so a GPU grades it in one GEMM.

## Ask your agent

> In `cookbook/gpu-batch-transcribe/`, read SPEC.md and build the batch
> transcriber `examples/good/transcriber.py`: read `manifest.json` (the
> tone grid and signal parameters) and every `utt_*.npy` beside it, find
> the push-to-talk onset, walk the 60 ms burst clock, and decode each
> letter from its row+column tone pair — batching ALL bursts of ALL
> utterances into one complex matmul. Write `transcripts.json` with every
> utterance id and its decoded tokens. Then run `judge/selftest.sh` and
> `judge/grade.sh` on it until every gate passes.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/gpu-batch-transcribe/run.py --ref <branch>
```

- Exit 0 with an all-gates-pass verdict JSON and a human summary; any
  failing step (setup, selftest, grade) exits non-zero, naming the
  sandbox id if cleanup could not be confirmed.
- `--gpu` grades the same artifact on a 1 GiB VRAM slice over the REST
  lease API (`api.sbx.agent-next.com`) — the decode matmul runs as one
  CUDA GEMM; the transcript is identical to the CPU run.
- `--keep` leaves the sandbox up and prints its id.

## What the judge checks

| gate | rule |
|---|---|
| structure | ≤ 128 KiB, byte-compiles, defines `decode_batch`, reads the manifest at runtime, no oracle literals pasted in |
| run | runs on the whole corpus, writes `transcripts.json` |
| shape | every utterance present, non-empty, tokens in the ICAO grid vocabulary |
| accuracy | ≥ 98 % exact matches and WER ≤ 0.02 vs the oracle texts |
| determinism | a second run gives byte-identical transcripts |
| judge intact | sha256 of `judge/` unchanged after grading |

The self-test is mandatory and proves the judge fails on bad inputs:
10/10 single-edit mutants of the good transcriber are killed (kill rate
100 % — see `judge/mutants.py`), including pasted oracle tokens and
delegation attempts.

## Measured wall time (CPU sandbox, this repo's CI image)

| step | wall time |
|---|---|
| `sbx create` | ~3 s |
| clone (depth 1) | ~5 s |
| `judge/setup.sh` (torch 2.14.0+cpu install + corpus regen) | ~90 s |
| `judge/selftest.sh` (1 good + 10 mutants + determinism pair) | ~110 s |
| `judge/grade.sh` good artifact (2 runs for determinism) | ~20 s |
| total `run.py` | ~4 min |

Limits, plainly: the corpus is 20 utterances, 110 tokens, 21 s of audio
(~880 KB); the artifact must be ≤ 128 KiB and stdlib+numpy+torch only;
grading a mutant that hangs is bounded by a 1800 s timeout per run.
GPU lease time is billed per second; `--gpu` holds the lease for about
a minute. Numbers for the exact runs behind this table are in
RECEIPT.md, reproduced side by side from two fresh sandboxes.
