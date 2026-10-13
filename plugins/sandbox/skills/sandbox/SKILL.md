---
name: sandbox
description: Run code and commands in an agent-next cloud sandbox. Use for long-running jobs, untrusted code, parallel work, anything needing a public preview URL, or heavy dependencies that should not install on the user's machine.
---

# Use the agent-next cloud sandbox

This plugin connects to the agent-next sandbox MCP server, which creates
remote, disposable Linux sandboxes (E2B-compatible). Work happens in the
cloud, not on the user's machine.

## When to use it

- **Long-running jobs** — builds, test suites, data processing that would
  block or time out locally.
- **Untrusted or risky code** — generated scripts, third-party packages,
  anything you would not run on the user's machine directly.
- **Parallel work** — create several sandboxes to run independent tasks at
  once instead of serializing on one machine.
- **Public preview links** — expose a port and share
  `https://<port>-<sandbox-id>.sbx.agent-next.com` so the user can see a
  running web app, notebook or service.
- **Heavy dependencies** — compilers, GPU stacks, large toolchains that are
  impractical to install locally.

## Normal flow

1. `sandbox_create` — pick a template; note the returned sandbox id.
2. `sandbox_exec` to run commands, `sandbox_files_write` /
   `sandbox_files_read` to move code and results in and out.
3. `sandbox_preview_url` (expose a port) when the user should open a web
   app or service — return the URL to the user.
4. `sandbox_kill` — always destroy the sandbox when the work is done.

## Rules

- **Always kill sandboxes after use.** A forgotten sandbox holds a quota
  slot and consumes running credit while it is active. Kill every sandbox you create once it is no
  longer needed, and tell the user if a kill fails. Killing one that is
  already gone answers `sandbox not found`: treat that as gone.
- **CPU `timeout_min` is an idle keep-alive.** After that many idle minutes
  (default 5, max 1440), the sandbox auto-pauses, preserving files, memory
  and running processes. Activity restarts the clock; CPU usage alone does
  not count. Pausing never fires before the 300 s idle floor and may land a
  reaper sweep late. The next exec or files call auto-resumes an MCP-created
  CPU sandbox. A full paused quota keeps it running and billing until a
  paused slot is available. Continuously paused sandboxes expire after
  7 days, so copy durable results out. The separate `sbx` CLI uses the SDK's
  kill-on-timeout mode; its `--timeout-min` does not promise MCP auto-pause.
- **Concurrency is per key.** The actual limit for the key in use is
  `limits.max_concurrent` in
  `GET /v0/account` (and `quota_running` in `GET /v0/usage`). A create over
  the limit fails with `quota exceeded, retry in 5s`: kill finished
  sandboxes or wait, do not retry in a tight loop.
- **Check the exit code.** `sandbox_exec` returns `status: exited` with
  `exit_code` (0 included) when the command ends within `wait_s` (default
  and max 45). If it returns `status: running`, `exit_code` is null: call
  `sandbox_exec_output` with the same `job_id` until the status is
  `exited`, and read the exit code there.
- **Redirect the output of background processes.** Write
  `nohup server > /tmp/server.log 2>&1 &`, never a bare `server &`: a
  child holding the stdout pipe keeps the call `running` until it exits.
  Read the log with `sandbox_files_read`.
- **Memory limits.** The default template has 2 vCPU, about 3.8 GiB RAM, no
  swap and about 50 GiB disk. There is no memory cgroup: a process past
  roughly 3.5 GiB is OOM-killed (exit 137) and its buffered stdout is lost,
  so flush output to a file. Larger sizes are template-level classes
  (`small` 2 vCPU / 8 GiB, `standard` 4 / 16, `large` 8 / 32 where
  enabled), not an argument of `sandbox_create`.
- **GPU leases are available through MCP.** Call `sandbox_templates` for
  the live catalog, then `sandbox_create` with a GPU template (`gpu`,
  `gpu-lease-v06`, `mujoco` or `kernel`) and `vram_gb` (default 4, range
  0.5–32). GPU sandboxes support `sandbox_exec` and `sandbox_kill`, consume
  separate GPU credit, and have a hard VRAM cap. They cannot pause, expose
  preview URLs, or use the files tools. `timeout_min` is validated but is
  not applied (`timeout_min_applied: false`): kill them explicitly when
  done. Their maximum lease age appears as `end_at` in `sandboxes_list`.
- **Preview URLs are public by default.** Anyone with
  `https://<port>-<sandbox-id>.sbx.agent-next.com` can reach the port, with
  no sign-in, and it answers 502 after the sandbox is killed. Do not serve
  secrets or admin tools on a preview port. To restrict it, create the
  sandbox over the REST API with `network.allowPublicTraffic=false` (or
  register the port `public:false`); `sandbox_preview_url` then returns a
  `token` to append as `?_gw_token=<token>`.
- Outbound SMTP (25, 465, 587) is blocked and networking is IPv4 only.
- Keep secrets out of file contents and command lines where possible; if
  a job needs credentials, pass them as environment variables and do not
  echo them back.
- Command output and tool results are truncated (256 KiB per stream, and
  100000 bytes per poll); page through files with `sandbox_files_read`
  instead of catting large outputs.
