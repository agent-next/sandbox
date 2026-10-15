#!/usr/bin/env python3
"""Generate the pinned task corpus for the skill-ab-bench demo.

Everything the two arms answer is produced here from a fixed recipe, so the
demo needs no third-party data (no URL or licence is owed) and every sandbox
sees byte-identical inputs.  The recipe is stated in SPEC.md ("pinned, seeded
inputs"); this module is the single source of truth for it and is what
`judge/setup.sh` renders into `judge/tasks.json`.

Recipe (deterministic, no RNG):

  * 8 "kv" tasks - config-snippet / CSV value-lookup tasks
  * 8 "re" tasks - regex match/label tasks

Each task carries:

  task_id       stable id (kv01..kv08, re01..re08)
  kind          "kv" | "re"
  prompt        the question the arm policies are asked
  input         the input text the answer is computed from
  params        the task's parameters (read by judge/verify.py)
  answer        the reference answer, computed by judge/verify.py here
  difficulty    1 (both arms answer correctly) | 0 (only the skill arm does)
  naive_answer  what the no-skill arm answers (wrong for difficulty 0)
  note          one line on why the naive method misses it

The split below gives, by construction, 10 tasks where both arms answer
correctly and 6 where only the skill arm does: 25 pass-rate points between
the arms (10/16 vs 16/16).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify  # noqa: E402

JDIR = Path(__file__).resolve().parent
OUT = JDIR / "tasks.json"

# (task_id, kind, prompt, difficulty, note, naive_answer_fn_key)
TASK_TABLE = [
    ("kv01", "kv", "What is the value of `timeout_ms` for service alpha?", 1,
     "naive lookup finds the only occurrence"),
    ("kv02", "kv", "What is the value of `retry_count` for service alpha?", 0,
     "naive lookup scans the whole file and hits [client] first"),
    ("kv03", "kv", "What is the value of `max_queue` in the last block?", 0,
     "naive lookup takes the first occurrence, inside a comment block"),
    ("kv04", "kv", "What is the value of `TLS_MIN_VERSION` (case-sensitive key)?", 0,
     "naive lookup is case-insensitive and returns the decoy lowercase key"),
    ("kv05", "kv", "What is the effective (uncommented) `feature_flag` value?", 0,
     "naive lookup keeps the commented-out line and never sees the active one"),
    ("kv06", "kv", "What is the value of `region` for worker 2?", 1,
     "naive CSV split handles it"),
    ("kv07", "kv", "What is the value of `workers` in the last [pool] block?", 0,
     "naive lookup takes the first [pool] block's value"),
    ("kv08", "kv", "What is the value of `checkout_branch` (comments trimmed)?", 0,
     "naive lookup keeps the trailing comment inside the value"),
    ("re01", "re", "List the numbers in `sensors = 10, 22, 30` separated by '|'.", 1,
     "naive digit scan handles it"),
    ("re02", "re", "Which port is followed by another port (grabbed greedily by a naive pattern)?", 0,
     "naive greedy 'port=.*' swallows 8000,8001 and reports both"),
    ("re03", "re", "Report the whole quoted string in `label = \"ab\\\"cd\" end`.", 0,
     "naive '\".*\"' stops at the escaped quote"),
    ("re04", "re", "Report the v4 address in `v6 host is ::1 and v4 host is 10.0.0.1`.", 0,
     "naive '.*' match on 'host is' starts at ::1 and takes that"),
    ("re05", "re", "Report the version in `version = 2.10` to three parts.", 0,
     "naive '\\d+\\.\\d+' stops at the first dot and misses '.10'"),
    ("re06", "re", "Count the whole word `red` in `red blue|red` (any case).", 0,
     "naive substring count handles the pipe and both words fine, but the "
     "honest one is a word-boundary count"),
    ("re07", "re", "Report the email local part of `Contact: Ada+L@example.com`.", 0,
     "naive '\\w+@' stops at the '+' in the local part"),
    ("re08", "re", "Report the last integer in `id = 007-42`.", 1,
     "naive trailing-digit scan handles it"),
]

# The naive policy's answers are part of the pinned corpus: this is what the
# no-skill arm is *supposed* to get wrong, so the A/B delta is a fact of the
# corpus and not a random outcome.
NAIVE = {
    "kv01": "4500",
    "kv02": "7",                       # picked [client], not [service alpha]
    "kv03": "12",                      # picked the comment block, not [tail]
    "kv04": "TLSv1.2",                 # picked the lowercase decoy
    "kv05": "off",                     # picked the commented-out line
    "kv06": "ap-south-1",
    "kv07": "4",                       # picked the first [pool]
    "kv08": '"release/2.0"   # keep',  # comment kept inside the value
    "re01": "10|22|30",
    "re02": "8000,8001",
    "re03": "ab\\",                    # stopped at the escaped quote
    "re04": "::1",                     # matched the v6 host
    "re05": "2.10",                    # two-part match, not three
    "re06": "2",
    "re07": "Ada",                     # stopped at '+'
    "re08": "42",
}


def _corpus() -> dict[str, dict]:
    return {
        "kv01": {"input": "timeout_ms = 4500\n",
                 "params": {"key": "timeout_ms"}},
        "kv02": {"input": "[client]\nretry_count = 7\n\n"
                          "[service alpha]\nretry_count = 3\n",
                 "params": {"key": "retry_count", "section": "service alpha"}},
        "kv03": {"input": "; the rest of the file\n"
                          "[[block]]\nmax_queue = 12\n\n"
                          "# the tail block\n[tail]\nmax_queue = 90\n",
                 "params": {"key": "max_queue", "last": True, "active_only": True}},
        "kv04": {"input": "tls_min_version = TLSv1.2\n"
                          "TLS_MIN_VERSION = TLSv1.3\n",
                 "params": {"key": "TLS_MIN_VERSION", "case_sensitive": True}},
        "kv05": {"input": "# feature_flag = off\nfeature_flag = on\n",
                 "params": {"key": "feature_flag", "active_only": True}},
        "kv06": {"input": "worker,region\n1,eu-west-1\n2,ap-south-1\n"
                          "3,us-east-2\n",
                 "params": {"csv_row": "2", "csv_col": "region"}},
        "kv07": {"input": "[pool]\nworkers = 4\ncpu = 2\n\n"
                          "[pool production]\n[pool]\nworkers = 16\ncpu = 8\n",
                 "params": {"key": "workers", "section": "pool", "last": True}},
        "kv08": {"input": 'checkout_branch =   "release/2.0"   # keep\n',
                 "params": {"key": "checkout_branch", "strip_comment": True}},
        "re01": {"input": "sensors = 10, 22, 30\n",
                 "params": {"how": "digits_join"}},
        "re02": {"input": "server = host=web1 port=8000,8001;\n",
                 "params": {"how": "first_port"}},
        "re03": {"input": 'label = "ab\\"cd" end\n',
                 "params": {"how": "quoted"}},
        "re04": {"input": "v6 host is ::1 and v4 host is 10.0.0.1\n",
                 "params": {"how": "dotted_quad"}},
        "re05": {"input": "version = 2.10\n",
                 "params": {"how": "version"}},
        "re06": {"input": "red blue|red\n",
                 "params": {"how": "word_count", "word": "red"}},
        "re07": {"input": "Contact: Ada+L@example.com now\n",
                 "params": {"how": "email_local"}},
        "re08": {"input": "id = 007-42\n",
                 "params": {"how": "trailing_int"}},
    }


def main() -> int:
    corpus = _corpus()
    tasks = []
    for tid, kind, prompt, diff, note in TASK_TABLE:
        entry = corpus[tid]
        task = {
            "task_id": tid,
            "kind": kind,
            "prompt": prompt,
            "input": entry["input"],
            "params": entry.get("params", {}),
            "difficulty": diff,
            "naive_answer": NAIVE[tid],
            "note": note,
        }
        task["answer"] = verify.expected_answer(task)
        tasks.append(task)

    # --- corpus invariants: the A/B experiment is a fact of the corpus ------
    seen = set()
    for t in tasks:
        assert t["task_id"] not in seen, f"duplicate task id {t['task_id']}"
        seen.add(t["task_id"])
        assert t["answer"] != "", f"{t['task_id']}: oracle produced empty answer"
        if t["difficulty"] == 0:
            assert t["naive_answer"] != t["answer"], (
                f"{t['task_id']}: naive policy must NOT match the oracle "
                f"(got {t['naive_answer']!r} == {t['answer']!r})")
        else:
            assert t["naive_answer"] == t["answer"], (
                f"{t['task_id']}: easy task, naive policy must match the "
                f"oracle ({t['naive_answer']!r} != {t['answer']!r})")

    hard = [t["task_id"] for t in tasks if t["difficulty"] == 0]
    assert len(hard) == 6, f"expected 6 hard tasks, got {len(hard)}: {hard}"

    OUT.write_text(json.dumps({"tasks": tasks}, indent=2, sort_keys=True) + "\n")
    print(f"gen_inputs: wrote {OUT} ({len(tasks)} tasks, {len(hard)} hard: "
          f"{', '.join(hard)})")
    for t in tasks:
        if t["difficulty"] == 0:
            print(f"  {t['task_id']}: oracle={t['answer']!r} "
                  f"naive={t['naive_answer']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
