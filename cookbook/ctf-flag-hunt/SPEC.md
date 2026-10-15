# SPEC — `cookbook/ctf-flag-hunt/`

An agent works on a security-engineering problem inside a disposable
agent-next sandbox: build a five-service capture-the-flag range, where a
judge it cannot fool (sha256 flag matching + scripted reference exploits +
an independent crypto oracle + a negative control + scripted mutants)
decides whether the range is right.

## Goal

Produce a CTF range of five self-contained C services that compiles on a
2 vCPU / 3 GB sandbox in seconds and in which **each challenge is
vulnerable in exactly one specified way and no other**:

| # | service | class | the range must be vulnerable to |
|---|---|---|---|
| C1 | `notes` | off-by-one | an out-of-bounds note id that reads past the notes table |
| C2 | `retrieve` | path traversal | a `../` name escaping the document root |
| C3 | `token` | weak crypto | forging a token from public data (no secret) |
| C4 | `status` | config leak | an internal-state query that dumps the flag |
| C5 | `admin` | logic bug | an unparsable mode that falls into the privileged branch |

Each service releases its flag only when its own exploit is used, and
never on any other input.

## Non-goals

- **Real-world hardening.** The range is deliberately vulnerable; the
  services are not to be written defensively. What *is* graded is that each
  vulnerability is the specified one, and that no non-exploit input to that
  service returns its flag (G4). Cross-service isolation — whether one
  challenge's exploit can reach another's flag file — is **not** graded.
- **Remote exploitation.** No sockets, no network: every exploit is a local
  process invocation (argv or stdin). Nothing binds a port.
- **Autonomous vulnerability discovery.** The judge does not grade whether
  an agent *found* an unknown bug. The vulnerability class and its
  observable exploit are pinned below, so the judge is deterministic; the
  agent's freedom is in the implementation.
- **Memory-safety realism.** C1 is a logical out-of-bounds read (a table
  index), not a memory-corruption exploit: no ASLR, stack or heap layout is
  involved and `-fstack-protector` does not change the outcome.
- **Flag secrecy against the operator.** The judge generates the flags and
  hands each service its flag in the environment at launch. A user who can
  read `/proc/<pid>/environ` can read the flag. G4 covers *service*
  behaviour (which inputs leak a flag), not the process environment.

## Artifact

A directory of C sources (the path graded by `judge/grade.sh <dir>`)
containing exactly these five entry files:

```
notes.c  retrieve.c  token.c  status.c  admin.c
```

The judge compiles each with a fixed, documented rule —

```
cd <dir> && gcc-12 -O2 -std=c11 -Wall -o <out>/<name> <name>.c
```

(`gcc-12` is the binary the pinned package installs; `/usr/bin/gcc` is a
symlink from a *different* package and is not guaranteed to exist on a
fresh install, so the judge names the compiler explicitly.)

— with `<dir>` as both the working directory and the include path (so
`#include "helper.h"` beside the sources works). Any other files in the
artifact directory are available for `#include` but are not compiled on
their own. The artifact must not contain a `build.sh`: the judge owns the
compile line.

### Pinned interfaces

Every service prints one result line per request to stdout and exits 0 on a
handled request, non-zero on a usage error. Nothing writes a file.

| service | invocation | request | response |
|---|---|---|---|
| `notes` | `notes <notes-file>` | one integer id per line on stdin | the note text, `error` for a rejected id |
| `retrieve` | `retrieve <docroot> <name>` | argv | the file content, or `not found` |
| `token` | `token issue` | argv | `token=<16 hex> seed=<n> salt=<n> time=<n>` |
| `token` | `token verify <token>` | argv | `verify=ok flag=<flag>` on a valid token, `verify=bad` otherwise |
| `status` | `status version` / `build` | argv | `version=<string>` / `build=<string>` |
| `status` | `status config` | argv | `config=version=<v>;build=<b>;flag=<flag>` |
| `status` | `status <other>` | argv | `error=unknown-key` |
| `admin` | `admin <mode> <path>` | argv | `mode=<m> content=<c>`, where `<c>` is the file content or `denied` |

`<notes-file>` is a text file of one note per line, ids `0..N-1` in file
order. `<docroot>` is a directory of servable files; `retrieve` resolves
`<name>` against it. `<path>` for `admin` is an absolute path to a file.
`range.conf`, the notes file and the document root are planted by the judge
and are not part of the artifact.

### Pinned vulnerability observables

These are the properties the judge measures. They are the contract; the
code that realizes them is the agent's.

- **C1**: for a notes file of `N` notes, ids `0..N-1` return that note and
  never the flag, the single id `N` returns the flag, and any other id
  prints `error`. The bound check is written `id > n` instead of `id >= n`,
  so exactly one id past the last note is admitted. The judge knows `N`
  because it writes the notes file.
- **C2**: a name that stays inside `<docroot>` serves that file; a name
  containing `..` that escapes `<docroot>` serves the file outside it. The
  flag file for C2 lives **outside** the document root.
- **C3**: `issue` derives the token from `seed` and `salt` (public, in
  `range.conf`) and the current `time` by the mixer pinned below, and prints
  all three inputs. `verify <token>` accepts a token computed for **any `t`
  with `|now − t| ≤ 300 s`**, and only then prints the flag; any other token
  prints `verify=bad` and no flag. Because every input is public and the
  acceptance window is 300 s wide, the token is forgeable by anyone who can
  read `range.conf` and their own clock — that is the weakness.
- **C4**: `status config` prints its internal configuration table, which
  includes `flag=<flag>`; `status version` and `status build` print their
  value and never the flag; any other key prints `error=unknown-key`.
- **C5**: the documented modes are `1` (status) and `2` (audit), and both
  print `denied` for any path. Mode `0` is documented as retired but is
  still wired to the privileged read, and the mode is parsed with `atoi`,
  so any unparsable mode silently becomes `0`. `admin 0 <flagfile>` and
  `admin <non-numeric> <flagfile>` therefore print the flag file's content;
  `admin 1 <flagfile>` and `admin 2 <flagfile>` print `denied`.

The **token mixer** (pinned; the judge recomputes it in Python):

```
x = seed
x = (x * 6364136223846793005 + 1442695040888963407) mod 2**64
x = x xor ((salt << 13) mod 2**64)
x = (x * 6364136223846793005 + 1442695040888963407) mod 2**64
x = x xor ((t << 7) mod 2**64)
token = the 16 lowercase hex digits of x, zero-padded
```

`t` is `issue`'s `time(NULL)`; the shift and multiply are on unsigned
64-bit integers, so the result is taken mod 2**64 at every step.

### Pinned flag format

```
flag{c<N>_<16 lowercase hex digits>}
```

matching `^flag\{c[1-5]_[0-9a-f]{16}\}$`. The judge generates the five
flags itself from `--seed` and hands every one to its service only in the
environment variable `CTF_FLAG` at launch. The two file challenges (C2, C5)
also need a file to read, so the judge materialises those two flags as the
flag files it plants (`flag_c2.txt` outside the document root,
`flag_c5.txt` in the run directory). No flag is written into the artifact
directory, the binaries or the document root — the negative-control sweep
in G4 checks exactly that.

### Pinned configuration

The judge plants `range.conf` in the run directory (mode 0644), one
`key=value` per line:

```
seed=<decimal>
salt=<decimal>
version=<string>
build=<string>
```

Services that need it read `range.conf` from the working directory. The
judge owns this file; it is not part of the artifact.

## Judge gates (`judge/grade.sh <artifact-dir> [--seed N] [--json out.json]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.

- **G1 build**: all five entry files exist and each compiles with the fixed
  rule, warning-free under `-Wall`, in under 60 s total.
- **G2 flag match (5/5)**: for each challenge, the judge's scripted
  reference exploit runs and the captured string must satisfy the flag
  format **and** `sha256(captured)` must equal `sha256(planted flag)` for
  that challenge. Pass rule: exactly **5/5**.
- **G3 independent oracle per challenge**: G2's capture is not accepted on
  its own. For each challenge the judge additionally requires the
  challenge-specific independent check:
  - C1: an in-bounds id returns its note and a non-exploit id returns
    neither the flag nor another note;
  - C2: the same file served from inside the docroot matches a direct read
    of that file (the traversal is a real file read, not a canned string);
  - C3: the judge recomputes the token in Python from the printed
    `seed/salt/time` and requires an exact string match with the printed
    token, then requires `verify` to accept the judge's independently
    computed token (and to reject one computed for `t` outside the window);
  - C4: `status version` and `status build` return their configured values
    from `range.conf` and contain no flag;
  - C5: `admin 1 <flagfile>` and `admin 2 <flagfile>` print `denied`.
  Pass rule: **5/5** independent checks hold.
- **G4 negative control (exploit step disabled)**: the judge replays, for
  every challenge, the *legitimate* action set only — in-bounds note ids,
  in-docroot retrievals, `verify` with a wrong token, `status` on
  non-leaking keys, `admin 1`/`admin 2` — and requires **0/5** flags.
  Additionally a filesystem sweep for the five flag strings over the
  artifact directory, the compiled binaries and the document root must
  return **0 hits**, so a flag cannot be baked in or served without
  exploitation. Pass rule: 0/5 and 0 hits.
- **G5 blast radius**: sha256 of every file in the run directory (and the
  document root) is recorded before the exploit harness and compared after.
  The set difference must be **empty**: no service writes, deletes or
  modifies any file.

Violating any gate fails with the offending numbers printed.

**G6, the mutant kill rate, is not a `grade.sh` gate** — `grade.sh` grades
one artifact and has no mutants of its own. G6 is enforced by
`judge/selftest.sh`, which grades the known-good artifact, then each
mutant, and fails if the kill rate is below 90 %.

## Acceptance oracle (independent of "it ran")

1. **sha256 flag matching, not string presence.** A gate that only checked
   "the word flag appeared" would pass a service that prints a constant.
   G2 compares the sha256 of the captured string against the sha256 of the
   flag the judge generated for this run — and the flags are regenerated
   per `--seed`, so no constant can match.
2. **Independent recomputation for the crypto challenge.** C3's token is
   recomputed in Python from the service's own printed inputs. A service
   that prints a token unrelated to its inputs, or that prints the flag
   without a valid token, fails G3 even though G2 might still see a flag.
3. **Differential oracle for the file challenges.** C2's capture is
   compared against a direct read of the same file, so returning a canned
   string fails; C1's in-bounds and out-of-bounds paths are both probed, so
   a lookup that always returns the flag fails.
4. **Negative control.** G4 replays every legitimate action and requires
   zero flags, so a service that leaks its flag on *any* input, not just
   the exploit, fails. The filesystem sweep additionally proves the flags
   are not baked into the artifact.
5. **Spec mask.** The pinned interfaces and observables above are measured
   from the running services, not asserted by the artifact or its comments.
6. **Determinism**: two `grade.sh` runs with the same `--seed` produce
   byte-identical verdict JSON (excluding the `timing` key); `selftest.sh`
   checks this on every run.

## Self-test (`judge/selftest.sh`)

- The known-good artifact passes every gate.
- ≥ 5 known-bad single-line mutants of the good artifact each fail ≥ 1
  gate; mutants are generated by `judge/mutants.py`, one edit each, and
  include both "fixes the vulnerability" edits (must fail G2) and "leaks
  the flag elsewhere" edits (must fail G3), plus a flag-baking edit (must
  fail the G4 sweep) and a file-writing edit (must fail G5).
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce
  byte-identical verdict JSON; checked on every run.

## Judge-integrity rule

The artifact under test is copied to a temp directory before grading; the
judge compares `sha256` of its own `judge/` tree before and after every
grade and fails closed if anything changed.

## Out of scope for the judge

- Whether the services are *good engineering* beyond the pinned
  observables (style, comments, extra files).
- Anything the sources claim in comments.
- Network-facing behaviour, real memory corruption, and flag secrecy
  against a user who can read process environments.

## Tools (pinned by `judge/setup.sh`)

- **gcc 12.2.0** (`gcc-12` Debian bookworm package), sha256-pinned `.deb`
  download, installed idempotently. Python 3.10+ (stdlib only) for the
  judge math.
- The judge itself is stdlib-only Python; `judge/setup.sh` records what it
  installed in `judge/VERSIONS.txt`.
