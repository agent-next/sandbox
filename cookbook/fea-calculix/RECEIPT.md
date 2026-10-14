# Receipt — fea-calculix demo

Real command output. "Fresh-setup run" = everything `judge/setup.sh`
installed was first removed (`apt-get purge` of calculix-ccx and every
package its installation pulled in, plus `rm -rf ~/tools`), then
setup → selftest → grade were run again from that clean state.

Environment: Debian 12 (bookworm) container, 2 vCPU, 3.8 GB RAM —
the same image class the `sbx` sandbox runs.

---

## Hardening

### Pinned downloads (every file sha256-checked)

`judge/setup.sh` no longer takes calculix-ccx from apt by version; it
downloads the exact bookworm `.deb` files from the Debian pool by URL,
checks sha256, and installs the local files:

```
== downloading http://deb.debian.org/debian/pool/main/c/calculix-ccx/calculix-ccx_2.20-1_amd64.deb ==
/tmp/.../calculix-ccx_2.20-1_amd64.deb: OK
== downloading http://deb.debian.org/debian/pool/main/s/spooles/libspooles2.2_2.2-14_amd64.deb ==
/tmp/.../libspooles2.2_2.2-14_amd64.deb: OK
== downloading http://deb.debian.org/debian/pool/main/a/arpack/libarpack2_3.8.0-3_amd64.deb ==
/tmp/.../libarpack2_3.8.0-3_amd64.deb: OK
== downloading https://gmsh.info/bin/Linux/gmsh-4.10.0-Linux64.tgz ==
/tmp/.../gmsh-4.10.0-Linux64.tgz: OK
```

`judge/VERSIONS.txt` (written by `setup.sh` itself):

```
calculix-ccx: 2.20-1 (Debian bookworm .deb, sha256: a448239f3caf5a324f9589a636e595e3e676153489f75843e509decb6809f346)
libspooles2.2: 2.2-14 (Debian bookworm .deb, sha256: 51faa6a5aad9aba20beadffba5d4d9e28fa7a5ef426a1d4fa16c825fd80034a0)
libarpack2: 3.8.0-3 (Debian bookworm .deb, sha256: 949773b357e8f4c74fbc585f2fbee452adb2931c3d36a5baf8eae49f7d45bede)
gmsh: 4.10.0 (official tarball, sha256: 6c7d748e941a6823eeb930fd91a3d46236f752afe2629fe43f61deae562eda95)
python3: 3.12.15
```

### Pinned python dependencies

`judge/requirements.txt` documents that the judge and `run.py` use only
the Python standard library (verified by an AST import scan — exit 0,
`non-stdlib imports: none`); there is nothing to pin on PyPI, and all
third-party binaries carry sha256s in `judge/VERSIONS.txt` / `judge/setup.sh`.

### Setup is idempotent

Re-running `bash judge/setup.sh` on an installed tree: exit 0, zero
re-downloads, 2.6 s wall (vs ~15 s fresh).

### Determinism

`grade.sh` now puts wall time under a `timing` key in the verdict JSON
(judge/judge.py). `selftest.sh` grades the good artifact twice with
`--seed 42` and requires the JSON to be identical except `timing`:

```
== selftest: determinism (grade twice with --seed 42) ==
determinism: PASS (two --seed 42 runs identical excluding "timing")
```

Cross-check outside selftest (run 1 vs run 2 verdict JSON):

```
$ python3 -c "… load both, pop('timing'), compare …"
run1 == run2 (excl timing): True
```

### Selftest shows per-mutant kill lines and the kill rate

```
mutant coarse-mesh: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant load-on-ntip: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant load-wrong-dof: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant no-stress-output: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant overload-10x: FAIL (expected) -- killed by gate: verification, spec_limits
mutant propped-tip: FAIL (expected) -- killed by gate: verification, convergence, spec_limits
mutant unconverged: FAIL (expected) -- killed by gate: convergence
mutant undersized: FAIL (expected) -- killed by gate: spec_limits
mutant units-in-metres: FAIL (expected) -- killed by gate: spec_limits
== selftest summary ==
known-good: passed
kill rate: 9/9 (100%)
```

(identical in run 1 and run 2). `examples/bad/README.md` documents each
mutant and its killing gate.

### run.py --ref run (recorded by the lead, 2026-10-14)

`python3 run.py --ref sbx/demo-fea-calculix-3` from a host with the sbx
CLI: exit 0, sandbox killed and confirmed gone.

```
setup 12 s, selftest 236 s, grade 35 s
verdict: PASS
EB ref +0.41 % / -0.74 %, convergence 0.23 % / 0.50 %,
sigma 138.2 <= 166.7 MPa, deflection 7.72 <= 10 mm, mass 5652 g
```

Same numbers as both fresh-setup runs below (that run predates the
per-mutant selftest printout and the pinned-.deb setup, which do not
change any measured quantity).

---

## Two fresh-setup runs, side by side

| | run 1 | run 2 |
|---|---|---|
| date (UTC) | 2026-10-14 | 2026-10-14 |
| purged before | calculix-ccx + 17 deps removed, `~/tools` deleted | same |
| `judge/setup.sh` exit | 0 | 0 |
| setup wall time | 10 s | 16 s |
| ccx / gmsh installed | 2.20 ("This is Version 2.20") / 4.10.0 | same |
| `judge/selftest.sh` exit | 0 | 0 |
| selftest wall time | 311 s | 300 s |
| kill rate | 9/9 (100%) | 9/9 (100%) |
| determinism check | PASS | PASS |
| `judge/grade.sh examples/good` exit | 0 | 0 |
| grade wall time | 34 s | 34 s |
| verdict | PASS | PASS |
| EB deflection error (ref beam) | +0.41 % | +0.41 % |
| EB stress error (ref beam) | -0.74 % | -0.74 % |
| mesh convergence (deflection / stress) | 0.23 % / 0.50 % | 0.23 % / 0.50 % |
| sigma_wall | 138.241 MPa (<= 166.7) | 138.241 MPa |
| tip deflection | 7.7221 mm (<= 10.00) | 7.7221 mm |
| mass | 5652.0 g | 5652.0 g |
| verdict JSON (excl. `timing`) | identical | identical |

Fresh-setup run 1, `bash judge/setup.sh` (key lines):

```
== downloading http://deb.debian.org/debian/pool/main/c/calculix-ccx/calculix-ccx_2.20-1_amd64.deb ==
/tmp/tmp.2OTgLZoLuG/calculix-ccx_2.20-1_amd64.deb: OK
== downloading http://deb.debian.org/debian/pool/main/s/spooles/libspooles2.2_2.2-14_amd64.deb ==
/tmp/tmp.2OTgLZoLuG/libspooles2.2_2.2-14_amd64.deb: OK
== downloading http://deb.debian.org/debian/pool/main/a/arpack/libarpack2_3.8.0-3_amd64.deb ==
/tmp/tmp.2OTgLZoLuG/libarpack2_3.8.0-3_amd64.deb: OK
Setting up calculix-ccx (2.20-1) ...
ccx: This is Version 2.20
== downloading https://gmsh.info/bin/Linux/gmsh-4.10.0-Linux64.tgz ==
/tmp/tmp.VC3utWaWvH/gmsh-4.10.0-Linux64.tgz: OK
gmsh: 4.10.0
setup complete -> /home/user/tools/bin
```

(exit 0, wall 10 s)

Fresh-setup run 1, `bash judge/selftest.sh` (summary; full per-mutant
lines above):

```
== selftest: known-good artifact ==
known-good: PASS (expected)
…9 per-mutant kill lines, see Hardening…
== selftest summary ==
known-good: passed
kill rate: 9/9 (100%)
== selftest: determinism (grade twice with --seed 42) ==
determinism: PASS (two --seed 42 runs identical excluding "timing")
selftest: PASS
```

(exit 0, wall 311 s)

Fresh-setup run 1, `bash judge/grade.sh examples/good --seed 42` verdict
JSON (run 2 identical except `"wall_s"`):

```json
{
  "verdict": "PASS",
  "timing": {"wall_s": 34.0},
  "gates": {
    "verification": {
      "pass": true,
      "detail": "reference beam vs Euler-Bernoulli: deflection 0.4016 vs 0.4000 mm (+0.41%), stress 11.91 vs 12.00 MPa (-0.74%); tolerance 3%"
    },
    "convergence": {
      "pass": true,
      "detail": "mesh 4 vs 2 mm (11250 -> 60000 elements): deflection change 0.23%, stress change 0.50%; tolerance 2%"
    },
    "spec_limits": {
      "pass": true,
      "detail": "sigma 138.2 <= allowable 166.7 MPa; deflection 7.72 <= limit 10.00 mm"
    }
  },
  "metrics": {
    "L_mm": 1000.0, "b_mm": 12.0, "h_mm": 60.0, "mesh_size_mm": 4.0,
    "mass_g": 5652.0,
    "ref_delta_mm": 0.4016, "ref_sigma_mpa": 11.911,
    "coarse_elems": 11250, "fine_elems": 60000,
    "delta_mm": 7.7221, "sigma_mpa": 138.241
  }
}
```

## Wall times (2 vCPU / 4 GB)

| step | run 1 | run 2 |
|---|---|---|
| setup (pinned .debs + gmsh tarball) | 10 s | 16 s |
| selftest (good + 9 mutants + determinism) | 311 s | 300 s |
| grade the good artifact | 34 s | 34 s |

## Deviations

- `calculix-ccx` needs base-library dependencies (libopenmpi3 & co.) that
  have no history of breaking this judge; only calculix-ccx itself,
  libspooles2.2 (its direct solver) and libarpack2 (its eigenvalue
  solver) — the numerics-carrying packages — are sha256-pinned by URL.
  apt resolves the rest from the refreshed bookworm lists.
- The lead's `run.py --ref sbx/demo-fea-calculix-3` run (recorded above)
  was executed on the pre-hardening tree; both fresh-setup runs on the
  hardened tree reproduce its numbers exactly.
- `sudo: unable to resolve host instance` warnings in apt output are
  harmless (container hostname not in /etc/hosts).
- `ccx -v` writes job files to its working directory; `setup.sh` runs it
  in a scratch directory to avoid littering. Expected CalculiX 2.20
  behaviour.
- The good example design (L=1000, b=12, h=60, mesh_size=4) is
  hand-crafted to satisfy all gates; it is not derived from a published
  third-party source.
- `run.py`'s in-sandbox steps (setup/selftest/grade) were verified
  directly here; the sbx round-trip itself was verified by the lead's
  run recorded above (exit 0, sandbox removed).
- media/ (result.png, loop.png, demo.mp4) is out of scope for this pass
  (not done: another agent owns media/ for this demo).
- REPRODUCE.md (independent reproduction by a different model family,
  per the standard) is not written yet (not done: that check belongs to
  a different agent following README.md in a fresh sandbox; the two
  fresh-setup runs above give the reference numbers it must match).
