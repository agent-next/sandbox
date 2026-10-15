"""Collect the exact independently graded states. No local simulation."""

import hashlib
import json
from pathlib import Path
import os
import sys
import tempfile

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
sys.path.insert(0, str(DEMO / "judge"))
import grade
from selftest import checked_verdict, selftest_on_lease


def main():
    data = HERE / "data"
    data.mkdir(exist_ok=True)
    (HERE / "work").mkdir(exist_ok=True)
    key = os.environ.get("SBX_API_KEY") or os.environ.get("E2B_API_KEY")
    if not key:
        raise RuntimeError("export SBX_API_KEY")
    good = DEMO / "examples/good"
    with grade.Lease(key, 4) as lease:
        print(f"media collect: created {lease.id}", flush=True)
        test = selftest_on_lease(lease, str(good), str(data / "selftest.json"))
        assert test["ok"], "media self-test failed"
        with tempfile.TemporaryDirectory(dir=HERE / "work") as tmp:
            tmp = Path(tmp)
            for name, policy in (("trained", good / "policy.npz"),
                                 ("untrained", good / "step0.npz")):
                (tmp / "policy.npz").write_bytes(policy.read_bytes())
                rep = grade.grade_on_lease(lease, str(tmp), "101,202,303",
                                           64, 500, 1.0, trace=True,
                    remote_policy=("~/go1mutants/mutants/random-init/policy.npz"
                                   if name == "untrained" else None))
                v = checked_verdict(rep)
                assert v["ok"] == (name == "trained"), f"unexpected {name} verdict"
                if name == "untrained":
                    contents = lease.fetch_file(
                        "~/go1mutants/mutants/random-init/policy.npz")
                    assert hashlib.sha256(contents).hexdigest() == v["policy_sha256"]
                    (data / "untrained-policy.npz").write_bytes(contents)
                (data / f"{name}.json").write_text(json.dumps(v, indent=2, sort_keys=True) + "\n")
                for seed in (101, 202, 303):
                    contents = lease.fetch_file(f"~/go1judge/traces/seed-{seed}.npz")
                    assert hashlib.sha256(contents).hexdigest() == v["traces"][str(seed)]
                    (data / f"{name}-{seed}.npz").write_bytes(contents)
                print(f"media collect: {name} measured={v['measured']}", flush=True)


if __name__ == "__main__":
    main()
