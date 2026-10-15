# SPEC — `cookbook/snapshot-branch-search/`

An agent works on a combinatorial search problem inside a disposable
agent-next sandbox: solve eight fixed sliding-puzzle instances exactly,
branching working-directory state with filesystem snapshots, so that a judge
it cannot fool (an exact A* oracle plus a cross-check, sharing only the
puzzle model) decides whether every solution is right.

## Goal

Solve a fixed set of 8 sliding-puzzle instances (a 15-puzzle family: one
blank, numbered tiles, optional wall cells) *optimally*, producing an
artifact of move sequences. The agent keeps its search working directory in
the sandbox and branches it with filesystem snapshots (`cp --reflink`
copies / `tar` checkpoints; the one-command run additionally documents
`sbx` pause/resume/snapshot where the CLI offers them). Optimality is
measured by the judge, not asserted.

## Non-goals

- Novel search algorithms or performance records: the judge's pass rule is
  solution correctness plus optimality vs its own bound, not speed, memory or
  snapshot throughput.
- Other puzzles (8-puzzle on plain 3x3 boards without walls, Rubik cubes,
  Sokoban). The model in `puzzle.py` covers this one game only.
- Any guarantee about *how* the agent searches: BFS, A*, DFS with snapshots,
  hand-solving — the artifact and the judge's replay are the only contract.
- Distribution of the solver: the graded artifact is data (the move
  sequences), not the agent's solver code.

## Artifact

A single JSON file (the file graded by `judge/grade.sh <artifact>`) holding
exactly the keys:

- `instances`: a JSON array, one entry per instance id in `instances.json`
  (all 8, no duplicates, no extras), each entry an object with:
  - `id`: the instance id string, exactly as in `instances.json`;
  - `board`: the instance's starting board as text, exactly the canonical
    form of `puzzle.py` (`board_to_text`, one space-separated row per line,
    `#` for walls), matching the instance's board byte-for-byte after
    canonical round-trip;
  - `moves`: an array of move strings; each move names the tile that slides
    into the blank, e.g. `"13"`. Moves are tile numbers as decimal strings
    (`str(tile)`); the array may be empty only for a goal start.

The known-good example is produced by an exact solver over the pinned
instances, but the gates below apply to *any* move sequences that replay to
the goal in the optimal number of moves.

## Judge gates (`judge/grade.sh <artifact> [--seed N] [--json out.json]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.
The judge engine (`judge/puzzle_judge.py`, stdlib only) loads the demo's
pinned `puzzle.py` (its sha256 recorded in `judge/PINNED.txt`; a changed
model file fails closed) and the pinned `instances.json`.

- **G1 artifact shape**: the file parses as JSON within 64 KiB, has an
  `instances` array, and holds exactly one entry per instance id of
  `instances.json` — same ids, no duplicates, no missing, no unknown ids.
  Each entry is an object whose `board` text parses (`parse_text`) and
  equals the instance board after a canonical round-trip (whitespace
  may differ, nothing else), and whose `moves` is an array of strings,
  each a positive decimal integer naming a tile of that instance.
- **G2 replay**: for every instance, the judge replays the move sequence
  from the instance start using the model's `apply_move` (which raises on
  an illegal move). A sequence with an illegal move, a non-existent tile
  id, or wrong arity fails this gate with the move index and board state.
  Sequences that stop before the goal fail this gate (they do not reach
  the goal), reporting the final distance.
- **G3 goal reached**: the replayed final state equals the derived goal
  (`goal_board`) for every instance. (Checked as part of G2's success
  path; kept as its own gate with its own numeric rule: final state ==
  goal for 8/8 instances.)
- **G4 optimality**: for every instance, `len(moves)` equals the exact
  optimum computed by the judge's own A* (`puzzle.astar`) on the pinned
  model. A longer sequence fails with the submitted and optimal lengths.
  A *shorter* sequence is impossible if G2/G3 pass and would itself fail
  G2 (it cannot reach the goal), so the equality is the whole rule.
- **G5 blank/no-move validity**: no move may name the blank (`"0"`) or a
  wall; no instance entry may carry duplicate ids. (Structural, folded
  into G1's per-entry rules so a structural problem reports once.)

The blank-swap count per instance is reported in the verdict as
`moves_len` / `optimal` for every instance.

## Acceptance oracle (independent of "the tool ran")

1. **Exact search oracle**: the judge runs its own A* over the pinned
   model (admissible Manhattan heuristic) and uses the optimal length as
   the gate — an analytic solution of the same puzzle, computed by code
   that never sees the artifact beyond replaying it.
2. **Cross-check, structurally different algorithm**: a meet-in-the-middle
   bidirectional BFS (`puzzle.bidirectional_optimum`) computes the optimum
   again; the judge requires both to agree before G4 can pass. Two search
   algorithms sharing only `puzzle.py` must produce the same number.
3. **Replay, not trust**: move sequences are validated by applying them to
   the start board through the model's own `apply_move`, so a sequence
   that "looks right" but contains an illegal slide fails with the exact
   move index and the board at which it is illegal.
4. **No self-report**: nothing in the artifact (lengths, digests, claims)
   is taken as evidence; the only artifact fields the judge reads are the
   board text (checked against the pinned instance) and the moves.

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants of the good artifact each fail ≥ 1
  gate, generated by `judge/mutants.py` (one edit each):
  - `illegal-move`: one move changed to a tile not adjacent to the blank;
  - `one-short`: the last move of one instance deleted (sequence stops
    one move short of the goal);
  - `wrong-id`: one instance entry's `id` replaced by an unknown id;
  - `non-optimal`: one instance's optimal sequence prefixed with a legal
    move away and back (optimal + 2 moves);
  - `corrupted-board`: one entry's `board` text altered to a different
    legal board (fails the board-match rule);
  - `extra-instance`: a ninth entry invented (fails the exact-id-set
    rule).
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce
  byte-identical verdict JSON; checked by the self-test on every run.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares `sha256` of its own `judge/` tree (including the pinned model's
PINNED.txt check) before and after every grade and fails closed if
anything changed.

## Out of scope for the judge

- How the agent obtained the sequences (search code quality, snapshot
  counts, reflink vs tar).
- Wall-clock or memory cost of the agent's run.
- Anything the artifact claims in extra fields (unknown fields are
  ignored; only the rules above are graded).

## Tools (pinned by `judge/setup.sh`)

- Python **3.10+**, standard library only (no downloads); `setup.sh`
  verifies the interpreter and records `python3 --version` in
  `judge/VERSIONS.txt`. No third-party tools and no network access are
  needed to grade.
