# browser-agent

Prompt:

> In a sandbox, drive a real browser to find the cheapest in-stock book rated four stars or more on books.toscrape.com, and tell me its title and price.

Run:

```bash
claude -p "In a sandbox, drive a real browser to find the cheapest in-stock book rated four stars or more on books.toscrape.com, and tell me its title and price. Kill the sandbox when done." --allowedTools "mcp__plugin_sandbox_sandbox__*"
```

The sandbox image already ships Chromium (and its headless shell) under
`/opt/ms-playwright`, with `PLAYWRIGHT_BROWSERS_PATH` exported and versioned
to match a current `pip install playwright`. So the agent should **not** run
`playwright install` — against the read-only, root-owned directory it hangs
silently (see #34). Install the pip package and launch straight away; the
first page loads in seconds. Nothing runs on your machine.
