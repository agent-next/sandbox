# sandbox plugin

Connects Claude Code and Codex to the agent-next cloud sandbox: remote,
disposable Linux environments exposed over one MCP server. Create a sandbox,
run commands, read and write files, expose a port as a public preview URL,
then kill it. Nothing executes on your machine.

Contents:

- `.claude-plugin/plugin.json`, `.mcp.json`: Claude Code manifest and MCP
  config (header `X-API-Key: ${SBX_API_KEY}`).
- `.codex-plugin/plugin.json`, `codex.mcp.json`: Codex manifest and MCP
  config (`SBX_API_KEY` sent as a bearer token).
- `skills/sandbox/SKILL.md`: when to use the sandbox and the rules to follow.

Tools: `sandboxes_list`, `sandbox_templates`, `sandbox_create`,
`sandbox_exec`, `sandbox_exec_output`, `sandbox_files_read`,
`sandbox_files_write`, `sandbox_preview_url`, `sandbox_kill`. Server URL:
`https://api.sbx.agent-next.com/mcp/v1`.

## API key

Create a key at <https://sbx.agent-next.com/console> and export it as
`SBX_API_KEY` in the environment that launches Claude Code or Codex. For
Claude Code, if the variable is unset the literal `${SBX_API_KEY}` is sent and
authentication fails.

## Privacy

Sandbox contents, command output and retained files are governed by the
agent-next privacy policy: <https://agent-next.com/privacy>.
