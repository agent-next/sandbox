# gpu-llm-batch-eval — reproduction report

Status: **(not done: needs a different agent in a fresh sandbox)**.

Per `cookbook/DEMO-STANDARD.md`, an independent reproduction is done by a
different agent, from a different model family, following only `README.md`
in a fresh sandbox, with its numbers recorded here and compared against
`RECEIPT.md` within the tolerances in `SPEC.md`.

What a reproducing agent needs to run, in order, from a fresh sandbox:

```bash
git clone --depth 1 -b <ref> https://github.com/agent-next/sandbox
cd sandbox/cookbook/gpu-llm-batch-eval
time bash judge/setup.sh
time bash judge/selftest.sh
time bash judge/grade.sh examples/good/bundle.json --json /tmp/v.json
```

What must match `RECEIPT.md`:

- `judge/selftest.sh` prints the same kill rate (11/11 = 100 %) and
  `selftest: ok`, exit 0.
- `judge/grade.sh examples/good/bundle.json` exits 0 and its verdict has
  `judge_intact: true` and all four gates `pass: true`. The verdict is
  deterministic apart from the `timing` key, so a diff of two verdicts
  with `timing` removed must be empty.
- `judge/setup.sh` installs the exact versions in `judge/requirements.lock`
  (torch 2.10.0+cpu, transformers 4.57.6, and the pinned transitive set);
  `judge/VERSIONS.txt` is regenerated with the same versions.
- The good bundle's measured numbers (`judge_accuracy`, `untruncated_fraction`,
  `derived_tok_s`) are properties of the committed bundle and the pinned
  problems, so they must reproduce **exactly**, not within a tolerance:
  the judge reads a file, it does not re-run the model. A difference means
  the judge or `problems.json` changed, which is itself the finding.

The generation numbers (`wall_time_s`, `throughput_tok_s` of the good run)
are **not** expected to reproduce: they were measured on this builder's
machine and are reported under a device-plausible gate rather than a fixed
value. A reproducer that re-runs `examples/good/eval.py` will get a
different rate on different hardware; that is expected and is why the gate
is a plausibility check, not an equality check.
