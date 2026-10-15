# gpu-sim-sweep

Prompt:

> Time a MuJoCo robot-arm simulation at 1, 16 and 256 parallel worlds in a sandbox and report steps per second for each.

Run:

```bash
claude -p "Time a MuJoCo robot-arm simulation at 1, 16 and 256 parallel worlds in a sandbox and report steps per second for each. Kill the sandbox when done." --allowedTools "mcp__plugin_sandbox_sandbox__*"
```

This prompt targets a CPU sandbox. For GPU work, first ask the agent to call
`sandbox_templates` for the live catalog, then create a GPU template with
`sandbox_create` and a `vram_gb` slice. GPU leases support exec and kill,
and `sbx gpu pause`/`resume` between jobs; they never auto-pause on idle or
expose preview URLs, so always kill them when done.
The reviewed demo video swept thousands of worlds on a GPU sandbox; this
CPU recipe does not establish that scale or performance.
