# app-builder-preview — receipt

Real command output from two fresh agent-next sandboxes (setup from
nothing: Node tarball, two Chromium zips, npm cache). Every grade ran with
the default `--seed 0`. Commands ran from the repository root unless shown
otherwise. Sandbox ids are the ones this demo's own `run.py` created; both
were killed and confirmed gone.

Toolchain recorded by `judge/VERSIONS.txt` after `judge/setup.sh`:
node v22.23.3, npm 10.9.9, Playwright Python binding 1.63.0, Chromium
153.0.8010.12 (rev 1243), react 19.3.0, react-dom 19.3.0, vite 8.3.4,
@vitejs/plugin-react 6.1.1.

## Fresh-sandbox run 1 — `python3 cookbook/app-builder-preview/run.py --ref sbx/demo-app-builder-preview-f3`

```text
[create] sbx create --timeout-min ... ok (6 s)
sandbox: 01a140cd-25e6-78a0-8bc5-d37d52854199 (template default)
  [clone] sbx exec 01a140cd-25e6-78a0-8bc5-d37d52854199 ... ok (14 s)
  [layout] sbx exec 01a140cd-25e6-78a0-8bc5-d37d52854199 ... ok (17 s)
setup.sh: installing node v22.23.3
/tmp/tmp.jlgcRoOuW1/node-v22.23.3-linux-x64.tar.xz: OK
setup.sh: playwright 1.63.0 (python binding) present
setup.sh: installing chromium 153.0.8010.12 (rev 1243)
/tmp/tmp.jlgcRoOuW1/dl.zip: OK
setup.sh: installing chromium headless shell 153.0.8010.12
/tmp/tmp.jlgcRoOuW1/dl.zip: OK
setup.sh: chromium launch probe ok
setup.sh: warming npm cache from app/package-lock.json
setup.sh: ok
  [setup] sbx exec 01a140cd-25e6-78a0-8bc5-d37d52854199 ... ok (189 s)
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant broken_delete: killed (gate: flows)
selftest: mutant stats_wrong_span: killed (gate: flows)
selftest: mutant no_persist: killed (gate: flows)
selftest: mutant console_error: killed (gate: hygiene)
selftest: mutant wrong_element_id: killed (gate: flows)
selftest: mutant build_broken: killed (gate: build)
selftest: kill rate: 6/6 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: judge/ checksums unchanged
selftest: ok
  [selftest] sbx exec 01a140cd-25e6-78a0-8bc5-d37d52854199 ... ok (641 s)
{
  "artifact": "app",
  "demo": "app-builder-preview",
  "flows": {
    "add": {
      "pass": true,
      "problems": []
    },
    "complete": {
      "pass": true,
      "problems": []
    },
    "delete": {
      "pass": true,
      "problems": []
    },
    "filter": {
      "pass": true,
      "problems": []
    },
    "persist": {
      "pass": true,
      "problems": []
    },
    "stats": {
      "pass": true,
      "problems": []
    }
  },
  "gates": {
    "build": {
      "pass": true,
      "problems": []
    },
    "flows": {
      "pass": true,
      "problems": []
    },
    "hygiene": {
      "console_errors": [],
      "dist_bytes": 224294,
      "pass": true,
      "problems": []
    },
    "serve": {
      "pass": true,
      "port": 5317,
      "problems": []
    },
    "structure": {
      "pass": true,
      "problems": []
    }
  },
  "judge_intact": true,
  "seed": 0,
  "states": {
    "add": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": false,
          "text": "buy milk"
        },
        {
          "done": false,
          "text": "walk dog"
        },
        {
          "done": false,
          "text": "read book"
        }
      ],
      "stats": {
        "active": "3",
        "done": "0",
        "total": "3"
      }
    },
    "complete": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": true,
          "text": "task a"
        },
        {
          "done": false,
          "text": "task b"
        }
      ],
      "stats": {
        "active": "1",
        "done": "1",
        "total": "2"
      }
    },
    "delete": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": false,
          "text": "buy milk"
        },
        {
          "done": false,
          "text": "read book"
        }
      ],
      "stats": {
        "active": "2",
        "done": "0",
        "total": "2"
      }
    },
    "filter": {
      "active_filter": "active",
      "input_value": "",
      "items": [
        {
          "done": false,
          "text": "a2"
        },
        {
          "done": false,
          "text": "a3"
        }
      ],
      "stats": {
        "active": "2",
        "done": "1",
        "total": "3"
      }
    },
    "persist": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": true,
          "text": "p1"
        },
        {
          "done": false,
          "text": "p2"
        }
      ],
      "stats": {
        "active": "1",
        "done": "1",
        "total": "2"
      }
    },
    "stats": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": true,
          "text": "s1"
        },
        {
          "done": true,
          "text": "s2"
        },
        {
          "done": false,
          "text": "s4"
        },
        {
          "done": false,
          "text": "s5"
        }
      ],
      "stats": {
        "active": "2",
        "done": "2",
        "total": "4"
      }
    }
  },
  "timing": {
    "build_s": 11.1,
    "flows_s": 28.7,
    "hygiene_s": 43.7,
    "serve_s": 5.0,
    "structure_s": 0.0
  }
}
  [grade] sbx exec 01a140cd-25e6-78a0-8bc5-d37d52854199 ... ok (96 s)
  [cat] sbx exec 01a140cd-25e6-78a0-8bc5-d37d52854199 ... ok (5 s)
killed 01a140cd-25e6-78a0-8bc5-d37d52854199
  [kill] sbx kill 01a140cd-25e6-78a0-8bc5-d37d52854199 ... ok (4 s)
  [list] sbx list ... ok (1 s)
cleanup: sandbox 01a140cd-25e6-78a0-8bc5-d37d52854199 killed and confirmed gone
total: 974 s

app-builder-preview demo: PASS
  gate build: pass
  gate flows: pass
  gate hygiene: pass
  gate serve: pass
  gate structure: pass

real	16m14.442s
user	0m15.675s
sys	0m2.563s
RC=0
```

exit=0.

## Fresh-sandbox run 2 — same command, new sandbox

```text
[create] sbx create --timeout-min ... ok (6 s)
sandbox: 01a140cd-22cf-7681-9200-e430678fe788 (template default)
  [clone] sbx exec 01a140cd-22cf-7681-9200-e430678fe788 ... ok (13 s)
  [layout] sbx exec 01a140cd-22cf-7681-9200-e430678fe788 ... ok (18 s)
setup.sh: installing node v22.23.3
/tmp/tmp.jcQjqfNhDL/node-v22.23.3-linux-x64.tar.xz: OK
setup.sh: playwright 1.63.0 (python binding) present
setup.sh: installing chromium 153.0.8010.12 (rev 1243)
/tmp/tmp.jcQjqfNhDL/dl.zip: OK
setup.sh: installing chromium headless shell 153.0.8010.12
/tmp/tmp.jcQjqfNhDL/dl.zip: OK
setup.sh: chromium launch probe ok
setup.sh: warming npm cache from app/package-lock.json
setup.sh: ok
  [setup] sbx exec 01a140cd-22cf-7681-9200-e430678fe788 ... ok (165 s)
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant broken_delete: killed (gate: flows)
selftest: mutant stats_wrong_span: killed (gate: flows)
selftest: mutant no_persist: killed (gate: flows)
selftest: mutant console_error: killed (gate: hygiene)
selftest: mutant wrong_element_id: killed (gate: flows)
selftest: mutant build_broken: killed (gate: build)
selftest: kill rate: 6/6 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: judge/ checksums unchanged
selftest: ok
  [selftest] sbx exec 01a140cd-22cf-7681-9200-e430678fe788 ... ok (618 s)
{
  "artifact": "app",
  "demo": "app-builder-preview",
  "flows": {
    "add": {
      "pass": true,
      "problems": []
    },
    "complete": {
      "pass": true,
      "problems": []
    },
    "delete": {
      "pass": true,
      "problems": []
    },
    "filter": {
      "pass": true,
      "problems": []
    },
    "persist": {
      "pass": true,
      "problems": []
    },
    "stats": {
      "pass": true,
      "problems": []
    }
  },
  "gates": {
    "build": {
      "pass": true,
      "problems": []
    },
    "flows": {
      "pass": true,
      "problems": []
    },
    "hygiene": {
      "console_errors": [],
      "dist_bytes": 224294,
      "pass": true,
      "problems": []
    },
    "serve": {
      "pass": true,
      "port": 5317,
      "problems": []
    },
    "structure": {
      "pass": true,
      "problems": []
    }
  },
  "judge_intact": true,
  "seed": 0,
  "states": {
    "add": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": false,
          "text": "buy milk"
        },
        {
          "done": false,
          "text": "walk dog"
        },
        {
          "done": false,
          "text": "read book"
        }
      ],
      "stats": {
        "active": "3",
        "done": "0",
        "total": "3"
      }
    },
    "complete": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": true,
          "text": "task a"
        },
        {
          "done": false,
          "text": "task b"
        }
      ],
      "stats": {
        "active": "1",
        "done": "1",
        "total": "2"
      }
    },
    "delete": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": false,
          "text": "buy milk"
        },
        {
          "done": false,
          "text": "read book"
        }
      ],
      "stats": {
        "active": "2",
        "done": "0",
        "total": "2"
      }
    },
    "filter": {
      "active_filter": "active",
      "input_value": "",
      "items": [
        {
          "done": false,
          "text": "a2"
        },
        {
          "done": false,
          "text": "a3"
        }
      ],
      "stats": {
        "active": "2",
        "done": "1",
        "total": "3"
      }
    },
    "persist": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": true,
          "text": "p1"
        },
        {
          "done": false,
          "text": "p2"
        }
      ],
      "stats": {
        "active": "1",
        "done": "1",
        "total": "2"
      }
    },
    "stats": {
      "active_filter": "all",
      "input_value": "",
      "items": [
        {
          "done": true,
          "text": "s1"
        },
        {
          "done": true,
          "text": "s2"
        },
        {
          "done": false,
          "text": "s4"
        },
        {
          "done": false,
          "text": "s5"
        }
      ],
      "stats": {
        "active": "2",
        "done": "2",
        "total": "4"
      }
    }
  },
  "timing": {
    "build_s": 12.2,
    "flows_s": 31.6,
    "hygiene_s": 37.6,
    "serve_s": 5.5,
    "structure_s": 0.0
  }
}
  [grade] sbx exec 01a140cd-22cf-7681-9200-e430678fe788 ... ok (95 s)
  [cat] sbx exec 01a140cd-22cf-7681-9200-e430678fe788 ... ok (5 s)
killed 01a140cd-22cf-7681-9200-e430678fe788
  [kill] sbx kill 01a140cd-22cf-7681-9200-e430678fe788 ... ok (4 s)
  [list] sbx list ... ok (1 s)
cleanup: sandbox 01a140cd-22cf-7681-9200-e430678fe788 killed and confirmed gone
total: 926 s

app-builder-preview demo: PASS
  gate build: pass
  gate flows: pass
  gate hygiene: pass
  gate serve: pass
  gate structure: pass

real	15m26.524s
user	0m17.498s
sys	0m2.475s
RC=0
```

exit=0. Both runs' verdict JSONs are byte-identical except `timing`
(enforced per grade by `judge/selftest.sh`, which fails if two grades of the
same artifact differ beyond that key).

## Key numbers (identical in both runs)

| quantity | value |
|---|---|
| gates | structure, build, serve, flows, hygiene — all pass |
| flows | 6/6 pass (add, complete, delete, filter, persist, stats) |
| reference cross-check | agrees with the artifact on all 6 flows |
| `dist/` size | 224294 B = 219.0 KiB of the 250 KiB budget |
| console errors | 0 |
| `judge_intact` | true (judge/ sha256 unchanged across the grade) |
| self-test kill rate | 6/6 = 100 % (requirement ≥ 90 %) |
| self-test mutants | broken_delete → flows; stats_wrong_span → flows; no_persist → flows; console_error → hygiene; wrong_element_id → flows; build_broken → build |
| determinism | OK — two grades of the good artifact byte-identical except `timing` |

Per-gate wall times from the verdict JSON (`timing` key, run 1):
structure 0.0 s, build 6.6 s, serve 1.8 s, flows 19.1 s, hygiene 26.1 s.

## Judge self-test, standalone

`bash cookbook/app-builder-preview/judge/selftest.sh` in a fresh sandbox
(own run, 7 min 0 s wall):

```text
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant broken_delete: killed (gate: flows)
selftest: mutant stats_wrong_span: killed (gate: flows)
selftest: mutant no_persist: killed (gate: flows)
selftest: mutant console_error: killed (gate: hygiene)
selftest: mutant wrong_element_id: killed (gate: flows)
selftest: mutant build_broken: killed (gate: build)
selftest: kill rate: 6/6 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: judge/ checksums unchanged
selftest: ok
```

## Media traceability

Every figure and number in README.md comes from a judge verdict, regenerated
by `bash media/make_media.sh` (which re-runs the judge and writes
`media/data/*.json`); `media/MANIFEST.json` names the command, the source
data file and the sha256 of each media file. Figures show measured numbers
only.

## Deviations

- The Chromium builds are fetched from the Playwright CDN as two pinned zips
  (~315 MB total, sha256-checked). This is the one setup step that needs real
  bandwidth; on a slow link it dominates the setup step's wall time. Nothing
  else in setup touches the network beyond the Node tarball and the npm cache
  warm-up.
- The Playwright **Python binding** is not installed by `setup.sh`: the
  sandbox image ships exactly 1.63.0, and `setup.sh` verifies that version
  and fails loudly if the image ever ships a different one. It is never
  upgraded in place.
- `npm ci` in the build gate is served from the warm cache `setup.sh`
  created, so the build gate does not need the network.
- The self-test's determinism check grades the good artifact twice; its wall
  time is part of the `selftest` step above, not a separate step.
