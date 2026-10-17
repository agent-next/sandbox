# browser-agent

Prompt:

> In a sandbox, drive a real browser to find the cheapest in-stock book rated four stars or more on books.toscrape.com, and tell me its title and price.

Run:

```bash
claude -p "In a sandbox, drive a real browser to find the cheapest in-stock book rated four stars or more on books.toscrape.com, and tell me its title and price. Kill the sandbox when done." --allowedTools "mcp__plugin_sandbox_sandbox__*"
```

The `agent-full` CPU template already includes Playwright and Chromium under
`/opt/ms-playwright`, with `PLAYWRIGHT_BROWSERS_PATH` set. Use its installed
Python package and `p.chromium.launch(headless=True)`; no `playwright install`
is needed. If you create a virtual environment, match the image's installed
Playwright version (`python -m pip show playwright`) so it uses the bundled
browser revision. Nothing runs on your machine.
