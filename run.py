"""tool-browser — headless WebKit automation via Playwright.

Subprocess contract (same as all kiso tools):
  stdin:  JSON {args, session, workspace, session_secrets, plan_outputs}
  stdout: result text on success
  stderr: error description on failure
  exit 0: success, exit 1: failure
"""
from __future__ import annotations

import json
import re
import signal
import sys
from pathlib import Path

signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

# Selectors for elements included in the numbered snapshot.
_SNAPSHOT_SELECTORS = (
    "a, button, input, select, textarea, "
    "[role='button'], [role='link'], [role='checkbox'], "
    "[role='radio'], [role='menuitem']"
)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    data = json.load(sys.stdin)
    args = data["args"]
    workspace = Path(data.get("workspace", "/tmp"))
    action = args.get("action", "snapshot")

    browser_dir = workspace / ".browser"
    browser_dir.mkdir(parents=True, exist_ok=True)
    state_file = browser_dir / "state.json"

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print(
            "Playwright is not installed. Re-run: kiso tool install tool-browser",
            file=sys.stderr,
        )
        sys.exit(1)

    with sync_playwright() as p:
        context = p.webkit.launch_persistent_context(
            user_data_dir=str(browser_dir / "profile"),
            headless=True,
        )
        try:
            result = dispatch(action, args, context, state_file)
            print(result)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(1)
        finally:
            context.close()


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(action: str, args: dict, context, state_file: Path) -> str:
    page = context.new_page()
    if action == "navigate":
        return do_navigate(page, args, state_file)
    if action == "snapshot":
        return do_snapshot(page, args, state_file)
    if action == "text":
        return do_text(page, args, state_file)
    if action == "links":
        return do_links(page, args, state_file)
    if action == "forms":
        return do_forms(page, args, state_file)
    if action == "click":
        return do_click(page, args, state_file)
    if action == "fill":
        return do_fill(page, args, state_file)
    if action == "screenshot":
        return do_screenshot(page, args, state_file)
    raise ValueError(
        f"Unknown action: {action!r}. "
        "Use: navigate, text, links, forms, snapshot, click, fill, screenshot"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _urls_match(a: str, b: str) -> bool:
    """Check if two URLs are equivalent, ignoring trailing slashes and fragments."""
    from urllib.parse import urlparse  # noqa: PLC0415
    pa, pb = urlparse(a), urlparse(b)
    return (
        pa.scheme == pb.scheme
        and pa.netloc == pb.netloc
        and pa.path.rstrip("/") == pb.path.rstrip("/")
        and pa.query == pb.query
    )


_COOKIE_ACCEPT_SELECTORS = [
    "button:has-text('Accept')", "button:has-text('Accetta')",
    "button:has-text('Accept all')", "button:has-text('Accetta tutti')",
    "[id*='cookie'] button:has-text('OK')",
    ".cookie-banner button.accept", "#onetrust-accept-btn-handler",
]


def _dismiss_cookie_consent(page) -> bool:
    """Try to dismiss cookie consent banners using common selectors."""
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


def _ensure_page(page, args: dict, state_file: Path) -> None:
    """Navigate to page from explicit url arg or saved state, then save state."""
    url = args.get("url", "").strip()
    if url:
        page.goto(url, timeout=30000)
    else:
        url = load_state(state_file)
        if not url:
            raise ValueError("No current page. Use action='navigate' or provide 'url'.")
        page.goto(url, timeout=30000)
    save_state(state_file, page.url)


def _page_header(page) -> str:
    return f"Page: {page.title()}\nURL: {page.url}"


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def do_navigate(page, args: dict, state_file: Path) -> str:
    url = args.get("url", "").strip()
    if not url:
        raise ValueError("navigate: 'url' argument is required")
    current = load_state(state_file)
    if current and _urls_match(current, url):
        page.goto(current, timeout=30000)
        save_state(state_file, page.url)
        return f"Already on {url}.\n\n{snapshot(page)}"
    page.goto(url, timeout=30000)
    _dismiss_cookie_consent(page)
    save_state(state_file, page.url)
    return f"Navigated to: {page.title()}\nURL: {page.url}"


def do_snapshot(page, args: dict, state_file: Path) -> str:
    current_url = load_state(state_file)
    if not current_url:
        raise ValueError("No current page. Use action='navigate' first.")
    page.goto(current_url, timeout=30000)
    save_state(state_file, page.url)
    return snapshot(page)


def do_text(page, args: dict, state_file: Path) -> str:
    _ensure_page(page, args, state_file)
    selector = args.get("selector", "").strip()
    return extract_text(page, selector or None)


def do_links(page, args: dict, state_file: Path) -> str:
    _ensure_page(page, args, state_file)
    selector = args.get("selector", "").strip()
    return extract_links(page, selector or None)


def do_forms(page, args: dict, state_file: Path) -> str:
    _ensure_page(page, args, state_file)
    selector = args.get("selector", "").strip()
    return extract_forms(page, selector or None)


def do_click(page, args: dict, state_file: Path) -> str:
    current_url = load_state(state_file)
    if not current_url:
        raise ValueError("No current page. Use action='navigate' first.")
    ref = args.get("element", "").strip()
    if not ref:
        raise ValueError("click: 'element' argument is required")
    page.goto(current_url, timeout=30000)
    click_element(page, ref)
    save_state(state_file, page.url)
    return f"Clicked {ref!r}. URL: {page.url}\n\n{snapshot(page)}"


def do_fill(page, args: dict, state_file: Path) -> str:
    current_url = load_state(state_file)
    if not current_url:
        raise ValueError("No current page. Use action='navigate' first.")
    ref = args.get("element", "").strip()
    if not ref:
        raise ValueError("fill: 'element' argument is required")
    value = args.get("value", "")
    page.goto(current_url, timeout=30000)
    fill_element(page, ref, value)
    save_state(state_file, page.url)
    return f"Filled {ref!r} with: {value!r}. URL: {page.url}\n\n{snapshot(page)}"


def do_screenshot(page, args: dict, state_file: Path) -> str:
    current_url = load_state(state_file)
    if not current_url:
        raise ValueError("No current page. Use action='navigate' first.")
    page.goto(current_url, timeout=30000)
    out_path = state_file.parent.parent / "screenshot.png"
    page.screenshot(path=str(out_path))
    return f"Screenshot saved: {out_path}"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

_CAPTCHA_MARKERS = [
    "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']",
    "iframe[src*='turnstile']", ".g-recaptcha", ".h-captcha",
    "[data-sitekey]",
]


def _detect_captcha(page) -> bool:
    """Return True if the page contains a known CAPTCHA element."""
    for sel in _CAPTCHA_MARKERS:
        if page.query_selector(sel):
            return True
    return False


def snapshot(page) -> str:
    """Return a numbered list of interactive elements for the current page."""
    elements = page.query_selector_all(_SNAPSHOT_SELECTORS)
    lines = [_page_header(page), ""]
    if _detect_captcha(page):
        lines.append(
            "CAPTCHA detected on this page. "
            "Form submission may require human verification."
        )
        lines.append("")
    for i, el in enumerate(elements, 1):
        lines.append(f"[{i}] {_describe_element(el)}")
    if not elements:
        lines.append("(no interactive elements found)")
    return "\n".join(lines)


def _describe_element(el) -> str:
    tag = el.evaluate("e => e.tagName.toLowerCase()")
    parts = [f"<{tag}"]
    for attr in ("type", "name", "placeholder", "href"):
        v = el.get_attribute(attr)
        if v:
            parts.append(f' {attr}="{v[:80]}"')
    text = (el.inner_text() or "").strip()[:80]
    if text:
        parts.append(f">{text}</{tag}>")
    else:
        parts.append(">")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Text / Links / Forms extraction
# ---------------------------------------------------------------------------

# Selectors for noise elements stripped from text extraction.
_NOISE_SELECTORS = (
    "nav, header, footer, "
    "[role='navigation'], [role='banner'], [role='contentinfo'], "
    ".cookie-banner, [class*='cookie'], [id*='cookie'], "
    ".ads, [class*='ad-banner'], aside"
)

# Selectors for content containers, tried in priority order.
_CONTENT_SELECTORS = ("main", "article", "[role='main']")


def extract_text(page, selector: str | None = None) -> str:
    """Return visible text content, stripped of navigation noise."""
    if selector:
        el = page.query_selector(selector)
        if not el:
            raise ValueError(f"Selector not found: {selector!r}")
        text = el.inner_text() or ""
        return f"{_page_header(page)}\n\n{text.strip()}"

    # Remove noise elements from DOM before extraction.
    page.evaluate(
        """sel => document.querySelectorAll(sel).forEach(e => e.remove())""",
        _NOISE_SELECTORS,
    )

    # Try content containers first, fall back to body.
    for cs in _CONTENT_SELECTORS:
        el = page.query_selector(cs)
        if el:
            text = el.inner_text() or ""
            if text.strip():
                return f"{_page_header(page)}\n\n{text.strip()}"

    body = page.query_selector("body")
    text = (body.inner_text() if body else "") or ""
    return f"{_page_header(page)}\n\n{text.strip()}"


def extract_links(page, selector: str | None = None) -> str:
    """Return a numbered list of links with text and href."""
    scope = selector or "body"
    anchors = page.query_selector_all(f"{scope} a[href]")
    seen: set[str] = set()
    lines = [_page_header(page), ""]
    n = 0
    for a in anchors:
        href = (a.get_attribute("href") or "").strip()
        if not href or href.startswith("javascript:") or href == "#":
            continue
        if href in seen:
            continue
        seen.add(href)
        text = (a.inner_text() or "").strip()[:120]
        if not text:
            continue
        n += 1
        lines.append(f"{n}. {text} — {href}")
    if n == 0:
        lines.append("(no links found)")
    return "\n".join(lines)


def extract_forms(page, selector: str | None = None) -> str:
    """Return structured form field information."""
    scope = f"{selector} form" if selector else "form"
    forms = page.query_selector_all(scope)
    lines = [_page_header(page), ""]
    if not forms:
        lines.append("(no forms found)")
        return "\n".join(lines)

    for i, form in enumerate(forms, 1):
        action = form.get_attribute("action") or ""
        method = (form.get_attribute("method") or "GET").upper()
        lines.append(f"Form {i} (action: {action}, method: {method}):")

        fields = form.query_selector_all("input, select, textarea, button")
        for field in fields:
            tag = field.evaluate("e => e.tagName.toLowerCase()")
            ftype = field.get_attribute("type") or ""

            # Determine label from aria-label, placeholder, or name.
            label = (
                field.get_attribute("aria-label")
                or field.get_attribute("placeholder")
                or field.get_attribute("name")
                or ""
            )
            req = ", required" if field.get_attribute("required") is not None else ""

            if tag == "button" or (tag == "input" and ftype in ("submit", "button", "reset")):
                btn_text = (field.inner_text() or "").strip() or field.get_attribute("value") or ftype
                lines.append(f"  - [{btn_text}] (button)")
            elif tag == "select":
                options = field.query_selector_all("option")
                opt_texts = []
                for opt in options[:10]:
                    t = (opt.inner_text() or "").strip()
                    if t:
                        opt_texts.append(t)
                if len(options) > 10:
                    opt_texts.append("...")
                lines.append(f"  - {label} (select{req}): [{', '.join(opt_texts)}]")
            else:
                value = field.get_attribute("value") or ""
                desc = ftype or tag
                lines.append(f"  - {label} ({desc}{req}): \"{value}\"")
        lines.append("")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Element resolution
# ---------------------------------------------------------------------------

def resolve_element(page, ref: str):
    """Resolve a [N] reference or CSS selector to a Playwright element handle."""
    m = re.match(r"^\[?(\d+)\]?$", ref.strip())
    if m:
        n = int(m.group(1)) - 1
        elements = page.query_selector_all(_SNAPSHOT_SELECTORS)
        if 0 <= n < len(elements):
            return elements[n]
        raise ValueError(
            f"Element [{int(m.group(1))}] not found (page has {len(elements)} elements)"
        )
    el = page.query_selector(ref)
    if el:
        return el
    raise ValueError(f"Element not found: {ref!r}")


def click_element(page, ref: str) -> None:
    el = resolve_element(page, ref)
    el.click()
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass  # navigation may not have occurred


def fill_element(page, ref: str, value: str) -> None:
    el = resolve_element(page, ref)
    el.fill(value)


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def save_state(state_file: Path, url: str) -> None:
    state_file.write_text(json.dumps({"url": url}))


def load_state(state_file: Path) -> str | None:
    if not state_file.exists():
        return None
    try:
        return json.loads(state_file.read_text()).get("url")
    except Exception:
        return None


if __name__ == "__main__":
    main()
