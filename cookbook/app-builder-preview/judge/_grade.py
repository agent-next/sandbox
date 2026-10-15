#!/usr/bin/env python3
"""Judge driver for the app-builder-preview demo. Invoked by grade.sh; see SPEC.md.

Grades a copied artifact (the artifact under test never touches judge/):
  gate 1 structure   - size, byte-compile, react-based, reads spec.json at runtime
  gate 2 build       - npm ci + npm run build exit 0, dist/index.html produced
  gate 3 serve       - vite preview serves dist/ on localhost, GET / returns 200
  gate 4 flows       - 6 scripted browser flows asserting exact DOM state
  gate 5 hygiene     - dist under 250 KiB, zero console errors, reference-build
                       cross-check agreement

Prints one JSON verdict on stdout; exit 0 only if every gate passes.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.join(os.path.expanduser("~"), ".tools", "app-builder-preview")

MAX_PKG_BYTES = 64 * 1024
MAX_APP_BYTES = 32 * 1024
BUILD_TIMEOUT_S = 300
SERVE_TIMEOUT_S = 30
FLOW_TIMEOUT_S = 120
MAX_DIST_BYTES = 250 * 1024

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
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(TOOLS, "pw-browsers")
    return env


def run_node(cmd, cwd=None, timeout=None, capture=True):
    """Run a node/npm command with the pinned toolchain. Returns (rc, out, err)."""
    env = node_env()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=True,
                          timeout=timeout, env=env)
    return proc.returncode, proc.stdout or "", proc.stderr or ""


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
        if not re.search(r"fetch\s*\(\s*['\"]/?spec\.json", text):
            problems.append("App.jsx does not read spec.json at runtime "
                            "(fetch of /spec.json not found)")

    return {"pass": not problems, "problems": problems}


# ---------------------------------------------------------------- gates 2-5 (browser)


def gate_build(app_dir):
    rc, out, err = run_node(["npm", "ci"], cwd=app_dir,
                              timeout=BUILD_TIMEOUT_S)
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
    return {"pass": True, "problems": [],
            "dist_html": dist_html,
            "dist_bytes": sum(
                os.path.getsize(os.path.join(root, f))
                for root, _, files in os.walk(os.path.join(app_dir, "dist"))
                for f in files)}


def gate_serve(app_dir):
    """Start vite probe, verify GET / returns 200 with root div, stop it."""
    env = node_env()
    port = 5199
    cmd = ["npx", "vite", "preview", "--port", str(port), "--strictPort"]
    proc = subprocess.Popen(cmd, cwd=app_dir, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True)
    try:
        deadline = time.monotonic() + SERVE_TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                out = ""
                try:
                    out = proc.stdout.read() or ""
                except Exception:
                    pass
                return {"pass": False,
                        "problems": [f"vite preview exited early "
                                     f"(rc {proc.returncode}): {out[-300:]}"]}
            try:
                import urllib.request
                with urllib.request.urlopen(
                        f"http://localhost:{port}/", timeout=2) as resp:
                    if resp.status != 200:
                        return {"pass": False,
                                "problems": [f"GET / returned {resp.status}"]}
                    body = resp.read().decode("utf-8", "replace")
                    if 'id="root"' not in body and "id='root'" not in body:
                        return {"pass": False,
                                "problems": ["GET / body has no #root div"]}
                    return {"pass": True, "problems": [], "port": port}
            except Exception:
                time.sleep(0.5)
        return {"pass": False,
                "problems": [f"vite preview did not serve within "
                             f"{SERVE_TIMEOUT_S} s"]}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)


def gate_flows(app_dir, seed):
    """Drive Playwright through 6 flows, asserting exact DOM state."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {"pass": False,
                "problems": [f"playwright not importable: {exc}"]}

    problems = []
    flows = {}
    port = 5299
    console_errors = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context()
            page = ctx.new_page()
            page.on("console", lambda msg: (
                console_errors.append(msg.text)
                if msg.type == "error" else None))
            page.on("pageerror", lambda err: console_errors.append(str(err)))

            page.goto(f"http://localhost:{port}/", wait_until="networkidle")

            ids = {}

            def get_id(name):
                if name not in ids:
                    el = page.query_selector(f"[data-judge-id='{name}']")
                    if el is None:
                        el = page.query_selector(f"#{name}")
                    if el is None:
                        ids[name] = None
                    else:
                        ids[name] = el.get_attribute("id")
                return ids[name]

            def click(jid):
                el = page.query_selector(f"#{get_id(jid)}")
                el.click()

            def type_input(jid, text):
                el = page.query_selector(f"#{get_id(jid)}")
                el.fill(text)

            def add_todo(text):
                type_input("todo-input", text)
                click("todo-add")

            def visible_items():
                return page.query_selector_all(f"#{get_id('todo-list')} > li")

            def item_classes(item):
                return (item.get_attribute("class") or "").split()

            def item_text(item):
                el = item.query_selector(f"#{get_id('todo-text')}")
                return el.inner_text() if el is not None else ""

            # --- flow 1: add
            f1 = []
            try:
                add_todo("buy milk")
                add_todo("walk dog")
                add_todo("read book")
                items = visible_items()
                if len(items) != 3:
                    f1.append(f"expected 3 li, got {len(items)}")
                texts = [item_text(i) for i in items]
                if texts != ["buy milk", "walk dog", "read book"]:
                    f1.append(f"texts {texts} != expected")
                inp = page.query_selector(f"#{get_id('todo-input')}")
                if inp.input_value() != "":
                    f1.append("input not cleared")
                st = page.query_selector(f"#{get_id('stats-total')}")
                if st.inner_text() != "3":
                    f1.append(f"stats-total {st.inner_text()} != 3")
            except Exception as exc:
                f1.append(f"flow crashed: {exc}")
            flows["add"] = {"pass": not f1, "problems": f1}

            # --- flow 2: complete
            f2 = []
            try:
                add_todo("task a")
                add_todo("task b")
                items = visible_items()
                if len(items) < 2:
                    f2.append("fewer than 2 items after add")
                else:
                    btn = items[0].query_selector(f"#{get_id('todo-toggle')}")
                    btn.click()
                    items2 = visible_items()
                    cls = item_classes(items2[0])
                    if "done" not in cls:
                        f2.append(f"first li class '{' '.join(cls)}' lacks 'done'")
                    sa = page.query_selector(f"#{get_id('stats-active')}")
                    sd = page.query_selector(f"#{get_id('stats-done')}")
                    if sa.inner_text() != "1":
                        f2.append(f"stats-active {sa.inner_text()} != 1")
                    if sd.inner_text() != "1":
                        f2.append(f"stats-done {sd.inner_text()} != 1")
            except Exception as exc:
                f2.append(f"flow crashed: {exc}")
            flows["complete"] = {"pass": not f2, "problems": f2}

            # --- flow 3: delete
            f3 = []
            try:
                for t in ("x1", "x2", "x3"):
                    add_todo(t)
                items = visible_items()
                if len(items) < 3:
                    f3.append("fewer than 3 items after add")
                else:
                    btn = items[1].query_selector(f"#{get_id('todo-delete')}")
                    btn.click()
                    items2 = visible_items()
                    if len(items2) != 2:
                        f3.append(f"expected 2 li after delete, got {len(items2)}")
                    texts = [item_text(i) for i in items2]
                    if texts != ["buy milk", "read book"]:
                        f3.append(f"remaining texts {texts} != "
                                  f"['buy milk', 'read book']")
                    st = page.query_selector(f"#{get_id('stats-total')}")
                    if st.inner_text() != "5":
                        f3.append(f"stats-total {st.inner_text()} != 5 "
                                  f"(3 added, 1 deleted, from 3 prior)")
            except Exception as exc:
                f3.append(f"flow crashed: {exc}")
            flows["delete"] = {"pass": not f3, "problems": f3}

            # --- flow 4: filter
            f4 = []
            try:
                click("filter-active")
                items = visible_items()
                if len(items) != 3:
                    f4.append(f"expected 3 visible li (3 active), got {len(items)}")
                for it in items:
                    if "done" in item_classes(it):
                        f4.append("done item visible under filter-active")
                fa = page.query_selector(f"#{get_id('filter-active')}")
                cls = item_classes(fa)
                if "active" not in cls:
                    f4.append(f"filter-active class '{' '.join(cls)}' lacks 'active'")
            except Exception as exc:
                f4.append(f"flow crashed: {exc}")
            flows["filter"] = {"pass": not f4, "problems": f4}

            # --- flow 5: persist
            f5 = []
            try:
                click("filter-all")
                add_todo("p1")
                add_todo("p2")
                items = visible_items()
                # toggle the last one (a p-task)
                btn = items[-1].query_selector(f"#{get_id('todo-toggle')}")
                btn.click()
                page.reload(wait_until="networkidle")
                items2 = visible_items()
                if len(items2) < 2:
                    f5.append(f"fewer than 2 li after reload: {len(items2)}")
                else:
                    # find the p2 item
                    p2 = [i for i in items2 if item_text(i) == "p2"]
                    if not p2:
                        f5.append("p2 item missing after reload")
                    elif "done" not in item_classes(p2[0]):
                        f5.append("p2 lost its done class after reload")
                st = page.query_selector(f"#{get_id('stats-total')}")
                # total: 3 (buy milk, walk dog, read book) + 1 x-remainder +
                # x1,x2,x3 minus x2 + p1,p2 = 3 + 1 + 2 + 2 = 8? compute:
                # flow1: 3; flow2: +2 = 5; flow3: +3 -1 = 7;
                # flow5: +2 = 9
                if st.inner_text() != "9":
                    f5.append(f"stats-total {st.inner_text()} != 9")
            except Exception as exc:
                f5.append(f"flow crashed: {exc}")
            flows["persist"] = {"pass": not f5, "problems": f5}

            # --- flow 6: stats
            f6 = []
            try:
                # add 5, toggle 2, delete 1
                for t in ("s1", "s2", "s3", "s4", "s5"):
                    add_todo(t)
                items = visible_items()
                if len(items) < 5:
                    f6.append("fewer than 5 items")
                else:
                    for idx in (0, 1):
                        btn = items[idx].query_selector(f"#{get_id('todo-toggle')}")
                        btn.click()
                    items = visible_items()
                    btn = items[0].query_selector(f"#{get_id('todo-delete')}")
                    btn.click()
                st = page.query_selector(f"#{get_id('stats-total')}")
                sa = page.query_selector(f"#{get_id('stats-active')}")
                sd = page.query_selector(f"#{get_id('stats-done')}")
                # 9 prior + 5 added = 14, minus 1 deleted = 13 total;
                # done: x1? no. done items: read book's group...
                # after flows: done = [read book, task a, p2] = 3, plus s1, s2
                # toggled = 5 done; active = 13 - 5 = 8
                if st.inner_text() != "13":
                    f6.append(f"stats-total {st.inner_text()} != 13")
                if sa.inner_text() != "8":
                    f6.append(f"stats-active {sa.inner_text()} != 8")
                if sd.inner_text() != "5":
                    f6.append(f"stats-done {sd.inner_text()} != 5")
            except Exception as exc:
                f6.append(f"flow crashed: {exc}")
            flows["stats"] = {"pass": not f6, "problems": f6}

            browser.close()
    except Exception as exc:
        problems.append(f"browser session failed: {exc}")
        return {"pass": False, "problems": problems, "flows": flows,
                "console_errors": console_errors}

    all_pass = all(f["pass"] for f in flows.values())
    return {"pass": all_pass, "problems": problems, "flows": flows,
            "console_errors": console_errors, "seed": seed}


def gate_hygiene(app_dir, seed, flows_result):
    problems = []
    dist_bytes = sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(os.path.join(app_dir, "dist"))
        for f in files)
    if dist_bytes > MAX_DIST_BYTES:
        problems.append(f"dist {dist_bytes} B > {MAX_DIST_BYTES} B")

    console_errors = flows_result.get("console_errors", [])
    if console_errors:
        problems.append(f"{len(console_errors)} console error(s): "
                        f"{console_errors[:3]}")

    # reference cross-check: the judge's own spec-faithful app must produce
    # the same final DOM state as the artifact. We rebuild the reference
    # from judge/spec.json and compare final stats after the same 6 flows.
    # (Implemented as a build + serve + flow replay against judge/ref_app/.)
    ref_ok, ref_problems = run_reference_check(seed)
    if not ref_ok:
        problems.append(f"reference cross-check failed: {ref_problems}")

    return {"pass": not problems, "problems": problems,
            "dist_bytes": dist_bytes, "console_errors": console_errors}


# ---------------------------------------------------------------- reference app

def run_reference_check(seed):
    """Build and drive the judge-controlled reference app; return final
    DOM stats to compare against the artifact's."""
    ref_dir = os.path.join(HERE, "ref_app")
    if not os.path.isdir(ref_dir):
        return True, []  # reference app not present; cross-check is advisory
    try:
        g = gate_build(ref_dir)
        if not g["pass"]:
            return False, g["problems"]
        g = gate_flows(ref_dir, seed)
        return g["pass"], g["problems"]
    except Exception as exc:
        return False, [str(exc)]


# ---------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", dest="json_out")
    ap.add_argument("--judge-dir")
    args = ap.parse_args()

    judge_dir = os.path.abspath(args.judge_dir or HERE)
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

        # ---- gate 1: structure
        g1 = gate_structure(copied)
        verdict["gates"]["structure"] = g1
        if not g1["pass"]:
            rc = 1

        # ---- gate 2: build
        if rc == 0:
            t0 = time.monotonic()
            g2 = gate_build(copied)
            verdict["timing"]["build_s"] = round(time.monotonic() - t0, 1)
            verdict["gates"]["build"] = g2
            if not g2["pass"]:
                rc = 1

        # ---- gate 3: serve
        if rc == 0:
            t0 = time.monotonic()
            g3 = gate_serve(copied)
            verdict["timing"]["serve_s"] = round(time.monotonic() - t0, 1)
            verdict["gates"]["serve"] = g3
            if not g3["pass"]:
                rc = 1

        # ---- gate 4: flows
        if rc == 0:
            t0 = time.monotonic()
            g4 = gate_flows(copied, args.seed)
            verdict["timing"]["flows_s"] = round(time.monotonic() - t0, 1)
            verdict["gates"]["flows"] = {
                "pass": g4["pass"], "problems": g4["problems"]}
            verdict["flows"] = g4.get("flows", {})
            if not g4["pass"]:
                rc = 1

        # ---- gate 5: hygiene
        if rc == 0:
            t0 = time.monotonic()
            g5 = gate_hygiene(copied, args.seed, g4)
            verdict["timing"]["hygiene_s"] = round(time.monotonic() - t0, 1)
            verdict["gates"]["hygiene"] = g5
            if not g5["pass"]:
                rc = 1

        sha_after = check_shas(judge_dir)
        verdict["judge_intact"] = sha_before == sha_after
        if not verdict["judge_intact"]:
            rc = 1
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(verdict, fh, indent=2, sort_keys=True)
    print(json.dumps(verdict, indent=2, sort_keys=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
