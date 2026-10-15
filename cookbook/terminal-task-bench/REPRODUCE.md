# REPRODUCE — `cookbook/terminal-task-bench/`

Independent reproduction by a different agent, following only `README.md`.

**RUN-B is a second fresh-sandbox run on this branch** (purged `sqlite3`,
then `judge/setup.sh` → `judge/grade.sh` → `judge/selftest.sh`). Its verdict
is byte-identical to RUN-A's with `timing` stripped — see `RECEIPT.md` for
the pasted output and the `A == B (timing stripped): True` comparison.

## What to run

From a fresh sandbox, with only README.md in hand:

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/terminal-task-bench/run.py
```

and, if reproducing the numbers by hand rather than through `run.py`:

```bash
bash cookbook/terminal-task-bench/judge/setup.sh
bash cookbook/terminal-task-bench/judge/selftest.sh
bash cookbook/terminal-task-bench/judge/grade.sh \
     cookbook/terminal-task-bench/examples/good --json /tmp/v.json
```

## What must match, and the tolerance

| quantity | RECEIPT value | tolerance |
|---|---|---|
| `judge/setup.sh` exit | 0 | must be 0 |
| sqlite3 installed | 3.40.1-2+deb12u2 | exact |
| `judge/grade.sh` exit | 0 | must be 0 |
| G1 solved | 10/10 | exact |
| G2 pristine trees rejected | 10/10 | exact |
| G3 negative control | 0/10 | exact |
| G5 judge sha256 before == after | yes | exact |
| verdict JSON, `timing` stripped | (see RECEIPT) | **byte-identical** |
| kill rate | 12/12 = 100 % | ≥ 90 % |
| wall times | 3.0 s verify, 10 s grade, 100 s selftest | any |

Per SPEC.md the only accepted difference between two runs is wall time:
`grade.sh` twice on the same seed must produce byte-identical verdict JSON
once the `timing` key is removed, and `selftest.sh` checks exactly that. If
any other number differs, that is a bug in the demo, not a tolerance.

## Record here

- sandbox id and shape (vCPU / RAM):
- `judge/setup.sh` exit and `judge/VERSIONS.txt`:
- `judge/grade.sh` exit, G1/G2/G3/G5:
- `judge/selftest.sh` exit and kill rate:
- the two verdict JSONs, `diff`ed after removing `timing`:
- anything that did not match, and how it was explained or fixed:
