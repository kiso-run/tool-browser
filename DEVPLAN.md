# tool-browser — Development Plan

## Overview

Headless WebKit browser automation tool for kiso. Allows the planner to
navigate pages, read content, extract links, inspect forms, interact with
elements, and take screenshots — all via a subprocess that communicates over
JSON on stdin/stdout.

**Current status:** v0.2.0 — all core actions plus UX quality fixes (navigate
dedup, fill echo, cookie consent auto-dismiss, CAPTCHA detection). Tested with
unit-level mocks (133 tests). No integration tests against a real browser yet.

## Architecture

```
tool-browser/
├── kiso.toml          # manifest: args schema, deps, usage guide
├── pyproject.toml     # Python deps (playwright >=1.44, pytest)
├── run.py             # entry point + all action logic (~390 LOC)
├── deps.sh            # system libs + WebKit binary installer
├── tests/
│   ├── conftest.py    # shared fixtures and mock builders
│   ├── test_dispatch.py      # dispatch(), main() error paths
│   └── test_read_actions.py  # text/links/forms extraction + _ensure_page
├── README.md
└── LICENSE
```

**Key design decisions:**

- Single-file `run.py` — keeps the tool self-contained; no internal packages.
- Persistent browser profile (`workspace/.browser/profile/`) — cookies and
  session survive between calls within the same kiso session.
- State file (`workspace/.browser/state.json`) — tracks current URL so the
  browser can restore context across invocations.
- Noise stripping in `extract_text` — removes nav, header, footer, cookie
  banners, and ads before extracting body text; prefers `<main>`/`<article>`
  containers.

## Capabilities

| Action     | Description                                        | Status |
|------------|----------------------------------------------------|--------|
| navigate   | Go to a URL, return title + final URL              | done   |
| text       | Extract visible text, strip noise, scope by CSS    | done   |
| links      | Numbered list of links with dedup and filtering    | done   |
| forms      | Structured form field info (inputs, selects, buttons) | done |
| snapshot   | Numbered list of interactive elements `[1]`, `[2]` | done  |
| click      | Click element by `[N]` ref or CSS selector         | done   |
| fill       | Type text into element by `[N]` ref or CSS selector | done  |
| screenshot | Save full-page PNG to workspace                    | done   |

## Milestones

### M1 — Initial tool scaffold ✅

**Problem:** kiso had no browser automation capability.

**Change:**
1. Created `run.py` with subprocess contract (JSON stdin → stdout/stderr)
2. Implemented all 8 actions: navigate, text, links, forms, snapshot, click,
   fill, screenshot
3. Added persistent browser profile and state file for session continuity
4. Defined `kiso.toml` manifest with args schema and usage guide
5. Set up `deps.sh` for system libs + WebKit binary installation

### M2 — Test suite ✅

**Problem:** No automated tests; correctness relied on manual verification.

**Change:**
1. Added `conftest.py` with mock builders (`make_mock_page`,
   `make_mock_element`, `make_input`, `run_tool`)
2. `test_dispatch.py` — covers dispatch routing, navigate, snapshot, click,
   fill, screenshot, text/links/forms delegation, unknown-action error,
   missing-playwright error path
3. `test_read_actions.py` — covers `_ensure_page` (url vs state, redirects),
   `extract_text` (body fallback, content containers, noise stripping,
   selector scoping), `extract_links` (filtering, dedup, scoping),
   `extract_forms` (inputs, selects, textareas, buttons, method default,
   scoping)

### M3 — Read actions: inline URL and selector support ✅

**Problem:** `text`, `links`, and `forms` originally required a prior
`navigate` call. Users had to make two calls to read a new page.

**Change:**
1. Added `_ensure_page` helper — navigates from explicit `url` arg or saved
   state, then saves state
2. All three read actions now accept optional `url` (navigate + extract in one
   step) and `selector` (scope extraction to a CSS subtree)
3. Tests cover both paths (inline URL, state URL) and state persistence after
   redirect

### M4 — Navigate dedup (skip if already on URL) ✅

**Problem:** Planner re-navigates to URLs already loaded. Browser state
persists between calls, so reloading the same page wastes time.

**File:** `run.py` — `do_navigate()`

**Change:**
1. Before `page.goto()`, check if current URL matches target via saved state:
   ```python
   current = load_state(state_file)
   if current and _urls_match(current, url):
       page.goto(current, timeout=30000)
       return f"Already on {url}.\n{snapshot(page)}"
   ```
2. Add `_urls_match(a, b)` helper — normalize trailing slashes, ignore
   fragment:
   ```python
   def _urls_match(a: str, b: str) -> bool:
       from urllib.parse import urlparse
       pa, pb = urlparse(a), urlparse(b)
       return (pa.scheme == pb.scheme and pa.netloc == pb.netloc
               and pa.path.rstrip("/") == pb.path.rstrip("/")
               and pa.query == pb.query)
   ```

**Test:** Navigate to same URL twice — second call returns "Already on..."
without calling `page.goto` a second time.

---

### M5 — Fill action echoes filled value ✅

**Problem:** `do_fill()` returns `Filled '{ref}'. URL: ...` without echoing
the value. Reviewer can't verify the fill succeeded.

**File:** `run.py` — `do_fill()`

**Change:**
1. Change return message to include the value:
   ```python
   return f"Filled {ref!r} with: {value!r}. URL: {page.url}\n\n{snapshot(page)}"
   ```

**Test:** Fill a field — output includes `with: 'the_value'`.

---

### M6 — Cookie consent auto-dismiss ✅

**Problem:** Cookie banners obscure page content and block interactions.

**File:** `run.py` — add `_dismiss_cookie_consent()`

**Change:**
1. Add helper that tries common cookie consent selectors:
   ```python
   _COOKIE_ACCEPT_SELECTORS = [
       "button:has-text('Accept')", "button:has-text('Accetta')",
       "button:has-text('Accept all')", "button:has-text('Accetta tutti')",
       "[id*='cookie'] button:has-text('OK')",
       ".cookie-banner button.accept", "#onetrust-accept-btn-handler",
   ]

   def _dismiss_cookie_consent(page):
       for sel in _COOKIE_ACCEPT_SELECTORS:
           try:
               btn = page.locator(sel).first
               if btn.is_visible(timeout=500):
                   btn.click(timeout=2000)
                   page.wait_for_timeout(500)
                   return True
           except Exception:
               continue
       return False
   ```
2. Call `_dismiss_cookie_consent(page)` at the end of `do_navigate()`, after
   page load.

**Test:** Navigate to a page with a cookie banner — banner dismissed, snapshot
shows page content.

---

### M7 — CAPTCHA detection in snapshot ✅

**Problem:** Forms with CAPTCHA elements cause fill/submit failures. Kiso
should detect and warn early.

**File:** `run.py` — `do_snapshot()`

**Change:**
1. After building the snapshot elements list, scan for CAPTCHA indicators:
   ```python
   _CAPTCHA_MARKERS = [
       "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']",
       "iframe[src*='turnstile']", ".g-recaptcha", ".h-captcha",
       "[data-sitekey]",
   ]

   def _detect_captcha(page) -> bool:
       for sel in _CAPTCHA_MARKERS:
           if page.query_selector(sel):
               return True
       return False
   ```
2. If CAPTCHA detected, prepend warning to snapshot output:
   ```python
   if _detect_captcha(page):
       lines.insert(0, "CAPTCHA detected on this page. "
                       "Form submission may require human verification.")
   ```

**Test:** Load a page with reCAPTCHA iframe — snapshot output starts with
CAPTCHA warning.

## Milestone Checklist

- [x] **M1** — Initial tool scaffold
- [x] **M2** — Test suite
- [x] **M3** — Read actions: inline URL and selector support
- [x] **M4** — Navigate dedup (skip if already on URL)
- [x] **M5** — Fill action echoes filled value
- [x] **M6** — Cookie consent auto-dismiss
- [x] **M7** — CAPTCHA detection in snapshot
- [x] **M8** — Usage guide rewrite + operation timeouts
- [x] **M9** — Complete test coverage

### M8 — Usage guide rewrite + operation timeouts

**Problem:** (1) kiso.toml manca la riga `guide:` che il planner di Kiso
tratta come regola obbligatoria — senza di essa il planner può usare il browser
per fare ricerche web anziché navigare URL noti. (2) Se una pagina non risponde,
il processo resta appeso indefinitamente e blocca la sessione Kiso. (3) `el.click()`
e `el.fill()` non hanno timeout — se l'elemento non è interagibile, stallo.

**Files:** `kiso.toml`, `run.py`

**Changes:**

1. **kiso.toml** — riscrivere `summary` e `usage_guide` con la riga `guide:`:
   ```toml
   summary = "Navigate to specific URLs, inspect page elements, click, fill forms, take screenshots"
   usage_guide = """\
   guide: This tool is for navigating to SPECIFIC known URLs and interacting with those pages. \
   NEVER use it for web searches — use the search task type or the websearch tool instead. \
   Browser is slow, may hit CAPTCHAs, and has no search capability.
   ...
   """
   ```

2. **run.py — global 60s timeout** in `main()`:
   ```python
   signal.signal(signal.SIGALRM, lambda *_: (
       print("Browser operation timed out after 60s", file=sys.stderr),
       sys.exit(1),
   ))
   signal.alarm(60)
   ```

3. **run.py — timeout su click e fill**:
   ```python
   def click_element(page, ref: str) -> None:
       el = resolve_element(page, ref)
       el.click(timeout=10000)  # 10s timeout
       ...

   def fill_element(page, ref: str, value: str) -> None:
       el = resolve_element(page, ref)
       el.fill(value, timeout=10000)  # 10s timeout
   ```

**Note:** l'azione `text` richiesta nel ticket esiste già (`do_text` + `extract_text`).

- [x] Aggiornare `summary` e `usage_guide` in kiso.toml
- [x] Aggiungere global timeout 60s in `main()`
- [x] Aggiungere `timeout=10000` a `el.click()` e `el.fill()`
- [x] Aggiornare test se necessario
- [x] Estrarre costanti timeout + handler SIGALRM come funzione named (da /simplify)

---

### M9 — Complete test coverage ✅

**Problem:** Several core functions in `run.py` lacked dedicated unit tests:
`extract_text()` noise/container logic, `extract_links()` filtering/dedup,
`resolve_element()` ref resolution, `_page_header()`, and timeout constants.
Total test count was 109; gaps left regressions possible.

**Files:** 5 new test files in `tests/`

**Changes:**

1. `tests/test_extract_text.py` (8 tests) — CSS selector scoping, selector not
   found error, noise removal via `page.evaluate`, content container priority
   (`main` → `article` → `[role='main']`), body fallback, empty body, empty
   container skip.

2. `tests/test_extract_links.py` (8 tests) — filters `javascript:` and `#`
   hrefs, deduplicates same href, filters empty-text links, scopes to CSS
   selector, defaults to `body` scope, no-links message, header inclusion.

3. `tests/test_resolve_element.py` (6 tests) — `[1]` bracket ref, bare `2`
   number, out-of-range error with element count, `[0]` error, CSS selector via
   `query_selector`, CSS not found error.

4. `tests/test_timeouts.py` (1 test) — verifies all 6 timeout constants match
   expected values.

5. `tests/test_page_header.py` (1 test) — verifies `_page_header()` output
   format.

**Result:** 133 tests total (24 new), all passing.

- [x] Add `test_extract_text.py`
- [x] Add `test_extract_links.py`
- [x] Add `test_resolve_element.py`
- [x] Add `test_timeouts.py`
- [x] Add `test_page_header.py`

---

## Known Issues / Improvement Ideas

- No integration tests — all tests use mocks; a real-browser test suite
  (against a local HTML fixture server) would catch Playwright API mismatches
- Screenshots are full-page PNG only — no element-scoped or viewport-only
  option, no WebP support
- Timeout constants are module-level in `run.py` but not user-configurable
  (no env var or kiso.toml override)
- No scroll/pagination support — long pages require manual snapshot + click
  workflows
- `extract_text` noise stripping mutates the DOM (removes elements) — if the
  same page object is reused, subsequent calls may miss content
- No JavaScript execution action — cannot run arbitrary JS snippets
- Element resolution re-queries the full snapshot selector list on every
  click/fill — could cache between calls within the same invocation
