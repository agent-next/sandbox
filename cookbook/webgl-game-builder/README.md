# webgl-game-builder

Prompt:

> Build a neon synthwave racing game with arrow keys, serve it from a sandbox, and give me the preview URL.

Run:

```bash
claude -p "Build a neon synthwave racing game with arrow keys, serve it from a sandbox, and give me the preview URL. Create it with a 30 minute lifetime." --allowedTools "mcp__plugin_sandbox_sandbox__*"
```

The agent creates a sandbox, writes the game, starts a web server on a port
and returns a public preview URL. Preview URLs are public: anyone with the
link can open it until the sandbox is killed. Kill the sandbox when you
are done (`sbx kill <id>`, or ask your agent to).
