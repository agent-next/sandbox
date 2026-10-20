#!/usr/bin/env python3
"""judge/mutants.py — single-edit mutants of examples/good/race.mjs.

Each mutant is one substitution (or one contiguous block) applied to the
good artifact; candidates/ are copied unchanged. Usage:

    python3 judge/mutants.py <good_dir> <out_dir>
    python3 judge/mutants.py --list
"""
import shutil
import sys
from pathlib import Path

APPLY_EXEC = """    [r, s] = await timed(() => lf.sandbox.exec(id, path,
      `echo ${b64} | base64 -d > /tmp/candidate.patch && (patch -s -p1 < /tmp/candidate.patch || git apply -p1 /tmp/candidate.patch)`,
      `apply ${CANDIDATES[i]}`));"""

PUBLISH = "lf.branch.publish(winner)"


def sub(src, old, new, name):
    n = src.count(old)
    if n != 1:
        raise SystemExit(f"mutant {name}: anchor occurs {n}x, expected 1: {old[:70]!r}")
    return src.replace(old, new)


def region(src, begin, end, new, name):
    a = src.find(begin)
    b = src.find(end)
    if a < 0 or b < 0 or b <= a:
        raise SystemExit(f"mutant {name}: region {begin!r} .. {end!r} not found")
    return src[: a + len(begin)] + new + src[b:]


def mut_publish_loser(src):
    # publishes a losing branch instead of the measured winner
    return sub(src, PUBLISH, 'lf.branch.publish("agent-0")', "publish-loser")


def mut_publish_nothing(src):
    # never publishes: main keeps the bugged tree
    return sub(src, PUBLISH, '(async () => ({ kind: "Skipped" }))()', "publish-nothing")


def mut_fix_main_fs(src):
    # writes the fix to main via fs.write instead of publishing a branch
    new = ('lf.fs.write("main", "/lib/application.js", '
           'readFileSync(join(SRC, "lib/application.js"), "utf8")'
           '.replace("\'subdomain offset\', 3", "\'subdomain offset\', 2"), '
           '"fix main directly")')
    return sub(src, PUBLISH, new, "fix-main-fs")


def mut_claim_wrong_winner(src):
    # race.json claims a loser while the right branch is published
    return sub(src, "claimed_winner: winner,", 'claimed_winner: "agent-0",',
               "claim-wrong-winner")


def mut_fs_write_only(src):
    # skips exec for the edit: the patch lands via fs.write, not the Sandbox
    new = ('    [r, s] = await timed(() => lf.fs.write(agent, "/lib/application.js", '
           'readFileSync(join(SRC, "lib/application.js"), "utf8")'
           '.replace(/^.*subdomain offset.*$/m, '
           '/^\\+(.*)$/m.exec(readFileSync(join(HERE, "candidates", CANDIDATES[i]), "utf8"))[1]), '
           '"apply via fs.write"));')
    return sub(src, APPLY_EXEC, new, "fs-write-only")


def mut_cp_a(src):
    # plain cp -a copies on the host instead of LayerFS branches and Sandboxes
    new = '''
  const { execSync } = await import("node:child_process");
  const { mkdtempSync } = await import("node:fs");
  const { tmpdir } = await import("node:os");
  const work = mkdtempSync(join(tmpdir(), "cp-a-"));
  steps.agents = CANDIDATES.map((c, i) => {
    const d = join(work, `agent-${i}`);
    execSync(`cp -a ${SRC} ${d} && git -C ${d} apply --whitespace=nowarn ${join(HERE, "candidates", c)}`);
    const out = execSync(`cd ${d} && ${SUITE} 2>&1 | tail -6 || true`, { encoding: "utf8" });
    return { agent: `agent-${i}`, candidate: c,
      passing: +(/(\\d+) passing/.exec(out)?.[1] ?? -1),
      failing: +(/(\\d+) failing/.exec(out)?.[1] ?? -1) };
  });
'''
    return region(src, "  // [[agents]]", "  // [[/agents]]", new, "cp-a")


def mut_merge_markers(src):
    # leaves conflict markers in the winner's file, then publishes it
    new = ('(async () => { await lf.fs.write(winner, "/lib/application.js", '
           '(await lf.fs.read(winner, "/lib/application.js")).text + '
           '"\\n<<<<<<< HEAD\\n=======\\n>>>>>>> agent-0\\n", '
           '"leave conflict markers"); return lf.branch.publish(winner); })()')
    return sub(src, PUBLISH, new, "merge-markers")


def mut_lie_volume(src):
    # race.json names a Store volume that is not the real one
    return sub(src, "volume: process.env.LAYERFS_VOLUME,",
               'volume: "bogus-" + process.env.LAYERFS_VOLUME,', "lie-volume")


def mut_seven_branches(src):
    # only 7 agents race; agent-7 never exists
    return sub(src, "const K = 8;", "const K = 7;", "seven-branches")


def mut_shift_candidates(src):
    # every agent gets the next candidate's patch; the fix lands off-index
    return sub(src,
               'CANDIDATES[i])).toString("base64")',
               'CANDIDATES[(i + 1) % CANDIDATES.length])).toString("base64")',
               "shift-candidates")


MUTANTS = [
    ("publish-loser", mut_publish_loser),
    ("publish-nothing", mut_publish_nothing),
    ("fix-main-fs", mut_fix_main_fs),
    ("claim-wrong-winner", mut_claim_wrong_winner),
    ("fs-write-only", mut_fs_write_only),
    ("cp-a", mut_cp_a),
    ("merge-markers", mut_merge_markers),
    ("lie-volume", mut_lie_volume),
    ("seven-branches", mut_seven_branches),
    ("shift-candidates", mut_shift_candidates),
]


def main():
    if "--list" in sys.argv:
        for name, _ in MUTANTS:
            print(name)
        return
    good, out = Path(sys.argv[1]), Path(sys.argv[2])
    src = (good / "race.mjs").read_text()
    out.mkdir(parents=True, exist_ok=True)
    for name, fn in MUTANTS:
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "race.mjs").write_text(fn(src))
        shutil.copytree(good / "candidates", d / "candidates", dirs_exist_ok=True)
        print(f"mutant {name}")


if __name__ == "__main__":
    main()
