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
  slot until its TTL ends. Kill every sandbox you create once it is no
  longer needed, and tell the user if a kill fails. Killing one that is
  already gone answers `sandbox not found`: treat that as gone.
- **`timeout_min` is a hard TTL, not an idle timer.** The sandbox is killed
  that many minutes after creation (default 5, max 1440) whatever its
  activity, and its files go with it. Ask for the time the job needs, and
  copy results out before then. Separately, a sandbox idle for 300 s is
  paused and resumes on the next call.
- **Concurrency is per key.** The free tier runs 2 sandboxes at once; the
  real number for the key in use is `limits.max_concurrent` in
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
  enabled), not an argument of `sandbox_create`. GPU sandboxes are a
  separate lease with a hard VRAM slice (`accel.vram_gb`, 0.5 to 32 GiB),
  not available through these tools; CUDA allocations past the slice fail
  with a normal out-of-memory error, while graphics memory past it kills
  the job.
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
