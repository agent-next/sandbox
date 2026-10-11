# gpu-sim-sweep

Prompt:

> Time a MuJoCo robot-arm simulation at 1, 16 and 256 parallel worlds in a sandbox and report steps per second for each.

Run:

```bash
claude -p "Time a MuJoCo robot-arm simulation at 1, 16 and 256 parallel worlds in a sandbox and report steps per second for each. Kill the sandbox when done." --allowedTools "mcp__plugin_sandbox_sandbox__*"
```

This runs on a CPU sandbox, which is what the plugin's tools create. The
reviewed demo video swept thousands of worlds on a GPU sandbox; GPU sandboxes
are a separate lease that is not created through these tools, so that scale is
not reproducible from this entry.
