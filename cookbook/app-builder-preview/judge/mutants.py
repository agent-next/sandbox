#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Each mutant is a full copy of the good app (examples/good/app) with exactly
one scripted edit; the self-test expects every mutant to fail at least one
gate (SPEC.md). The edits are the realistic ways a generated app goes wrong:
a delete handler that removes the wrong item, a route that is never matched
(the app renders nothing), stats that count done items twice, persistence
removed, a console.error on mount, a renamed element id, and a build that
cannot produce dist/.
"""

import os
import shutil
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "examples", "good", "app")

# (name, relative-file, must-exist-literal, replacement)
EDIT = [
    ("broken_delete",
     "src/App.jsx",
     "  function deleteTodo(id) {\n"
     "    setTodos(prev => prev.filter(t => t.id !== id))\n"
     "  }",
     "  function deleteTodo(id) {\n"
     "    setTodos(prev => {\n"
     "      const i = prev.findIndex(t => t.id === id)\n"
     "      return prev.filter((_, j) => j === i)\n"
     "    })\n"
     "  }"),
    ("missing_route",
     "src/App.jsx",
     "  if (!spec) return <div id=\"root-loading\">loading…</div>",
     "  if (!spec) return <div id=\"root-loading\">loading…</div>\n"
     "  if (spec.routes.indexOf(window.location.pathname + 'x') < 0) return null"),
    ("stats_off_by_one",
     "src/App.jsx",
     "  const total = todos.length",
     "  const total = todos.length + todos.filter(t => t.done).length"),
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
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    names = []
    for name, relpath, old, new in EDIT:
        dst = os.path.join(out_dir, name)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(SRC, dst,
                        ignore=shutil.ignore_patterns("node_modules", "dist",
                                                      "__pycache__"))
        path = os.path.join(dst, relpath)
        with open(path) as fh:
            mutant = fh.read()
        if old not in mutant:
            raise SystemExit(f"mutant {name}: edit anchor not found in {relpath}")
        mutant = mutant.replace(old, new, 1)
        if mutant == old and old in mutant:
            pass
        with open(path, "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
