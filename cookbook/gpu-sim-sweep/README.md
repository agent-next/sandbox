# gpu-sim-sweep

Prompt:

> Test my robot arm in 4,096 simulated worlds at once and report how many steps per second each setup reaches.

Run:

```bash
claude -p "Test my robot arm in 4,096 simulated worlds at once and report how many steps per second each setup reaches. Use a sandbox and kill it when done." --allowedTools "mcp__plugin_sandbox_sandbox__*"
```

Requirements: thousands of parallel worlds need a GPU sandbox. GPU sandboxes
are a separate lease that your key must have, and the plugin's tools create
CPU sandboxes only. Without GPU access the agent can still run a small CPU
sweep, but not the full 4,096.
