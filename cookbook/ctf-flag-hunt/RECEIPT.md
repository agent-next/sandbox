# RECEIPT — `cookbook/ctf-flag-hunt/`

Real command output, pasted as produced. The runs below were produced by
the committed code on this branch, in a Debian sandbox (2 vCPU, ~4 GB RAM)
at this repo's working tree. Every `judge/setup.sh` run below started from
nothing: the pinned `gcc-12` package was purged first
(`sudo apt-get purge -y gcc-12`), so setup did the sha256-checked download
and install each time.

## Two fresh-setup runs side by side

| | RUN-B | RUN-C |
|---|---|---|
| `judge/setup.sh` | exit 0, 32.7 s (download + install) | exit 0, 28.9 s (download + install) |
| `judge/selftest.sh` | exit 0, 44.2 s | exit 0, 43.2 s |
| `judge/grade.sh examples/good --json …` | exit 0, 4.5 s | exit 0, 6.7 s |
| sha256 of `.deb` download | `b46f33cc…0360e49d` OK (`sha256sum -c`) | same, OK |
| gcc installed | 12.2.0-14+deb12u1 | 12.2.0-14+deb12u1 |
| kill rate | **7/7 = 100 %** | **7/7 = 100 %** |
| determinism (two `--seed 1` runs) | identical except `timing` | identical except `timing` |
| verdict JSON | identical to RUN-C (see below) | identical to RUN-B |
| `flags.captured` | 5/5 | 5/5 |
| `oracle.passed` | 5/5 | 5/5 |
| `negative_control.captured` | 0/5 | 0/5 |
| `negative_control.sweep_hits` | 0 | 0 |
| `blast_radius` | clean (added/removed/changed all empty) | clean |

`diff` of the two verdict JSONs with the `timing` key removed → **no
differences**; both fresh runs reproduce byte-identically. (A third fresh
run, RUN-A, agreed with them as well.)

## RUN-B: `judge/setup.sh` (from a purged state)

```text
$ sudo apt-get purge -y -qq gcc-12
$ bash judge/setup.sh
setup: downloading gcc-12 12.2.0-14+deb12u1 from Debian pool
/tmp/tmp.0Lje64ceLl/gcc-12.deb: OK
Selecting previously unselected package gcc-12.
Preparing to unpack .../gcc-12_12.2.0-14+deb12u1_amd64.deb ...
Unpacking gcc-12 (12.2.0-14+deb12u1) ...
Setting up gcc-12 (12.2.0-14+deb12u1) ...
setup: tool versions
gcc-12 (Debian 12.2.0-14+deb12u1) 12.2.0
gcc-12 debian package: 12.2.0-14+deb12u1
Python 3.12.15
setup: wrote <demo>/judge/VERSIONS.txt
setup: done
```

`judge/VERSIONS.txt` after that run:

```text
# ctf-flag-hunt judge: versions installed by judge/setup.sh
# (Linux x86_64)
gcc-12 12.2.0
gcc-12 debian package: 12.2.0-14+deb12u1
python3 3.12.15
```

## RUN-A: `judge/selftest.sh`

```text
$ bash judge/selftest.sh
selftest: grading known-good <demo>/examples/good
selftest: known-good PASSED all gates
mutants: offbyone-fixed/  edit notes.c: closes the off-by-one: no id reaches the flag
mutants: traversal-fixed/  edit retrieve.c: rejects any name containing ..: the traversal no longer escapes
mutants: token-secret/  edit token.c: mixes in a secret constant: the token is no longer forgeable
mutants: status-leak/  edit status.c: leaks the flag on the legitimate `status version` path
mutants: admin-mode-fixed/  edit admin.c: rejects a non-numeric mode instead of falling into 0
mutants: flag-baked/  edit status.c: a flag-shaped string baked into the source: the sweep catches it
mutants: writes-a-file/  edit retrieve.c: logs every request to a file: the blast-radius gate catches it
mutants: wrote 7 mutants to /tmp/tmp.BygmVy8NAq/mutants
selftest: killed    admin-mode-fixed (gate: flags)
selftest: killed    flag-baked (gate: negative_control)
selftest: killed    offbyone-fixed (gate: flags)
selftest: killed    status-leak (gate: oracle)
selftest: killed    token-secret (gate: flags)
selftest: killed    traversal-fixed (gate: flags)
selftest: killed    writes-a-file (gate: blast_radius)
selftest: kill rate 7/7 = 100%
selftest: determinism OK (two --seed 1 runs identical except timing)
selftest: OK
```

Exit code 0; wall time 29.7 s. The seven mutants are one single-line edit
each; every gate that the SPEC claims can fail is exercised by at least one
mutant (flags ×4, oracle ×1, negative-control sweep ×1, blast-radius ×1).

## RUN-A: `judge/grade.sh examples/good --json /tmp/runA_verdict.json`

```text
$ bash judge/grade.sh examples/good --json /tmp/runA_verdict.json ; echo "exit $?"
{
  "artifact": "examples/good",
  "demo": "ctf-flag-hunt",
  "gates": {
    "blast_radius": {
      "added": [], "changed": [], "files_after": 6, "files_before": 6,
      "passed": true, "removed": []
    },
    "build": {
      "compiled": ["notes", "retrieve", "token", "status", "admin"],
      "errors": {}, "missing": [], "passed": true, "warnings": {}
    },
    "flags": {
      "captured": 5,
      "matches": {"c1": true, "c2": true, "c3": true, "c4": true, "c5": true},
      "required": 5,
      "planted_sha256": {
        "c1": "b44bc9d5703e374d398252861549cbf74089cb1fe07de3d18f5eb2322773f35f",
        "c2": "9da7c7040baec0f3e836984b8dd8122f2c1a615ca420668fc2f43206ac2f7fe7",
        "c3": "6bb2c5216648296aeabc4919c8cac0685bdd76978d4cb7d0d519ee368a564b21",
        "c4": "d6695f001e7d01f5a62764d0ae34ef218055c1decbf211c9894d0e7e6caffdce",
        "c5": "fa29e8cb36801e84947535fe7aa15f69ac94e2f2fe7ca429c1a8579e60be21fc"
      },
      "sha256": {
        "c1": "b44bc9d5703e374d398252861549cbf74089cb1fe07de3d18f5eb2322773f35f",
        "c2": "9da7c7040baec0f3e836984b8dd8122f2c1a615ca420668fc2f43206ac2f7fe7",
        "c3": "6bb2c5216648296aeabc4919c8cac0685bdd76978d4cb7d0d519ee368a564b21",
        "c4": "d6695f001e7d01f5a62764d0ae34ef218055c1decbf211c9894d0e7e6caffdce",
        "c5": "fa29e8cb36801e84947535fe7aa15f69ac94e2f2fe7ca429c1a8579e60be21fc"
      }
    },
    "negative_control": {
      "captured": 0, "leaked_by": {}, "passed": true, "required": 0,
      "sweep_hits": [], "sweep_required": 0
    },
    "oracle": {
      "checks": {"c1": true, "c2": true, "c3": true, "c4": true, "c5": true},
      "detail": {
        "c1": "in-bounds[0]='note-0-25734332' oob='error'",
        "c2": "served='public doc e5d466e2' direct='public doc e5d466e2'",
        "c3": "printed_matches_recomputed=True accepts_judge_token=True rejects_stale=True",
        "c4": "version='version=1.4.2' build='build=r2026'",
        "c5": "modes 1/2 -> ['mode=1 content=denied', 'mode=2 content=denied']"
      },
      "passed": 5, "required": 5
    }
  },
  "passed": true,
  "seed": 20261015,
  "timing": {
    "blast_radius_s": 0.009, "build_s": 3.733, "c3_forge_t": 1792031655,
    "exploit_s": 0.245, "total_s": 3.999
  }
}
exit 0
```

Key numbers: flags **5/5**, oracle **5/5**, negative control **0/5** with
**0** sweep hits, blast radius **clean**, grade wall time **5.2 s**.

## In-sandbox command sequence (run.py, verified without a sandbox)

`run.py` cannot create a sandbox from inside a sandbox, so its in-sandbox
command sequence was run directly from a fresh `git clone` of this branch:

```text
$ git clone --depth 1 -b sbx/demo-ctf-flag-hunt <repo> ctf-demo-repo
$ cd ctf-demo-repo/cookbook/ctf-flag-hunt
$ bash judge/setup.sh && bash judge/selftest.sh && bash judge/grade.sh examples/good --json /tmp/verdict.json
...
selftest: kill rate 7/7 = 100%
passed= True flags= 5
```

`run.py` itself passes `python3 -m py_compile`. The lead runs it end to end
against a real sandbox.

## Deviations

- **No `media/`, no `REPRODUCE.md`.** This task scopes media to a later
  task and does not include the independent reproduction pass. Both are
  listed as `(not done)` rather than claimed.
- **The judge does not sandbox the services.** Each service is a local
  process the judge invokes; a malicious artifact could in principle do
  anything the judge's user can. The judge guards *itself* (it grades from
  a temp copy and re-checks the `judge/` tree's sha256 before and after),
  but it does not confine the artifact — out of scope per SPEC non-goals.
- **`gcc-12`, not `gcc`.** A fresh install of the pinned package provides
  `/usr/bin/gcc-12` but not the `/usr/bin/gcc` symlink (that comes from a
  different package), so the judge names the compiler explicitly. Found by
  the fresh-install runs, not by inspection.
- **C1 is a logical out-of-bounds read**, not memory corruption: no ASLR or
  stack layout is involved. The SPEC says so explicitly so the judge's
  determinism does not depend on a particular compiler's memory layout.
