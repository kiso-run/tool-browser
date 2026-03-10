# skill-browser

Headless WebKit browser automation skill for [kiso](https://github.com/kiso-run/core). Powered by [Playwright](https://playwright.dev/).

## Installation

```bash
kiso skill install browser
```

This clones the repo to `~/.kiso/skills/browser/`, then runs `deps.sh` which installs Python dependencies (`uv sync`), system libraries needed by WebKit (`playwright install-deps`), and the WebKit browser binary (`playwright install webkit`).

## How it works

1. The planner decides a browser interaction is needed and emits a `skill` task.
2. Kiso runs `run.py` as a subprocess, passing the action and arguments as JSON on stdin.
3. The skill launches a headless WebKit browser with a **persistent profile** stored in `workspace/.browser/profile/` — cookies, localStorage, and session data survive between calls within the same session.
4. The current page URL is tracked in `workspace/.browser/state.json` so the browser can restore context across invocations.

## Workflow

Always start with `navigate` (or pass `url` to a read action), then use the right action for the task.

```
navigate url="https://example.com"
  → "Navigated to: Example Domain\nURL: https://example.com"

text
  → "Page: Example Domain\nURL: https://example.com\n\nWelcome to Example Domain..."

links selector="main"
  → "Page: Example Domain\n...\n1. About — /about\n2. Contact — /contact"

forms
  → "Page: Example Domain\n...\nForm 1 (action: /search, method: GET):\n  - q (search): \"\"\n  - [Search] (button)"

snapshot
  → "Page: Example Domain\n...\n[1] <a href="/about">About</a>\n[2] <input type="search">\n[3] <button>Go</button>"

fill element="[2]" value="kiso"
click element="[3]"

screenshot
  → "Screenshot saved: /path/to/workspace/screenshot.png"
```

## Args reference

| Arg | Type | Required | Description |
|-----|------|----------|-------------|
| `action` | string | yes | One of: `navigate`, `text`, `links`, `forms`, `snapshot`, `click`, `fill`, `screenshot` |
| `url` | string | for `navigate`; optional for `text`, `links`, `forms` | URL to navigate to |
| `selector` | string | no | CSS selector to scope extraction (for `text`, `links`, `forms`) |
| `element` | string | for `click`, `fill` | Element reference `[N]` from snapshot, or a CSS selector |
| `value` | string | for `fill` | Text to type into the element |

## Actions

| Action | What it does |
|--------|-------------|
| `navigate` | Go to a URL. Returns page title and final URL. Skips reload if already on the same URL. Auto-dismisses cookie consent banners. |
| `text` | Extract visible text content, stripping nav/ads/boilerplate. |
| `links` | Extract a numbered list of page links with text and href. |
| `forms` | Extract structured form field information. |
| `snapshot` | List all interactive elements numbered `[1]`, `[2]`, … Warns if a CAPTCHA is detected. |
| `click` | Click element `[N]`. Returns updated snapshot. |
| `fill` | Type text into element `[N]`. Returns updated snapshot with the filled value echoed. |
| `screenshot` | Save a PNG to `workspace/screenshot.png`. |

## License

MIT
