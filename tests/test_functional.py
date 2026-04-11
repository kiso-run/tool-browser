"""Functional tests — subprocess contract for run.py.

Tests in two tiers:
  1. Always-run: error paths that don't need a real browser.
  2. Playwright-dependent: skip if playwright is not importable.
"""
from __future__ import annotations

import http.server
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
RUN_PY = str(ROOT / "run.py")

# Detect whether playwright + browser deps are available.
def _can_launch_browser() -> bool:
    """Return True only if playwright is importable AND WebKit can launch."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    # Playwright is installed but system libs may be missing — probe.
    import subprocess as _sp, tempfile
    r = _sp.run(
        [sys.executable, "-c",
         "from playwright.sync_api import sync_playwright; import tempfile, os; "
         "d = tempfile.mkdtemp(); "
         "p = sync_playwright().start(); "
         "ctx = p.webkit.launch_persistent_context(os.path.join(d,'p'), headless=True); "
         "ctx.close(); p.stop()"],
        capture_output=True, timeout=15,
    )
    return r.returncode == 0

_HAS_BROWSER = _can_launch_browser()

needs_playwright = pytest.mark.skipif(
    not _HAS_BROWSER,
    reason="playwright not installed or browser deps missing",
)

_FIXTURE_HTML = (
    "<html><head><title>Test Page</title></head>"
    "<body>"
    "<p>Hello World</p>"
    "<a href=\"/other\">Other Link</a>"
    "<form action=\"/submit\" method=\"POST\">"
    "<input type=\"text\" name=\"field1\" placeholder=\"Enter text\">"
    "<button type=\"submit\">Submit</button>"
    "</form>"
    "</body></html>"
)


# ---------------------------------------------------------------------------
# Fixture HTTP server
# ---------------------------------------------------------------------------

def _start_fixture_server(html_content: str, port: int = 0):
    """Start a local HTTP server serving html_content on all GET paths."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(html_content.encode())

        def log_message(self, *a):
            pass  # suppress logs

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _start_slow_server(delay: float = 120.0, port: int = 0):
    """Start a server that delays response by `delay` seconds."""
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(delay)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>slow</body></html>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_wrapper(input_data, *, workspace: str | None = None, timeout: int = 70):
    """Run run.py as subprocess. Returns CompletedProcess."""
    if isinstance(input_data, dict):
        stdin_text = json.dumps(input_data)
    else:
        stdin_text = input_data  # raw string for malformed tests
    return subprocess.run(
        [sys.executable, RUN_PY],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _make_input(action: str, workspace: str = "/tmp/test-func", **extra_args):
    args = {"action": action}
    args.update(extra_args)
    return {
        "args": args,
        "workspace": workspace,
        "session": "test-session",
        "session_secrets": {},
        "plan_outputs": [],
    }


# ===================================================================
# ALWAYS-RUN TESTS (no browser needed)
# ===================================================================

class TestErrorPaths:
    """These tests should pass regardless of whether Playwright is installed."""

    def test_unknown_action(self):
        """Unknown action exits 1 (either at playwright import or dispatch)."""
        result = _run_wrapper(_make_input("nope"), timeout=15)
        assert result.returncode == 1

    def test_malformed_input_invalid_json(self):
        """Invalid JSON on stdin exits 1."""
        result = _run_wrapper("not json at all", timeout=15)
        assert result.returncode == 1

    def test_malformed_input_missing_args(self):
        """Missing 'args' key exits 1."""
        result = _run_wrapper({}, timeout=15)
        assert result.returncode == 1

    def test_malformed_input_empty_stdin(self):
        """Empty stdin exits 1."""
        result = _run_wrapper("", timeout=15)
        assert result.returncode == 1


# ===================================================================
# PLAYWRIGHT-DEPENDENT TESTS
# ===================================================================

@needs_playwright
class TestHappyPaths:
    """Full integration tests using a local fixture server + real WebKit."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.workspace = str(tmp_path)
        self.server = _start_fixture_server(_FIXTURE_HTML)
        self.port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        yield
        self.server.shutdown()

    def _input(self, action: str, **kwargs):
        return _make_input(action, workspace=self.workspace, **kwargs)

    # --- M10 tests ---

    def test_navigate_happy_path(self):
        """Navigate to local fixture, stdout contains page title, exit 0."""
        result = _run_wrapper(self._input("navigate", url=f"{self.base_url}/page.html"))
        assert result.returncode == 0
        assert "Test Page" in result.stdout

    def test_state_persistence(self):
        """After navigate, text action without url uses saved state."""
        # First call: navigate
        r1 = _run_wrapper(self._input("navigate", url=f"{self.base_url}/page.html"))
        assert r1.returncode == 0
        # Second call: text (no url arg)
        r2 = _run_wrapper(self._input("text"))
        assert r2.returncode == 0
        assert "Hello World" in r2.stdout

    def test_screenshot_saves_file(self):
        """Screenshot action creates a file on disk."""
        _run_wrapper(self._input("navigate", url=f"{self.base_url}/page.html"))
        result = _run_wrapper(self._input("screenshot"))
        assert result.returncode == 0
        screenshot_path = Path(self.workspace) / "screenshot.png"
        assert screenshot_path.exists()
        assert screenshot_path.stat().st_size > 0

    def test_snapshot_and_click(self):
        """Snapshot returns numbered elements; click works by ref."""
        _run_wrapper(self._input("navigate", url=f"{self.base_url}/page.html"))
        r_snap = _run_wrapper(self._input("snapshot"))
        assert r_snap.returncode == 0
        assert "[1]" in r_snap.stdout

        r_click = _run_wrapper(self._input("click", element="1"))
        assert r_click.returncode == 0
        assert "Clicked" in r_click.stdout

    def test_forms_and_fill(self):
        """Forms action returns fields; fill echoes the value."""
        _run_wrapper(self._input("navigate", url=f"{self.base_url}/page.html"))
        r_forms = _run_wrapper(self._input("forms"))
        assert r_forms.returncode == 0
        assert "Enter text" in r_forms.stdout or "field1" in r_forms.stdout

        r_fill = _run_wrapper(self._input("fill", element="input[name='field1']", value="hello"))
        assert r_fill.returncode == 0
        assert "with: 'hello'" in r_fill.stdout

    def test_navigate_dedup(self):
        """Second navigate to same URL returns 'Already on'."""
        url = f"{self.base_url}/page.html"
        _run_wrapper(self._input("navigate", url=url))
        r2 = _run_wrapper(self._input("navigate", url=url))
        assert r2.returncode == 0
        assert "Already on" in r2.stdout

    def test_links(self):
        """Links action extracts links from fixture page."""
        _run_wrapper(self._input("navigate", url=f"{self.base_url}/page.html"))
        result = _run_wrapper(self._input("links"))
        assert result.returncode == 0
        assert "Other Link" in result.stdout


# ===================================================================
# M11 — SIGTERM graceful shutdown
# ===================================================================

@needs_playwright
class TestSigterm:
    """Verify SIGTERM causes graceful exit (exit code 0)."""

    def test_sigterm_graceful_shutdown(self, tmp_path):
        """Start run.py navigating to a slow server, send SIGTERM, expect exit 0."""
        workspace = str(tmp_path)
        server = _start_slow_server(delay=120.0)
        port = server.server_address[1]

        input_data = _make_input(
            "navigate",
            workspace=workspace,
            url=f"http://127.0.0.1:{port}/slow",
        )

        proc = subprocess.Popen(
            [sys.executable, RUN_PY],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc.stdin.write(json.dumps(input_data))
        proc.stdin.close()

        # Give the process time to start and begin the navigation.
        time.sleep(2)

        # Send SIGTERM.
        proc.send_signal(signal.SIGTERM)

        # Wait for exit with timeout.
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            pytest.fail("Process did not exit after SIGTERM within 10s")

        assert proc.returncode == 0, (
            f"Expected exit 0 on SIGTERM, got {proc.returncode}. "
            f"stderr: {proc.stderr.read()}"
        )
        server.shutdown()
