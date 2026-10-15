#!/usr/bin/env python3
"""Generate the known-bad artifacts for the self-test from the good one.

Each mutant is a full copy of examples/good/app with exactly one scripted
edit. The edits are the realistic ways a generated app goes wrong; SPEC.md
names which gate kills each one. selftest.sh grades the good app (must
pass) and every mutant (each must fail at least one gate).

    python3 judge/mutants.py <out-dir>      # prints one mutant name per line

The good app ships no spec.json of its own: the judge copies judge/spec.json
into public/ before building, so the artifact must read the spec at runtime.
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "examples", "good", "app")

# (name, relative-file, must-exist-literal, replacement)
EDIT = [
    ("broken_delete",
     "src/App.jsx",
     "  function deleteTodo(id) {\n"
     "    setTodos(prev => prev.filter(t => t.id !== id))\n"
     "  }",
     "  function deleteTodo(id) {\n"
     "    setTodos(prev => prev.filter((_, j) => j !== 0))\n"
     "  }"),
    ("stats_wrong_span",
     "src/App.jsx",
     "        <div><dt>total</dt><dd id={ids['stats-total']}>{total}</dd></div>",
     "        <div><dt>total</dt><dd id={ids['stats-total']}>{done}</dd></div>"),
    ("no_persist",
     "src/App.jsx",
     "  useEffect(() => {\n"
     "    localStorage.setItem('todo-stats', JSON.stringify(todos))\n"
     "  }, [todos])",
     "  useEffect(() => {\n"
     "    void todos\n"
     "  }, [todos])"),
    ("console_error",
     "src/App.jsx",
     "  useEffect(() => {\n"
     "    loadSpec().then(setSpec).catch(console.error)\n"
     "  }, [])",
     "  useEffect(() => {\n"
     "    console.error('todo-stats: mount diagnostic')\n"
     "    loadSpec().then(setSpec).catch(console.error)\n"
     "  }, [])"),
    ("wrong_element_id",
     "src/App.jsx",
     "          <span id={ids['todo-text']}>{t.text}</span>",
     "          <span id={ids['todo-text'] + '-x'}>{t.text}</span>"),
    ("build_broken",
     "vite.config.js",
     "export default defineConfig({\n"
     "  plugins: [react()],\n"
     "})",
     "export default defineConfig({\n"
     "  plugins: [react()],\n"
     "  build: { rollupOptions: { input: 'src/does-not-exist.js' } },\n"
     "})"),
]


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: mutants.py <out-dir>")
    out_dir = sys.argv[1]
    names = []
    for name, relpath, old, new in EDIT:
        dst = os.path.join(out_dir, name)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(SRC, dst,
                        ignore=shutil.ignore_patterns("node_modules", "dist",
                                                      "__pycache__"))
        path = os.path.join(dst, relpath)
        with open(path) as fh:
            text = fh.read()
        if old not in text:
            raise SystemExit(f"mutant {name}: edit anchor not found in {relpath}")
        with open(path, "w") as fh:
            fh.write(text.replace(old, new, 1))
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
