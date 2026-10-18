# Changelog

Every released version, newest first. Generated from the release notes in
[`docs/releases/`](docs/releases/); edit the notes file for the version and
regenerate this file from it.

## v0.0.1 — What is in it

- **Claude Code and Codex plugin** (`plugins/sandbox`, version 0.0.1): the hosted sandbox MCP server plus the `sandbox` skill. Tools: `sandbox_create`, `sandbox_exec`, files read/write, public preview URL, `sandbox_kill`.
- **`sbx` CLI** (`cli/`, version 0.0.1): `create`, `exec`, `list`, `kill`; GPU leases (`sbx gpu create/exec/pause/resume/kill/templates/info`); GitHub Actions runners on disposable sandboxes (`sbx runners image/serve/migrate/stats/debug`).
- **Cookbook** (`cookbook/`): example recipes for CFD, FEA, SPICE, PLC, QEMU firmware, GPU kernels, path tracing, MuJoCo, CAD, CI runners and browser tasks, many with committed receipts, plus the demo tooling (video gate, slop gate, result manifest).


## v0.0.2 — What is new

- **`sbx templates`**: lists the CPU template aliases, one per line; `--json` prints the raw catalog, GPU entries included (#103).
- **`sbx cp`**: copies one file between your machine and a sandbox: `sbx cp LOCAL ID:REMOTE` uploads, `sbx cp ID:REMOTE LOCAL` downloads. Bytes are preserved (binary safe) and directories are rejected on either side. `--timeout` (default 600 s) is the deadline for each transfer attempt. A gateway restart is retried (#105).
- **`sbx gpu list`**: lists the GPU leases your key holds (id, template, state, VRAM, start time); `--json` prints the raw entries (#106).
- Plugin skill: GPU pause/suspend wording and the exec output limits now match the live service (#108).
- CLI tests no longer depend on an installed `sbx` (#107).


## v0.0.3 — What is new

- **`sbx list`**: prints `no sandboxes` (on stderr) when the key holds none. `--json` prints the raw list (`[]` when empty) (#114).
- **CLI errors**: an unknown template now prints the gateway's own message and exit code (`sbx: 404: template '...' not found`) instead of a `SandboxException:` prefix. The usage guidance also covers retrying a just-created sandbox and backing off on capacity refusals (#110).
- **Plugin `needs-auth`**: a session started without `SBX_API_KEY` can leave Claude Code with a cached auth entry. The plugin README now says to export the key first and gives a recovery snippet. The skill points to it (#112).
- **Plugin docs**: `sandbox_workspace` is now documented, so the README lists all 10 tools. The privacy link now goes to the live policy at https://sbx.agent-next.com/legal/privacy/, in the README and in the Codex manifest (#113).
- **`sbx gpu`**: the help text lists `list`. The pause wording now matches the GPU docs: a paused lease is spilled and bills 0, while a lease that cannot be spilled is frozen and bills the frozen time (#115).
