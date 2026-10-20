// layerfs-race judge — reads the LayerFS Store through the SDK and re-runs
// the pinned suite itself. It never trusts race.json for the winner:
// race.json only locates the project and carries claims the judge verifies.
//
// Usage: node grader.mjs <race.json> <verdict-out.json>
// Env: RACE_SRC (bugged tree), RACE_PROJECT, LAYERFS_*, BASELINE_PASS,
// CORRECT_INDEX. Prints nothing; the verdict goes to <verdict-out.json>.
import { execSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { performance } from "node:perf_hooks";
import { LayerFS } from "@layerfs/sdk";
import { LayerFSOperator } from "@layerfs/sdk/operator";

const [, , RACE_PATH, OUT_PATH] = process.argv;
const SRC = process.env.RACE_SRC;
const PROJECT = process.env.RACE_PROJECT;
const VOLUME = process.env.LAYERFS_VOLUME;
const HOME_DIR = process.env.LAYERFS_HOME;
const BASELINE_PASS = Number(process.env.BASELINE_PASS);
const CORRECT = Number(process.env.CORRECT_INDEX);
const K = 8;
// The oracle: the pinned suite on a judge-fixed file list (RACE_TEST_FILES is
// set by grade.sh before the artifact runs) with config/package loading off,
// so the artifact cannot rig the run through .mocharc, package.json, or added
// and removed test files.
const SUITE = `npx mocha --no-config --no-package --exit --require test/support/env --reporter dot --check-leaks ${process.env.RACE_TEST_FILES ?? "test/ test/acceptance/"}`;
// The suite command preserves the mocha exit status: the log keeps the full
// output, the summary is grepped out, and SUITE_EXIT carries mocha's code.
const SUITE_CMD = `rm -f /tmp/judge-suite-$$.log; ${SUITE} > /tmp/judge-suite-$$.log 2>&1; rc=$?; grep -E "[0-9]+ (passing|failing)" /tmp/judge-suite-$$.log | tail -5; echo "SUITE_EXIT:$rc"; rm -f /tmp/judge-suite-$$.log; exit $rc`;
const BUGGED_FILE = "lib/application.js";
const STORE_THRESHOLD = 0.25 * K; // x source bytes (SPEC gate 7)
const FORK_MEDIAN_MAX = 0.05;     // s (SPEC gate 8)

const du = (p) => Number(execSync(`sudo du -sb ${p}`).toString().split("\t")[0]);
const counts = (stdout) => ({
  passing: +(/(\d+) passing/.exec(stdout || "")?.[1] ?? -1),
  failing: +(/(\d+) failing/.exec(stdout || "")?.[1] ?? 0),
});
const parseSuite = (stdout) => ({
  ...counts(stdout),
  exit: +(/SUITE_EXIT:(\d+)/.exec(stdout || "")?.[1] ?? -1),
});

const gates = [];
const timing = { wall_s: {}, race: null };
const gate = (name, pass, detail) => gates.push({ name, pass: !!pass, detail: String(detail) });
const wall = async (name, fn) => {
  const s = performance.now();
  const v = await fn();
  timing.wall_s[name] = +((performance.now() - s) / 1000).toFixed(1);
  return v;
};

const verdict = { schema: "agent-next/layerfs-race-verdict@1", verdict: "FAIL", gates, timing };
const finish = () => {
  verdict.verdict = gates.every((g) => g.pass) ? "PASS" : "FAIL";
  writeFileSync(OUT_PATH, JSON.stringify(verdict, null, 1));
};
process.on("uncaughtException", (e) => {
  gates.push({ name: "judge-error", pass: false, detail: `${e.code ?? "error"} ${e.message}` });
  try { finish(); } finally { process.exit(0); }
});
process.on("unhandledRejection", (e) => {
  gates.push({ name: "judge-error", pass: false, detail: `${e?.code ?? "error"} ${e?.message ?? e}` });
  try { finish(); } finally { process.exit(0); }
});

// --- artifact gate: the run completed and produced a consistent manifest ---
let race = null;
try { race = JSON.parse(readFileSync(RACE_PATH, "utf8")); } catch { /* stays null */ }
timing.race = race?.steps ?? null;
gate("artifact",
  race !== null && race.project === PROJECT && race.volume === VOLUME
    && typeof race.claimed_winner === "string" && typeof race.published === "string",
  race === null ? "race.json missing or unreadable"
    : race.project !== PROJECT || race.volume !== VOLUME
      ? "race.json names a different project or Store volume"
      : `manifest ok (winner claim ${race.claimed_winner})`);
if (race === null) { await finish(); process.exit(0); }

const lf = new LayerFS(PROJECT);
const op = new LayerFSOperator(lf);

// --- bug-scope: the injected bug breaks 1..50 tests of the pinned suite ---
const bugged = await wall("bugged_suite", () => {
  try {
    const out = execSync(`cd ${SRC} && ${SUITE_CMD}`, { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
    return parseSuite(out);
  } catch (e) {
    // a non-zero suite exit lands here; the marker still carries the code
    return parseSuite((e.stdout ?? "").toString());
  }
});
gate("bug-scope", bugged.failing >= 1 && bugged.failing <= 50,
  `${bugged.failing} failing on the bugged tree (allowed 1-50)`);

// --- branches: agent-0..7 exist, each with >= 1 via:"exec" commit ---------
const branchProblems = await wall("branches", async () => {
  const problems = [];
  for (let i = 0; i < K; i++) {
    const name = `agent-${i}`;
    try {
      const { items } = await lf.branch.list_commits(name, 50, 0);
      if (!items.some((c) => c.via === "exec")) problems.push(`${name}: no via:exec commit`);
    } catch {
      problems.push(`${name}: missing`);
    }
  }
  return problems;
});
gate("branches", branchProblems.length === 0,
  branchProblems.length ? branchProblems.join("; ") : "agent-0..7 present, each with via:exec commits");

// --- main-isolation: only publish touched main; the pre-publish layer is
// --- the bugged tree, byte-identical --------------------------------------
let baseLayerId = null;
const iso = await wall("isolation", async () => {
  const snap = await op.inspect.snapshot();
  const main = snap.branches.find((b) => b.name === "main");
  const layer = snap.layers.find((l) => l.id === main?.base);
  const buggedText = readFileSync(join(SRC, BUGGED_FILE), "utf8");
  const detail = { layers: snap.layers.length, head: main?.head ?? null, source: layer?.sourceBranch ?? null };
  if (!layer || main?.head !== null || snap.layers.length !== 2 || layer.sourceBranch !== `agent-${CORRECT}`) {
    return { ok: false, detail };
  }
  const parent = snap.layers.find((l) => l.id === layer.parent);
  baseLayerId = parent?.id ?? null;
  let before = "";
  try { before = (await lf.fs.read(parent.id, `/${BUGGED_FILE}`)).text; } catch { /* stays empty */ }
  return { ok: before === buggedText, detail: { ...detail, prePublishByteIdentical: before === buggedText } };
});
gate("main-isolation", iso.ok,
  iso.ok ? `main moved only via publish (layer source ${iso.detail.source}); pre-publish layer holds the bugged ${BUGGED_FILE} byte-identical`
    : `layers=${iso.detail.layers} main.head=${iso.detail.head} source=${iso.detail.source} prePublish=${iso.detail.prePublishByteIdentical ?? "n/a"}`);

// --- winner-is-a-branch: exactly one agent-i diffs empty vs main, i === CORRECT
const matches = await wall("diffs", async () => {
  const found = [];
  for (let i = 0; i < K; i++) {
    try {
      const { items } = await lf.branch.diff_branches("main", `agent-${i}`);
      if (items.length === 0) found.push(i);
    } catch { /* missing branch: not a match */ }
  }
  return found;
});
const measuredWinner = matches.length === 1 ? matches[0] : null;
gate("winner-is-a-branch",
  measuredWinner === CORRECT && race.claimed_winner === `agent-${CORRECT}` && race.published === `agent-${CORRECT}`,
  `empty diff vs main: ${matches.map((i) => `agent-${i}`).join(", ") || "none"}; claimed ${race.claimed_winner}; expected agent-${CORRECT}`);

// --- oracle-intact: vs the bugged base layer, no agent branch and no main
// may change anything outside /lib/ — protects the test oracle (test files,
// .mocharc-style configs, package.json, node_modules) from the artifact. The
// artifact itself writes nothing outside candidate-patch edits, so any other
// changed path fails. (branch.fork accepts a Layer id, so the judge forks
// the pre-publish layer into "judge-base" and diffs every ref against it.)
const oracle = await wall("oracle", async () => {
  if (!baseLayerId) return { ok: false, bad: ["no pre-publish base layer found"] };
  try {
    await lf.branch.fork("judge-base", baseLayerId);
  } catch (e) {
    return { ok: false, bad: [`judge-base fork failed: ${e.code ?? e.message ?? e}`] };
  }
  const bad = [];
  for (const r of ["main", ...[...Array(K).keys()].map((i) => `agent-${i}`)]) {
    try {
      const { items } = await lf.branch.diff_branches("judge-base", r, 500, 0);
      for (const it of items) {
        if (!String(it.path ?? "").startsWith("/lib/")) bad.push(`${r}:${it.kind ?? "?"}${it.path ?? "?"}`);
      }
    } catch (e) {
      bad.push(`${r}: diff failed (${e.code ?? e.message ?? e})`);
    }
  }
  return { ok: bad.length === 0, bad };
});
gate("oracle-intact", oracle.ok,
  oracle.ok
    ? "every branch/main change vs the bugged base is confined to /lib/"
    : `changes outside /lib/: ${oracle.bad.slice(0, 8).join("; ")}${oracle.bad.length > 8 ? ` (+${oracle.bad.length - 8} more)` : ""}`);

// --- the judge re-runs the pinned suite on main and every losing branch ---
// main is a published Layer, not a mountable Branch: fork judge-main off it
// (zero-copy, identical tree) and mount that.
const loserIdx = [...Array(K).keys()].filter((i) => i !== measuredWinner);
const refs = ["main", ...loserIdx.map((i) => `agent-${i}`)];
const suites = await wall("suites", async () => {
  try { await lf.branch.fork("judge-main", "main"); } catch { /* main may not exist */ }
  const ids = [];
  for (const _ of refs) ids.push(await lf.sandbox.create());
  try {
    return await Promise.all(ids.map(async (id, k) => {
      const ref = refs[k];
      const out = { ref };
      let m;
      try {
        m = await lf.sandbox.mount(id, ref === "main" ? "judge-main" : ref);
        const r = await lf.sandbox.exec(id, m.path, SUITE_CMD, "judge re-runs the suite");
        Object.assign(out, parseSuite(r.stdout), { exec_exit: r.exitCode });
      } catch (e) {
        out.error = e.code ?? String(e.message ?? e);
      }
      if (m) await lf.sandbox.unmount(id, m.path, { discard: true }).catch(() => {});
      await lf.sandbox.close(id).catch(() => {});
      return out;
    }));
  } finally {
    for (const id of ids) await lf.sandbox.close(id).catch(() => {});
  }
});
const mainSuite = suites.find((s) => s.ref === "main") ?? {};
gate("winner-green",
  mainSuite.exit === 0 && mainSuite.failing === 0 && mainSuite.passing === BASELINE_PASS,
  `main: ${mainSuite.passing ?? "error"} passing / ${mainSuite.failing ?? "?"} failing, suite exit ${mainSuite.exit ?? "?"} (baseline ${BASELINE_PASS})`);
const redReport = suites.filter((s) => s.ref !== "main").map((s) => `${s.ref}:${s.failing ?? s.error}`);
gate("losers-red",
  loserIdx.length >= 7 && suites.filter((s) => s.ref !== "main").every((s) => (s.failing ?? 0) >= 1),
  redReport.join(" "));

// --- storage: Store volume bytes <= 0.25 x K x source bytes ---------------
const storeBytes = await wall("storage", () => du(`/var/lib/docker/volumes/${VOLUME}/_data`));
timing.store_bytes = storeBytes;
timing.sealed_home_bytes = du(HOME_DIR);
timing.source_bytes = du(SRC);
timing.store_ratio = +(storeBytes / timing.source_bytes).toFixed(4);
gate("storage", storeBytes <= STORE_THRESHOLD * timing.source_bytes,
  `store <= ${STORE_THRESHOLD}x source bytes`);

// --- conflict-refused: merging two same-hunk candidates rejects "Conflict" -
await wall("conflict", async () => {
  try {
    await lf.branch.merge("agent-0", "agent-1", "judge-merge", "judge conflict check");
    gate("conflict-refused", false, "merge was not refused");
  } catch (e) {
    const files = (e.detail?.conflicts ?? []).map((c) => c.path);
    gate("conflict-refused", e.code === "Conflict" && files.includes(`/${BUGGED_FILE}`),
      `${e.code ?? "thrown"} on ${files.join(", ") || "no file named"}`);
  }
});

// --- fork-latency: median branch.fork over forks 2..8 <= 0.050 s -----------
const forkTimes = await wall("forks", async () => {
  const times = [];
  for (let i = 0; i < K; i++) {
    const s = performance.now();
    await lf.branch.fork(`judge-${i}`);
    times.push(+((performance.now() - s) / 1000).toFixed(4));
  }
  return times;
});
const tail = forkTimes.slice(1).sort((a, b) => a - b);
const median = tail[Math.floor(tail.length / 2)];
timing.fork_s = forkTimes;
timing.fork_median_s = median;
gate("fork-latency", median <= FORK_MEDIAN_MAX, `median fork <= ${FORK_MEDIAN_MAX} s`);

await finish();

// close the service Sandbox connection so node can exit
for (const id of [...lf.sandboxes]) await lf.sandbox.close(id).catch(() => {});
process.exit(0);
