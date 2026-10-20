// layerfs-race — the artifact under test.
//
// Eight agents race to fix the same injected bug in a pinned express tree,
// each on its own copy-on-write LayerFS branch inside one Store. Every agent
// mounts its branch in a LayerFS Sandbox, applies its candidate patch, runs
// the pinned mocha suite, and commits. The run demonstrates that merging two
// candidates touching the same hunk is refused, then publishes the one green
// branch to main.
//
// The script writes race.json (project name, Store volume, claimed winner,
// per-step timings) and leaves the project and its Store volume for the
// judge, which re-checks everything itself — see SPEC.md.
//
// Env: RACE_SRC (bugged source tree), RACE_PROJECT, RACE_OUT, plus the
// usual LAYERFS_HOME / LAYERFS_VOLUME / LAYERFS_DOCKER / LAYERFS_IMAGE /
// LAYERFS_DAEMON the SDK reads.
import { readFileSync, writeFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { LayerFS } from "@layerfs/sdk";

const HERE = dirname(fileURLToPath(import.meta.url));
const K = 8;
const SRC = process.env.RACE_SRC;
const PROJECT = process.env.RACE_PROJECT ?? "race";
const OUT = process.env.RACE_OUT ?? join(HERE, "race.json");
const SUITE = "npx mocha --exit --require test/support/env --reporter dot --check-leaks test/ test/acceptance/";

if (!SRC) throw new Error("RACE_SRC must point at the bugged source tree");

const CANDIDATES = readdirSync(join(HERE, "candidates")).filter((f) => f.endsWith(".patch")).sort();
if (CANDIDATES.length !== K) throw new Error(`need ${K} candidate patches, found ${CANDIDATES.length}`);

const timed = async (fn) => {
  const s = performance.now();
  const v = await fn();
  return [v, +((performance.now() - s) / 1000).toFixed(3)];
};

const lf = new LayerFS(PROJECT);
const sandboxes = [];
const steps = {};

try {
  let v, dt;
  [v, steps.init_s] = await timed(() => lf.project.init(SRC));

  steps.fork_s = [];
  for (let i = 0; i < K; i++) {
    [, dt] = await timed(() => lf.branch.fork(`agent-${i}`));
    steps.fork_s.push(dt);
  }

  // Sandboxes are created sequentially in 0.1.7 (project ownership lock).
  steps.create_s = [];
  for (let i = 0; i < K; i++) {
    [v, dt] = await timed(() => lf.sandbox.create());
    sandboxes.push(v);
    steps.create_s.push(dt);
  }

  // [[agents]] each agent works its own branch in its own Sandbox
  steps.agents = await Promise.all(sandboxes.map(async (id, i) => {
    const agent = `agent-${i}`;
    const o = { agent, candidate: CANDIDATES[i] };
    let r, s;
    [r, s] = await timed(() => lf.sandbox.mount(id, agent));
    o.mount_s = s;
    const path = r.path;
    const b64 = readFileSync(join(HERE, "candidates", CANDIDATES[i])).toString("base64");
    [r, s] = await timed(() => lf.sandbox.exec(id, path,
      `echo ${b64} | base64 -d > /tmp/candidate.patch && (patch -s -p1 < /tmp/candidate.patch || git apply -p1 /tmp/candidate.patch)`,
      `apply ${CANDIDATES[i]}`));
    o.apply_s = s;
    o.apply_exit = r.exitCode;
    [r, s] = await timed(() => lf.sandbox.exec(id, path, `${SUITE} 2>&1 | grep -E "[0-9]+ (passing|failing)" | tail -5`, "run the pinned suite"));
    o.test_s = s;
    o.test_exit = r.exitCode;
    o.passing = +(/(\d+) passing/.exec(r.stdout || "")?.[1] ?? -1);
    o.failing = +(/(\d+) failing/.exec(r.stdout || "")?.[1] ?? 0);
    [r, s] = await timed(() => lf.sandbox.commit(id, path, { message: `candidate ${i} applied and tested` }));
    o.commit_s = s;
    o.head = r?.head ?? null;
    [r, s] = await timed(() => lf.sandbox.unmount(id, path));
    o.unmount_s = s;
    return o;
  }));
  // [[/agents]]

  const greens = steps.agents.filter((a) => a.failing === 0 && a.passing > 0);
  if (greens.length !== 1) throw new Error(`expected exactly one green candidate, got ${greens.map((a) => a.agent)}`);
  const winner = greens[0].agent;

  // Two candidates edit the same hunk of lib/application.js: their merge must
  // be refused with code "Conflict".
  try {
    steps.merge = { kind: (await lf.branch.merge("agent-0", "agent-1", "race-merge", "merge two candidates")).kind };
  } catch (e) {
    steps.merge = { code: e.code, files: (e.detail?.conflicts ?? []).map((c) => c.path) };
  }

  [v, steps.publish_s] = await timed(() => lf.branch.publish(winner));
  steps.publish = { kind: v.kind, layer: v.publishedLayer?.id ?? v.layer };

  writeFileSync(OUT, JSON.stringify({
    project: PROJECT,
    volume: process.env.LAYERFS_VOLUME,
    claimed_winner: winner,
    published: winner,
    steps,
  }, null, 1));
} finally {
  for (const id of sandboxes) await lf.sandbox.close(id).catch(() => {});
}
