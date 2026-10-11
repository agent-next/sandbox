# browser-agent

Prompt:

> In a sandbox, drive a real browser to find the cheapest in-stock book rated four stars or more on books.toscrape.com, and tell me its title and price.

Run:

```bash
claude -p "In a sandbox, drive a real browser to find the cheapest in-stock book rated four stars or more on books.toscrape.com, and tell me its title and price. Kill the sandbox when done." --allowedTools "mcp__plugin_sandbox_sandbox__*"
```

The agent installs a browser inside the sandbox, so the first run spends a
few minutes on setup. Nothing runs on your machine.
