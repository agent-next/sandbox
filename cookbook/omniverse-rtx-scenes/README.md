# Omniverse RTX scenes

Flagship demo: an agent creates a GPU sandbox on agent-next, uploads NVIDIA official SimReady scenes, and renders them photoreal with RTX via ovrtx.

## Ask your agent

"Using the official NVIDIA SimReady assets and ovrtx on our GPU sandbox, render the warehouse+robot, crate collapse and robot-arm hero scenes, judge them, and return the gate verdicts."

## One-command run

```
python3 run.py
```

Needs `SBX_API_KEY` and the `sbx` CLI on PATH.

## Limits

GPU sandbox template "omniverse" must be live. CPU stage assembles the bundle; rendering runs on the GPU lease only.
