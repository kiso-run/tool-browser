# skill-browser

Headless WebKit browser automation skill for [kiso](https://github.com/kiso-run/core). Powered by [Playwright](https://playwright.dev/).

## Installation

```bash
kiso skill install browser
```

This clones the repo to `~/.kiso/skills/browser/`, runs `uv sync`, then `deps.sh` which downloads the WebKit browser binary (~50 MB).

## How it works

1. The planner decides a browser interaction is needed and emits a `skill` task.
2. Kiso runs `run.py` as a subprocess, passing the action and arguments as JSON on stdin.
3. The skill launches a headless WebKit browser with a **persistent profile** stored in `workspace/.browser/profile/` — cookies, localStorage, and session data survive between calls within the same session.
4. The current page URL is tracked in `workspace/.browser/state.json` so the browser can restore context across invocations.

## Workflow

Always start with `navigate`, then use `snapshot` to see the numbered interactive elements, then `click` or `fill` by element number.

```
navigate url="https://example.com"
  → "Navigated to: Example Domain\nURL: https://example.com"

snapshot
  → "Page: Example Domain\nURL: https://example.com\n\n[1] <a href="/about">About</a>\n[2] <input type="search" placeholder="Search">\n[3] <button>Go</button>"

fill element="[2]" value="kiso"
click element="[3]"

screenshot
  → "Screenshot saved: /path/to/workspace/screenshot.png"
```

## Args reference

| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `action` | string | yes | One of: `navigate`, `snapshot`, `click`, `fill`, `screenshot` |
| `url` | string | for `navigate` | URL to navigate to |
| `element` | string | for `click`, `fill` | Element reference `[N]` from snapshot, or a CSS selector |
| `value` | string | for `fill` | Text to type into the element |

## Actions

| Action | What it does |
|--------|-------------|
| `navigate` | Go to a URL. Returns page title and final URL. |
| `snapshot` | List all interactive elements numbered `[1]`, `[2]`, … |
| `click` | Click element `[N]`. Returns updated snapshot. |
| `fill` | Type text into element `[N]`. Returns updated snapshot. |
| `screenshot` | Save a PNG to `workspace/screenshot.png`. |

## System dependencies

On Debian/Ubuntu, WebKit may need additional libraries. If `deps.sh` installs successfully but the browser fails to launch, run:

```bash
~/.kiso/skills/browser/.venv/bin/playwright install --with-deps webkit
```

## License

MIT
