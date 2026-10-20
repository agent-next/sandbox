# Pitch — layerfs-race

## Hero frame (0-2 s)

The finished result fills the frame: the judge's verdict grid — 8 agent
branches in one LayerFS Store, `main` re-tested green at 1238/1238, every
losing branch red — over a live terminal capture of the race.

## Claim

Eight agents race to fix an injected express bug on copy-on-write LayerFS
branches in one disposable sandbox; the Store holds 0.30× the source tree,
`branch.fork` medians 0.0006 s, and a judge that re-runs the suite itself
proves the published `main` green — killing 10/10 mutants.

## Storyboard

Slot table: `media/STORYBOARD.md`. Arc in one line: verdict grid ->
prompt/bug -> 8 sandboxes racing at Nx speed -> merge conflict refused ->
judge PASS + kill matrix -> `python3 run.py` end card.
