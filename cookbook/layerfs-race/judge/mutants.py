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
    # the patch lands via fs.write on the branch (via:"fs"), never through a
    # sandbox exec — so no branch earns a via:"exec" commit and the branches
    # gate must kill it. The suite still runs on a mount of each branch.
    new = '''
  steps.agents = await Promise.all(sandboxes.map(async (id, i) => {
    const agent = `agent-${i}`;
    const o = { agent, candidate: CANDIDATES[i] };
    let r, s;
    [r, s] = await timed(() => lf.fs.write(agent, "/lib/application.js",
      readFileSync(join(SRC, "lib/application.js"), "utf8")
        .replace(/^.*subdomain offset.*$/m,
          readFileSync(join(HERE, "candidates", CANDIDATES[i]), "utf8")
            .split("\\n").find((l) => /^\\+(?!\\+\\+)/.test(l)).slice(1)),
      `apply ${CANDIDATES[i]} via fs.write`));
    o.apply_s = s;
    [r, s] = await timed(() => lf.sandbox.mount(id, agent));
    o.mount_s = s;
    const path = r.path;
    [r, s] = await timed(() => lf.sandbox.exec(id, path,
      `${SUITE} 2>&1 | grep -E "[0-9]+ (passing|failing)" | tail -5`,
      "run the pinned suite"));
    o.test_s = s;
    o.test_exit = r.exitCode;
    o.passing = +(/(\\d+) passing/.exec(r.stdout || "")?.[1] ?? -1);
    o.failing = +(/(\\d+) failing/.exec(r.stdout || "")?.[1] ?? 0);
    [r, s] = await timed(() => lf.sandbox.unmount(id, path));
    o.unmount_s = s;
    return o;
  }));
'''
    return region(src, "  // [[agents]]", "  // [[/agents]]", new, "fs-write-only")


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
    # only 7 agents race; agent-7 is never forked. One patch is dropped too,
    # so the candidate-count preflight passes and the run reaches the SDK —
    # the kill must come from the missing-branch check, not the artifact gate.
    src = sub(src, "const K = 8;", "const K = 7;", "seven-branches")
    return sub(src,
               '.filter((f) => f.endsWith(".patch")).sort();',
               '.filter((f) => f.endsWith(".patch")).sort().slice(0, 7);',
               "seven-branches")


def mut_doctored_base(src):
    # inits the project from a doctored copy of the source — an extra
    # .mocharc.js outside lib/ — so every branch shares a poisoned base and
    # the diff-vs-base gates see nothing. The base-intact full-tree digest
    # gate must kill it.
    new = '''[v, steps.init_s] = await timed(async () => {
    const { execSync } = await import("node:child_process");
    const { mkdtempSync } = await import("node:fs");
    const { tmpdir } = await import("node:os");
    const d = mkdtempSync(join(tmpdir(), "doctored-"));
    execSync(`cp -a ${SRC}/. ${d}/`);
    writeFileSync(join(d, ".mocharc.js"), "module.exports = {};\\n");
    return lf.project.init(d);
  });'''
    return sub(src, "[v, steps.init_s] = await timed(() => lf.project.init(SRC));",
               new, "doctored-base")


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
    ("doctored-base", mut_doctored_base),
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
