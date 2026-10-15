# post-2109129990029930805 — <one-line hero claim: what is built, and the number that proves it>

<one paragraph: what the agent does inside a disposable agent-next
sandbox, what the judge checks, and why the judge cannot be fooled by
"<the thing> merely ran".>

**Hero result:** <the single measured number the video opens on, e.g.
"sigma 138 <= 167 MPa, mass 5.65 kg" — must trace to RECEIPT.md>.

## Results

![<what the key figure shows>](media/result.png)
![<agent loop + self-test matrix>](media/loop.png)

[media/demo.mp4](media/demo.mp4) — <duration> s: <one line on the
storyboard arc: hook -> input/output -> escalation -> proof -> end card>.

## Ask your agent

> Clone https://github.com/agent-next/sandbox into this sandbox and run
> `bash cookbook/post-2109129990029930805/judge/setup.sh`. <Then: what artifact to
> produce and the contract it must satisfy — point at SPEC.md. Then run
> `judge/grade.sh <artifact>` and iterate until it prints `"PASS"`.>

## One-command run

```bash
python3 run.py            # clones this repo at main into a fresh sandbox
python3 run.py --ref my-branch --keep
```

Needs the `sbx` CLI (`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` (or `E2B_API_KEY`) in the environment.

Measured on a <N> vCPU / <N> GB sandbox (see RECEIPT.md):

| step | wall time |
|---|---|
| setup | <s> |
| selftest (<n> mutants + determinism) | <s> |
| grade the good artifact | <s> |
| **time-to-result (README -> hero)** | <s> — target < 5 min CPU / < 10 min GPU |

## How the judge works

- `judge/setup.sh` — <what it installs, pinned how>.
- `judge/grade.sh <artifact>` — <the gates and their numeric pass rules>.
- `judge/selftest.sh` — <kill rate, determinism check>.

## Limits

- <what this demo does not cover, stated plainly>
