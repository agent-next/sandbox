#!/usr/bin/env python3
"""Host-side test: the rendered lease job must reference no undefined names.

run.py ships EXEC_SRC into the GPU lease with a handful of __PLACEHOLDER__
substitutions (see run.render_job). The exec sandbox runs the result with only
`report` injected, so any other unresolved name — e.g. a host-side constant
left behind by a refactor — detonates as a NameError *inside the lease* and
the API answers HTTP 409 (this exact failure shipped once; see RECEIPT).

This test renders the job through the same code path as run.py's main() and
then proves, twice over, that nothing is unbound:

  1. static: every name the job references is bound at module level, is a
     builtin, or is the injected `report` (stdlib `symtable` scope analysis);
  2. dynamic: the job is executed to completion with the outside world
     stubbed (a real demo tar is extracted into a temp dir; subprocess.run
     returns canned results), which drives every module-level statement —
     including inside step() — and would re-raise any NameError.

    python3 cookbook/sim-tuner/tools/test_rendered_job.py
"""
import builtins
import importlib.util
import os
import subprocess
import symtable
import sys
import tempfile
import types

TOOLS = os.path.dirname(os.path.abspath(__file__))
DEMO_DIR = os.path.dirname(TOOLS)
INJECTED = {"report"}   # names the lease exec framework provides


def load_run():
    spec = importlib.util.spec_from_file_location("run", os.path.join(DEMO_DIR, "run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bound_names(table):
    """Names bound in one symtable scope (assigned, imported, params, defs)."""
    out = set()
    for ident in table.get_identifiers():
        s = table.lookup(ident)
        if s.is_assigned() or s.is_imported() or s.is_parameter() or s.is_namespace():
            out.add(ident)
    return out


def unbound_names(src):
    """Every referenced name not bound in its scope chain, module or builtins."""
    root = symtable.symtable(src, "<job>", "exec")
    module_bound = bound_names(root)
    builtin = set(dir(builtins))
    problems = set()

    def walk(t):
        in_chain = bound_names(t)
        for ident in t.get_identifiers():
            s = t.lookup(ident)
            if not s.is_referenced():
                continue
            if ident in in_chain or ident in module_bound or ident in builtin or ident in INJECTED:
                continue
            problems.add(ident)
        for child in t.get_children():
            walk(child)

    walk(root)
    return problems


def exec_with_stubs(src, extract_to):
    """Run the job's module-level code end to end with the world stubbed."""
    real_run, real_expand = subprocess.run, os.path.expanduser
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    subprocess.run = fake_run
    os.path.expanduser = lambda p: extract_to if p.startswith("~") else p
    try:
        g = {"report": {}, "__name__": "__exec__"}
        exec(compile(src, "<job>", "exec"), g)
        return g, calls
    finally:
        subprocess.run = real_run
        os.path.expanduser = real_expand


def main():
    run = load_run()
    payload = run.pack_demo()
    src = run.render_job(payload, seed=7)

    compile(src, "<job>", "exec")   # syntax must be valid

    problems = unbound_names(src)
    if problems:
        print(f"FAIL: rendered job references unbound names: {sorted(problems)}",
              file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="sim-tuner-jobtest-") as tmp:
        g, calls = exec_with_stubs(src, tmp)
    stages = (g["report"].get("stages") or {})
    missing = {"stack-check", "selftest", "grade"} - set(stages)
    if missing:
        print(f"FAIL: job ran but stages missing: {sorted(missing)}", file=sys.stderr)
        return 1
    if len(calls) < 3:
        print(f"FAIL: expected >=3 subprocess calls, got {len(calls)}", file=sys.stderr)
        return 1
    print("ok: rendered job compiles, has no unbound names, and ran end to end")
    return 0


if __name__ == "__main__":
    sys.exit(main())
