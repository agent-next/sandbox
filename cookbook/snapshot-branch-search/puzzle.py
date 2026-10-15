"""The sliding-puzzle model shared by the agent and the judge.

A board is a list of rows of ints, fixed size for the whole instance set:

     0  the blank
   1..N  a numbered tile
   255  a wall cell (impassable, part of the board, never moves)

The goal is derived, never stored: lay tiles 1..N over the non-wall cells in
row-major order, then the blank on the last one.  A 4x5 board with four walls
in the middle therefore has the goal

     1  2  3  4  5
     6  7  8  9 10
    11 12  # 13 14
    15 16 17 18  0

A move names the tile that slides into the blank, e.g. "13".  A move is legal
iff the named tile sits on a cell orthogonally adjacent to the blank.  That is
the entire rule of the game; there is no other legal move.

The judge and the agent must agree on exactly these semantics, so this module
is the single definition of the puzzle for both.  The judge pins the sha256 of
its own copy (judge/PINNED.txt) and refuses to grade a build whose copy
changed.

Standard library only.
"""
from __future__ import annotations

import bisect
import hashlib
import heapq
import json

WALL = 255
BLANK = 0


class PuzzleError(ValueError):
    """A board, instance id, move, or artifact the model cannot use."""


# --------------------------------------------------------------------------
# board helpers
# --------------------------------------------------------------------------
def check_board(board, rows, cols):
    """Validate a board's shape and contents.  Returns the wall set."""
    if not isinstance(board, list) or len(board) != rows:
        raise PuzzleError(f"board must be a list of {rows} rows, got {board!r}")
    walls = set()
    tiles = []
    for r, row in enumerate(board):
        if not isinstance(row, list) or len(row) != cols:
            raise PuzzleError(f"board row {r} must be a list of {cols} cells, got {row!r}")
        for c, cell in enumerate(row):
            if isinstance(cell, bool) or not isinstance(cell, int):
                raise PuzzleError(f"board cell ({r},{c}) is not an int: {cell!r}")
            if cell == WALL:
                walls.add((r, c))
            elif cell == BLANK:
                tiles.append(0)
            elif cell > 0:
                tiles.append(cell)
            else:
                raise PuzzleError(
                    f"board cell ({r},{c}) must be 0, 1..{rows * cols}, or {WALL} (wall); "
                    f"got {cell}"
                )
    if tiles.count(0) != 1:
        raise PuzzleError(f"board must hold exactly one blank; found {tiles.count(0)}")
    playable = rows * cols - len(walls)
    if playable < 2:
        raise PuzzleError(f"board has only {playable} playable cells")
    # The tile *set* must be exactly 1..N, one of each -- a gap or a duplicate
    # is a broken board.  The arrangement is the puzzle, so it is not checked.
    got = sorted(t for t in tiles if t)
    if got != list(range(1, playable)):
        raise PuzzleError(
            f"board tiles must be exactly 1..{playable - 1}, one of each; got {got}"
        )
    return walls


def goal_board(rows, cols, walls):
    """The derived goal: tiles 1..N over non-wall cells in row-major order."""
    board = [[WALL] * cols for _ in range(rows)]
    k = 0
    last = None
    for r in range(rows):
        for c in range(cols):
            if (r, c) in walls:
                continue
            board[r][c] = k + 1
            k += 1
            last = (r, c)
    board[last[0]][last[1]] = BLANK
    return board


def board_to_text(board):
    """Canonical text form: one space-separated row per line."""
    return "\n".join(" ".join("#" if c == WALL else str(c) for c in row) for row in board)


def digest_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_text(text):
    """Parse the canonical text form back into a board.  Raises PuzzleError."""
    if not isinstance(text, str):
        raise PuzzleError("state text must be a string")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    board = []
    for line in lines:
        row = []
        for tok in line.split():
            if tok == "#":
                row.append(WALL)
            elif tok == ".":
                row.append(BLANK)
            else:
                try:
                    row.append(int(tok))
                except ValueError:
                    raise PuzzleError(f"state token {tok!r} is not '#', '.', or an int") from None
        board.append(row)
    if not board:
        raise PuzzleError("state text is empty")
    return board


# --------------------------------------------------------------------------
# the puzzle
# --------------------------------------------------------------------------
class Puzzle:
    """A fixed board geometry, its derived goal, and the move table.

    States are `bytes` (one byte per cell, row-major) so the judge's search can
    hold millions of them in a set without a per-state Python object.
    """

    def __init__(self, board):
        if not isinstance(board, list) or not board:
            raise PuzzleError("board must be a non-empty list of rows")
        self.rows = len(board)
        self.cols = len(board[0])
        if any(len(row) != self.cols for row in board):
            raise PuzzleError("every board row must have the same length")
        self.start_board = [list(r) for r in board]
        walls = check_board(self.start_board, self.rows, self.cols)
        self.walls = frozenset(walls)
        self.playable = self.rows * self.cols - len(walls)
        self.n_tiles = self.playable - 1
        self.goal_board = goal_board(self.rows, self.cols, walls)
        if check_board(self.goal_board, self.rows, self.cols) != walls:
            raise PuzzleError("start board and derived goal disagree about the walls")
        self.start = self.pack(self.start_board)
        self.goal = self.pack(self.goal_board)

        # blank index -> [(neighbour index), ...]; walls have no neighbours
        idx = self._index()
        self.neighbours = {}
        for i in range(self.rows * self.cols):
            r, c = divmod(i, self.cols)
            opts = []
            if r > 0:
                opts.append(i - self.cols)
            if r < self.rows - 1:
                opts.append(i + self.cols)
            if c > 0:
                opts.append(i - 1)
            if c < self.cols - 1:
                opts.append(i + 1)
            self.neighbours[i] = [j for j in opts if j in idx]

        # goal position of each tile, for the heuristic
        self.goal_pos = {}
        for r in range(self.rows):
            for c in range(self.cols):
                t = self.goal_board[r][c]
                if t not in (WALL, BLANK):
                    self.goal_pos[t] = (r, c)

    def _index(self):
        """The set of playable (non-wall) cell indices."""
        return {i for i in range(self.rows * self.cols) if i not in
                {r * self.cols + c for r, c in self.walls}}

    def manhattan(self, state):
        """Sum over tiles of the distance to their goal cell (admissible)."""
        total = 0
        for i, cell in enumerate(state):
            if cell in (WALL, BLANK):
                continue
            gr, gc = self.goal_pos[cell]
            r, c = divmod(i, self.cols)
            total += abs(gr - r) + abs(gc - c)
        return total

    def linear_conflict(self, state):
        """Extra cost from goal-sharing rows/cols (still admissible)."""
        total = 0
        rows, cols = self.rows, self.cols
        # rows: tiles already in their goal row, ordered by goal column
        for r in range(rows):
            line = []
            for c in range(cols):
                t = state[r * cols + c]
                if t in (WALL, BLANK):
                    line = []  # a wall breaks the row into segments
                    continue
                gr, gc = self.goal_pos[t]
                if gr == r:
                    line.append(gc)
            total += self._conflicts(line)
        # columns likewise
        for c in range(cols):
            line = []
            for r in range(rows):
                t = state[r * cols + c]
                if t in (WALL, BLANK):
                    line = []
                    continue
                gr, gc = self.goal_pos[t]
                if gc == c:
                    line.append(gr)
            total += self._conflicts(line)
        return 2 * total

    @staticmethod
    def _conflicts(line):
        """2 * the minimum number of tiles that must leave the line.

        `line` is the goal positions of the line's tiles in their current
        order.  The tiles that can stay are the longest already-ordered
        subsequence; every other tile must leave and come back (2 moves).
        """
        if len(line) < 2:
            return 0
        # patience-sorting LIS length (strictly increasing goal positions)
        tails = []
        for x in line:
            i = bisect.bisect_left(tails, x)
            if i == len(tails):
                tails.append(x)
            else:
                tails[i] = x
        return 2 * (len(line) - len(tails))

    # -- packing ----------------------------------------------------------
    def pack(self, board):
        return bytes(
            cell if cell >= 0 else WALL for row in board for cell in row
        )

    def unpack(self, state):
        return [
            [state[r * self.cols + c] for c in range(self.cols)]
            for r in range(self.rows)
        ]

    def text(self, state):
        return board_to_text(self.unpack(state))

    def digest(self, state):
        return digest_text(self.text(state))

    # -- moves ------------------------------------------------------------
    def blank_index(self, state):
        return state.index(BLANK)

    def legal_moves(self, state):
        """Every legal move as (tile, next_state) — deduplicated, sorted."""
        b = state.index(BLANK)
        seen = {}
        for j in self.neighbours[b]:
            tile = state[j]
            if tile == WALL:
                continue
            lst = list(state)
            lst[b], lst[j] = lst[j], lst[b]
            seen[tile] = bytes(lst)
        return sorted(seen.items())

    def apply_move(self, state, tile):
        """Apply the move named by tile.  Raises PuzzleError if illegal."""
        b = state.index(BLANK)
        for j in self.neighbours[b]:
            if state[j] == tile:
                lst = list(state)
                lst[b], lst[j] = lst[j], lst[b]
                ns = bytes(lst)
                assert ns.index(BLANK) == j
                return ns
        blank = self.unpack(state)
        raise PuzzleError(
            f"illegal move {tile!r}: tile {tile!r} is not adjacent to the blank at "
            f"row {b // self.cols + 1}, col {b % self.cols + 1} of\n{board_to_text(blank)}"
        )

    def is_move_legal(self, state, tile):
        b = state.index(BLANK)
        return any(state[j] == tile for j in self.neighbours[b])

    def solvable(self, state=None):
        """Parity check for the playable sub-board.

        Slides swap the blank with a tile, i.e. a transposition, so the parity
        of the permutation of playable cells (ignoring walls and the blank) is
        invariant.  Two states with different parity are unreachable.
        """
        state = self.start if state is None else state
        return self._parity(state) == self._parity(self.goal)

    def _parity(self, state):
        seq = [c for c in state if c not in (WALL, BLANK)]
        inv = sum(
            1
            for i in range(len(seq))
            for j in range(i + 1, len(seq))
            if seq[i] > seq[j]
        )
        pos = [i for i, c in enumerate(state) if c == BLANK][0]
        # number of inversions plus the blank's row from the bottom, with a
        # correction for the wall count (walls shift the blank's row parity)
        walls_above = sum(1 for i in range(pos) if state[i] == WALL)
        return (inv + pos // self.cols + walls_above) % 2


# --------------------------------------------------------------------------
# exact search — the judge's oracle
# --------------------------------------------------------------------------
def astar(p, start=None, node_cap=1_500_000):
    """Exact A*.  Returns (length, moves, nodes_expanded) or None if capped.

    The heuristic is admissible, so the first solution popped is optimal.  The
    node cap makes an out-of-budget instance fail loudly instead of hanging
    the grader.
    """
    start = p.start if start is None else start
    goal = p.goal
    if start == goal:
        return 0, [], 0
    open_heap = [(p.manhattan(start), 0, start)]
    g = {start: 0}
    parent = {}
    nodes = 0
    while open_heap:
        f, gc, s = heapq.heappop(open_heap)
        if g.get(s, -1) != gc:
            continue
        nodes += 1
        if s == goal:
            path = []
            cur = s
            while cur in parent:
                prev, mv = parent[cur]
                path.append(mv)
                cur = prev
            path.reverse()
            return len(path), path, nodes
        for tile, ns in p.legal_moves(s):
            ng = gc + 1
            if ng < g.get(ns, 1 << 30):
                g[ns] = ng
                parent[ns] = (s, tile)
                heapq.heappush(open_heap, (ng + p.manhattan(ns), ng, ns))
        if nodes > node_cap:
            return None
    return -1, [], nodes


def astar_conflict(p, start=None, node_cap=1_500_000):
    """Same A* with the Manhattan + linear-conflict heuristic.

    Two admissible heuristics over the same model; the cheaper one is used for
    the bound and this one is the cross-check that the first run's optimum is
    not an artefact of the weaker heuristic.
    """
    start = p.start if start is None else start
    goal = p.goal
    if start == goal:
        return 0, [], 0

    def h(s):
        return p.manhattan(s) + p.linear_conflict(s)

    open_heap = [(h(start), 0, start)]
    g = {start: 0}
    parent = {}
    nodes = 0
    while open_heap:
        f, gc, s = heapq.heappop(open_heap)
        if g.get(s, -1) != gc:
            continue
        nodes += 1
        if s == goal:
            path = []
            cur = s
            while cur in parent:
                prev, mv = parent[cur]
                path.append(mv)
                cur = prev
            path.reverse()
            return len(path), path, nodes
        for tile, ns in p.legal_moves(s):
            ng = gc + 1
            if ng < g.get(ns, 1 << 30):
                g[ns] = ng
                parent[ns] = (s, tile)
                heapq.heappush(open_heap, (ng + h(ns), ng, ns))
        if nodes > node_cap:
            return None
    return -1, [], nodes


def bidirectional_optimum(p, node_cap=4_000_000):
    """Meet-in-the-middle BFS: a second, structurally different optimum.

    Breadth-first from both ends at once.  Its answer is compared with the A*
    optimum by the judge; two algorithms sharing only the puzzle model must
    agree before the optimality gate can pass.
    """
    start, goal = p.start, p.goal
    if start == goal:
        return 0
    fwd = {start: 0}
    bwd = {goal: 0}
    fq, bq = [start], [goal]
    nodes = 0
    while fq and bq:
        nodes += 1
        if nodes > node_cap:
            return None
        nf, nb = [], []
        for s in fq:
            for _, ns in p.legal_moves(s):
                if ns not in fwd:
                    fwd[ns] = fwd[s] + 1
                    if ns in bwd:
                        return fwd[ns] + bwd[ns]
                    nf.append(ns)
        for s in bq:
            for _, ns in p.legal_moves(s):
                if ns not in bwd:
                    bwd[ns] = bwd[s] + 1
                    if ns in fwd:
                        return fwd[ns] + bwd[ns]
                    nb.append(ns)
        fq, bq = nf, nb
    return None


def scramble(p, n_moves, rng):
    """A random walk from the start — used only to build the instance set."""
    s = p.start
    if not p.solvable(s):
        raise PuzzleError("instance start is not solvable")
    for _ in range(n_moves):
        s = p.legal_moves(s)[rng.randrange(len(p.legal_moves(s)))][1]
    return s


# --------------------------------------------------------------------------
# instances
# --------------------------------------------------------------------------
def load_instances(path):
    """Load instances.json -> [(id, Puzzle), ...]  (order preserved)."""
    with open(path, encoding="utf-8") as fh:
        spec = json.load(fh)
    if not isinstance(spec, dict):
        raise PuzzleError("instances file must be a JSON object")
    try:
        rows, cols, raw = spec["rows"], spec["cols"], spec["instances"]
    except (KeyError, TypeError) as exc:
        raise PuzzleError(f"instances file is missing key {exc}") from None
    out = []
    seen = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise PuzzleError(f"instance {i} is not an object")
        iid = entry.get("id")
        board = entry.get("board")
        if not isinstance(iid, str) or not iid:
            raise PuzzleError(f"instance {i} needs a non-empty string 'id'")
        if iid in seen:
            raise PuzzleError(f"duplicate instance id {iid!r}")
        seen.add(iid)
        if not isinstance(board, list):
            raise PuzzleError(f"instance {iid!r} needs a 'board' list of rows")
        for row in board:
            if not isinstance(row, list) or len(row) != cols:
                raise PuzzleError(f"instance {iid!r}: every row needs {cols} cells")
        if len(board) != rows:
            raise PuzzleError(f"instance {iid!r} needs {rows} rows")
        p = Puzzle(board)
        if not p.solvable():
            raise PuzzleError(f"instance {iid!r} is not solvable (parity)")
        out.append((iid, p))
    if not out:
        raise PuzzleError("instances file lists no instances")
    return out
