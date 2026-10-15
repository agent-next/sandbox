#!/usr/bin/env python3
"""Judge driver for the app-builder-preview demo. Invoked by grade.sh; see SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure   - size, react-based, reads spec.json at runtime
  gate 2 build       - npm ci + npm run build exit 0, dist/index.html produced
  gate 3 serve       - vite preview serves dist/ on localhost, GET / returns 200
  gate 4 flows       - 6 scripted browser flows asserting exact DOM state
  gate 5 hygiene     - dist under 250 KiB, zero console errors, reference-build
                       cross-check agreement

Every flow starts from a fresh browser context (clean localStorage), so the
expected numbers in SPEC.md hold per flow. The element ids the judge drives
come from judge/spec.json - never from the artifact.

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.expanduser("~"), ".tools", "app-builder-preview")
BROWSERS = os.path.join(TOOLS, "pw-browsers")
NPM_CACHE = os.path.join(TOOLS, "npm-cache")
CHROME_REV = "1243"

MAX_PKG_BYTES = 64 * 1024
MAX_APP_BYTES = 32 * 1024
BUILD_TIMEOUT_S = 300
SERVE_TIMEOUT_S = 30
MAX_DIST_BYTES = 250 * 1024

# Tool output quoted into a verdict problem message must not carry the
# per-run temp dir: two grades of the same artifact have to be
# byte-identical apart from `timing` (selftest.sh enforces it), and
# tempfile.mkdtemp picks a fresh name every run.
WORKDIR_PREFIX = "appbuilder-artifact-"
WORKDIR_RE = re.compile(r"appbuilder-(artifact|ref)-[A-Za-z0-9_]+")


def scrub_workdirs(value):
    """Replace every per-run scratch dir (the artifact copy and the
    reference build) with a stable placeholder, recursively, so a verdict
    that quotes tool output is reproducible."""
    if isinstance(value, str):
        return WORKDIR_RE.sub(r"appbuilder-\1-<workdir>", value)
    if isinstance(value, list):
        return [scrub_workdirs(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub_workdirs(v) for k, v in value.items()}
    return value

APP_PORT = 5317
REF_PORT = 5318

# The 6 scripted flows. Each entry: (name, todo texts added, zero-based item
# indexes to toggle, index to delete or None, filter to click or None,
# reload after steps). Assertions and expected numbers live in drive_flows.
FLOWS = [
    ("add", ["buy milk", "walk dog", "read book"], [], None, None, False),
    ("complete", ["task a", "task b"], [0], None, None, False),
    ("delete", ["buy milk", "walk dog", "read book"], [], 1, None, False),
    ("filter", ["a1", "a2", "a3"], [0], None, "active", False),
    ("persist", ["p1", "p2"], [0], None, None, True),
    ("stats", ["s1", "s2", "s3", "s4", "s5"], [0, 1], 2, None, False),
]


# ---------------------------------------------------------------- helpers


def check_shas(judge_dir):
    digests = {}
    for root, dirs, files in os.walk(judge_dir):
        dirs.sort()
        if os.path.basename(root) == "__pycache__":
            dirs[:] = []
            continue
        for name in sorted(files):
            if name.endswith(".pyc"):
                continue
            p = os.path.join(root, name)
            with open(p, "rb") as fh:
                digests[os.path.relpath(p, judge_dir)] = \
                    hashlib.sha256(fh.read()).hexdigest()
    return digests


def node_env():
    env = os.environ.copy()
    env["PATH"] = os.path.join(TOOLS, "node", "bin") + ":" + env.get("PATH", "")
    env["npm_config_cache"] = NPM_CACHE
    return env


def run_node(cmd, cwd=None, timeout=None):
    """Run a node/npm command with the pinned toolchain. Returns (rc, out, err)."""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, env=node_env())
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def require_browser():
    """Point Playwright at the judge-installed browsers (never the image's
    read-only /opt/ms-playwright) and fail loudly if setup.sh has not run."""
    marker = os.path.join(BROWSERS, f"chromium-{CHROME_REV}",
                          "INSTALLATION_COMPLETE")
    if not os.path.isfile(marker):
        print("grade.sh: judge chromium missing; run judge/setup.sh first",
              file=sys.stderr)
        raise SystemExit(2)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS


def free_port(preferred):
    """The preferred port if it is free, else an ephemeral one."""
    import socket
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                continue
            return s.getsockname()[1]
    raise RuntimeError("no free localhost port")


@contextmanager
def serve(app_dir, preferred_port):
    """Serve app_dir/dist with vite preview; yields the port it bound."""
    port = free_port(preferred_port)
    cmd = ["npx", "--no-install", "vite", "preview",
           "--port", str(port), "--strictPort"]
    # own process group: npx spawns vite as a child, and only killing the
    # whole group frees the port for the next gate
    proc = subprocess.Popen(cmd, cwd=app_dir, env=node_env(),
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        deadline = time.monotonic() + SERVE_TIMEOUT_S
        last_err = None
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"vite preview exited rc {proc.returncode}")
            try:
                with urllib.request.urlopen(f"http://localhost:{port}/",
                                            timeout=2) as resp:
                    if resp.status == 200:
                        break
            except Exception as exc:
                last_err = exc
                time.sleep(0.5)
        else:
            raise RuntimeError(f"vite preview not serving within "
                               f"{SERVE_TIMEOUT_S} s: {last_err}")
        yield port
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=10)


def provision_spec(app_dir, judge_dir):
    """The judge owns the neutral spec: it drops judge/spec.json where the
    build will publish it as /spec.json.

    A public/ directory in the artifact would shadow the judge's copy, so
    it is refused rather than merged - the artifact must not ship one.
    """
    if os.path.isdir(os.path.join(app_dir, "public")):
        raise RuntimeError("app ships a public/ directory; the judge "
                           "provisions spec.json itself")
    pub = os.path.join(app_dir, "public")
    os.makedirs(pub, exist_ok=True)
    shutil.copyfile(os.path.join(judge_dir, "spec.json"),
                    os.path.join(pub, "spec.json"))


# ---------------------------------------------------------------- gate 1


def gate_structure(app_dir):
    problems = []
    pkg_path = os.path.join(app_dir, "package.json")
    app_path = os.path.join(app_dir, "src", "App.jsx")

    if not os.path.isfile(pkg_path):
        problems.append("app/package.json missing")
    else:
        with open(pkg_path, "rb") as fh:
            raw = fh.read()
        if len(raw) > MAX_PKG_BYTES:
            problems.append(f"package.json {len(raw)} B > {MAX_PKG_BYTES} B")
        try:
            pkg = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append(f"package.json does not parse: {exc}")
            pkg = {}
        if "react" not in (pkg.get("dependencies") or {}):
            problems.append("package.json does not depend on react")

    if not os.path.isfile(app_path):
        problems.append("app/src/App.jsx missing")
    else:
        with open(app_path, "rb") as fh:
            raw = fh.read()
        if len(raw) > MAX_APP_BYTES:
            problems.append(f"App.jsx {len(raw)} B > {MAX_APP_BYTES} B")
        text = raw.decode("utf-8", "replace")
        if not re.search(r"import\s+.*\bfrom\s+['\"]react['\"]", text) and \
           "from 'react'" not in text and 'from "react"' not in text:
            problems.append("App.jsx does not import react")
        if not (re.search(r"['\"]/spec\.json['\"]", text)
                and "fetch(" in text):
            problems.append("App.jsx does not read spec.json at runtime "
                            "(no fetch of /spec.json found)")

    return {"pass": not problems, "problems": problems}


# ---------------------------------------------------------------- gates 2-5


def gate_build(app_dir):
    rc, out, err = run_node(["npm", "ci"], cwd=app_dir, timeout=BUILD_TIMEOUT_S)
    if rc != 0:
        return {"pass": False,
                "problems": [f"npm ci exited {rc}: {(err or out)[-300:]}"]}
    rc, out, err = run_node(["npm", "run", "build"], cwd=app_dir,
                            timeout=BUILD_TIMEOUT_S)
    if rc != 0:
        return {"pass": False,
                "problems": [f"npm run build exited {rc}: {(err or out)[-300:]}"]}
    dist_html = os.path.join(app_dir, "dist", "index.html")
    if not os.path.isfile(dist_html):
        return {"pass": False,
                "problems": ["dist/index.html missing after build"]}
    return {"pass": True, "problems": []}


def dist_bytes(app_dir):
    return sum(os.path.getsize(os.path.join(root, f))
               for root, _, files in os.walk(os.path.join(app_dir, "dist"))
               for f in files)


def gate_serve(app_dir):
    try:
        with serve(app_dir, APP_PORT) as port:
            with urllib.request.urlopen(
                    f"http://localhost:{port}/", timeout=5) as resp:
                if resp.status != 200:
                    return {"pass": False,
                            "problems": [f"GET / returned {resp.status}"]}
                body = resp.read().decode("utf-8", "replace")
                if 'id="root"' not in body and "id='root'" not in body:
                    return {"pass": False,
                            "problems": ["GET / body has no #root div"]}
                return {"pass": True, "problems": [], "port": port}
    except RuntimeError as exc:
        return {"pass": False, "problems": [str(exc)]}


def drive_flows(port, ids, shots_dir=None):
    """Drive the 6 scripted flows, each from a fresh browser context.

    Returns (flows, console_errors) where flows[name] = {pass, problems,
    state} and state is the observed final DOM state used both for the
    assertions here and for the reference cross-check.
    """
    from playwright.sync_api import sync_playwright

    flows = {}
    console_errors = []

    def snapshot(page):
        items = []
        for li in page.query_selector_all(f"#{ids['todo-list']} > li"):
            if not li.is_visible():
                continue
            text_el = li.query_selector(f"#{ids['todo-text']}")
            items.append({
                "text": text_el.inner_text() if text_el else None,
                "done": "done" in (li.get_attribute("class") or "").split(),
            })

        def stat(name):
            el = page.query_selector(f"#{ids[name]}")
            return el.inner_text().strip() if el else None

        active_filter = None
        for f in ("all", "active", "done"):
            btn = page.query_selector(f"#{ids['filter-' + f]}")
            if btn and "active" in (btn.get_attribute("class") or "").split():
                active_filter = f
        inp = page.query_selector(f"#{ids['todo-input']}")
        return {"items": items,
                "stats": {"total": stat("stats-total"),
                          "active": stat("stats-active"),
                          "done": stat("stats-done")},
                "active_filter": active_filter,
                "input_value": inp.input_value() if inp else None}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for name, texts, toggles, delete, filt, reload in FLOWS:
                problems = []
                # light colour scheme so the captured screenshots are
                # readable against dark video backgrounds; deterministic
                ctx = browser.new_context(viewport={"width": 1280,
                                                    "height": 800},
                                          color_scheme="light")
                page = ctx.new_page()
                page.on("console", lambda msg: (
                    console_errors.append(f"[{name}] {msg.text}")
                    if msg.type == "error" else None))
                page.on("pageerror", lambda err: (
                    console_errors.append(f"[{name}] {err}")))
                try:
                    page.goto(f"http://localhost:{port}/",
                              wait_until="networkidle")
                    page.wait_for_selector(f"#{ids['todo-input']}",
                                           timeout=15000)

                    for t in texts:
                        page.fill(f"#{ids['todo-input']}", t)
                        page.click(f"#{ids['todo-add']}")
                    lis = page.query_selector_all(
                        f"#{ids['todo-list']} > li")
                    for i in toggles:
                        lis[i].query_selector(
                            f"#{ids['todo-toggle']}").click()
                    if delete is not None:
                        lis = page.query_selector_all(
                            f"#{ids['todo-list']} > li")
                        lis[delete].query_selector(
                            f"#{ids['todo-delete']}").click()
                    if filt is not None:
                        page.click(f"#{ids['filter-' + filt]}")
                    if reload:
                        page.reload(wait_until="networkidle")
                        page.wait_for_selector(f"#{ids['todo-input']}",
                                               timeout=15000)
                    state = snapshot(page)

                    # ---- assertions (exact DOM equality; SPEC.md table)
                    def expect(cond, msg):
                        if not cond:
                            problems.append(msg)

                    if name == "add":
                        expect([i["text"] for i in state["items"]] == texts,
                               f"items {[i['text'] for i in state['items']]} "
                               f"!= {texts}")
                        expect(state["input_value"] == "",
                               "input not cleared after add")
                        expect(state["stats"]["total"] == "3",
                               f"stats-total {state['stats']['total']} != 3")
                    elif name == "complete":
                        expect(state["items"][0]["done"] is True,
                               "first item lacks 'done' class")
                        expect(state["stats"]["active"] == "1",
                               f"stats-active {state['stats']['active']} != 1")
                        expect(state["stats"]["done"] == "1",
                               f"stats-done {state['stats']['done']} != 1")
                        expect(state["stats"]["total"] == "2",
                               f"stats-total {state['stats']['total']} != 2")
                    elif name == "delete":
                        expect([i["text"] for i in state["items"]] ==
                               ["buy milk", "read book"],
                               f"remaining {[i['text'] for i in state['items']]} "
                               f"!= ['buy milk', 'read book']")
                        expect(state["stats"]["total"] == "2",
                               f"stats-total {state['stats']['total']} != 2")
                    elif name == "filter":
                        expect(len(state["items"]) == 2,
                               f"{len(state['items'])} visible li != 2")
                        expect(all(not i["done"] for i in state["items"]),
                               "a done item is visible under filter-active")
                        expect(state["active_filter"] == "active",
                               f"active filter button is "
                               f"{state['active_filter']}, not 'active'")
                    elif name == "persist":
                        expect(len(state["items"]) == 2,
                               f"{len(state['items'])} li after reload != 2")
                        expect(state["items"][0]["done"] is True,
                               "first item lost its done class after reload")
                        expect(state["stats"]["total"] == "2",
                               f"stats-total {state['stats']['total']} != 2")
                    elif name == "stats":
                        expect(state["stats"] == {"total": "4",
                                                 "active": "2",
                                                 "done": "2"},
                               f"stats {state['stats']} != "
                               f"{{'total': '4', 'active': '2', 'done': '2'}}")

                    if shots_dir:
                        os.makedirs(shots_dir, exist_ok=True)
                        page.screenshot(
                            path=os.path.join(shots_dir, f"{name}.png"))
                except Exception as exc:
                    problems.append(f"flow crashed: {type(exc).__name__}: "
                                    f"{exc}")
                    state = None
                finally:
                    ctx.close()
                flows[name] = {"pass": not problems, "problems": problems,
                               "state": state}
        finally:
            browser.close()
    return flows, console_errors


def gate_flows(app_dir, ids, shots_dir=None):
    try:
        with serve(app_dir, APP_PORT) as port:
            flows, console_errors = drive_flows(port, ids, shots_dir)
    except RuntimeError as exc:
        return {"pass": False, "problems": [str(exc)], "flows": {},
                "states": {}, "console_errors": []}
    all_pass = all(f["pass"] for f in flows.values()) and bool(flows)
    return {"pass": all_pass, "problems": [],
            "flows": {k: {"pass": v["pass"], "problems": v["problems"]}
                      for k, v in flows.items()},
            "states": {k: v["state"] for k, v in flows.items()},
            "console_errors": console_errors}


def run_reference(judge_dir, ids):
    """Build the judge-controlled reference app and drive it through the
    same 6 flows; return (ok, states, problems)."""
    ref_src = os.path.join(judge_dir, "ref_app")
    work = tempfile.mkdtemp(prefix="appbuilder-ref-")
    try:
        ref_dir = os.path.join(work, "ref")
        shutil.copytree(ref_src, ref_dir, ignore=shutil.ignore_patterns(
            "node_modules", "dist", "__pycache__"))
        provision_spec(ref_dir, judge_dir)
        g = gate_build(ref_dir)
        if not g["pass"]:
            return False, None, [f"reference build failed: {g['problems']}"]
        try:
            with serve(ref_dir, REF_PORT) as port:
                flows, errors = drive_flows(port, ids)
        except RuntimeError as exc:
            return False, None, [f"reference serve failed: {exc}"]
        problems = []
        for name, f in flows.items():
            if not f["pass"]:
                problems.append(f"reference flow {name}: {f['problems']}")
        if errors:
            problems.append(f"reference console errors: {errors[:3]}")
        if problems:
            return False, None, problems
        return True, {k: v["state"] for k, v in flows.items()}, []
    finally:
        shutil.rmtree(work, ignore_errors=True)


def gate_hygiene(app_dir, ids, flows_result):
    problems = []
    nbytes = dist_bytes(app_dir)
    if nbytes > MAX_DIST_BYTES:
        problems.append(f"dist {nbytes} B > {MAX_DIST_BYTES} B")

    console_errors = flows_result.get("console_errors", [])
    if console_errors:
        problems.append(f"{len(console_errors)} console error(s): "
                        f"{console_errors[:3]}")

    ref_ok, ref_states, ref_problems = run_reference(HERE, ids)
    if not ref_ok:
        problems.append(f"reference cross-check failed: {ref_problems}")
    else:
        states = flows_result.get("states", {})
        for name, *_ in FLOWS:
            if states.get(name) != ref_states.get(name):
                problems.append(
                    f"reference disagreement on flow {name}: "
                    f"artifact {states.get(name)} vs reference "
                    f"{ref_states.get(name)}")

    return {"pass": not problems, "problems": problems,
            "dist_bytes": nbytes, "console_errors": console_errors}


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--judge-dir")
    ap.add_argument("--shots", dest="shots_dir", metavar="DIR",
                    help="save one screenshot per flow here")
    args = ap.parse_args()

    require_browser()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
    with open(os.path.join(judge_dir, "spec.json")) as fh:
        elements = json.load(fh)["elements"]
    # The element names in spec.json are the DOM ids the judge drives; the
    # values are descriptions for the agent, never selectors.
    ids = {name: name for name in elements}

    sha_before = check_shas(judge_dir)
    app_dir = os.path.abspath(args.artifact)

    verdict = {"demo": "app-builder-preview",
               "artifact": os.path.basename(app_dir.rstrip("/")),
               "seed": args.seed, "gates": {}, "flows": {},
               "timing": {}, "judge_intact": False}
    rc = 0

    workdir = tempfile.mkdtemp(prefix="appbuilder-artifact-")
    try:
        # copy the artifact so it never touches judge/
        copied = os.path.join(workdir, "app")
        shutil.copytree(app_dir, copied,
                        ignore=shutil.ignore_patterns("node_modules", "dist"))

        def record(name, result):
            nonlocal rc
            verdict["gates"][name] = result
            if not result["pass"]:
                rc = 1

        t0 = time.monotonic()
        try:
            provision_spec(copied, judge_dir)
            record("structure", gate_structure(copied))
        except RuntimeError as exc:
            record("structure", {"pass": False, "problems": [str(exc)]})
        verdict["timing"]["structure_s"] = round(time.monotonic() - t0, 1)

        if rc == 0:
            t0 = time.monotonic()
            record("build", gate_build(copied))
            verdict["timing"]["build_s"] = round(time.monotonic() - t0, 1)

        if rc == 0:
            t0 = time.monotonic()
            record("serve", gate_serve(copied))
            verdict["timing"]["serve_s"] = round(time.monotonic() - t0, 1)

        if rc == 0:
            t0 = time.monotonic()
            g4 = gate_flows(copied, ids, args.shots_dir)
            verdict["timing"]["flows_s"] = round(time.monotonic() - t0, 1)
            verdict["gates"]["flows"] = {
                "pass": g4["pass"], "problems": g4["problems"]}
            verdict["flows"] = g4["flows"]
            verdict["states"] = g4["states"]
            if not g4["pass"]:
                rc = 1

        if rc == 0:
            t0 = time.monotonic()
            g5 = gate_hygiene(copied, ids, g4)
            verdict["timing"]["hygiene_s"] = round(time.monotonic() - t0, 1)
            verdict["gates"]["hygiene"] = g5
            if not g5["pass"]:
                rc = 1

        verdict["judge_intact"] = check_shas(judge_dir) == sha_before
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # strip the per-run scratch paths that tool output can quote, so two
    # grades of the same artifact differ only in `timing`
    verdict = scrub_workdirs(verdict)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
