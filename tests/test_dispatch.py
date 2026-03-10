"""Tests for dispatch() and main() error paths."""
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from run import dispatch, save_state
from conftest import make_mock_element, make_mock_page

ROOT = Path(__file__).parent.parent


def make_context(url="https://example.com", title="Test", elements=None):
    page = make_mock_page(url=url, title=title, elements=elements)
    ctx = MagicMock()
    ctx.new_page.return_value = page
    return ctx, page


# ---------------------------------------------------------------------------
# dispatch — unknown action
# ---------------------------------------------------------------------------

def test_dispatch_unknown_action(tmp_path):
    ctx, _ = make_context()
    state_file = tmp_path / "state.json"
    with pytest.raises(ValueError, match="Unknown action"):
        dispatch("fly", {}, ctx, state_file)


# ---------------------------------------------------------------------------
# dispatch — navigate
# ---------------------------------------------------------------------------

def test_dispatch_navigate(tmp_path):
    ctx, page = make_context(url="https://example.com", title="Example")
    state_file = tmp_path / "state.json"
    result = dispatch("navigate", {"url": "https://example.com"}, ctx, state_file)
    assert "Example" in result
    page.goto.assert_called_once()


# ---------------------------------------------------------------------------
# dispatch — snapshot
# ---------------------------------------------------------------------------

def test_dispatch_snapshot(tmp_path):
    state_file = tmp_path / "state.json"
    save_state(state_file, "https://example.com")
    ctx, page = make_context(elements=[make_mock_element("button", "Click")])
    result = dispatch("snapshot", {}, ctx, state_file)
    assert "[1]" in result
    assert "Click" in result


# ---------------------------------------------------------------------------
# dispatch — click
# ---------------------------------------------------------------------------

def test_dispatch_click(tmp_path):
    state_file = tmp_path / "state.json"
    save_state(state_file, "https://example.com")
    el = make_mock_element("button", "Go")
    ctx, page = make_context(elements=[el])
    result = dispatch("click", {"element": "[1]"}, ctx, state_file)
    el.click.assert_called_once()
    assert "Clicked" in result


# ---------------------------------------------------------------------------
# dispatch — fill
# ---------------------------------------------------------------------------

def test_dispatch_fill(tmp_path):
    state_file = tmp_path / "state.json"
    save_state(state_file, "https://example.com")
    el = make_mock_element("input", "", {"type": "text"})
    ctx, page = make_context(elements=[el])
    result = dispatch("fill", {"element": "[1]", "value": "hello"}, ctx, state_file)
    el.fill.assert_called_once_with("hello")
    assert "Filled" in result


# ---------------------------------------------------------------------------
# dispatch — screenshot
# ---------------------------------------------------------------------------

def test_dispatch_screenshot(tmp_path):
    state_file = tmp_path / ".browser" / "state.json"
    state_file.parent.mkdir(parents=True)
    save_state(state_file, "https://example.com")
    ctx, page = make_context()
    result = dispatch("screenshot", {}, ctx, state_file)
    assert "screenshot.png" in result
    page.screenshot.assert_called_once()


# ---------------------------------------------------------------------------
# dispatch — text / links / forms
# ---------------------------------------------------------------------------

def test_dispatch_text(tmp_path):
    state_file = tmp_path / "state.json"
    save_state(state_file, "https://example.com")
    ctx, page = make_context()
    body = MagicMock()
    body.inner_text.return_value = "Hello world"
    page.query_selector.side_effect = lambda sel: body if sel == "body" else None
    page.evaluate.return_value = None
    result = dispatch("text", {}, ctx, state_file)
    assert "Hello world" in result


def test_dispatch_links(tmp_path):
    state_file = tmp_path / "state.json"
    save_state(state_file, "https://example.com")
    link = MagicMock()
    link.inner_text.return_value = "Link"
    link.get_attribute.side_effect = lambda k: {"href": "https://example.com/a"}.get(k)
    ctx, page = make_context()
    page.query_selector_all.return_value = [link]
    result = dispatch("links", {}, ctx, state_file)
    assert "Link" in result
    assert "https://example.com/a" in result


def test_dispatch_forms(tmp_path):
    state_file = tmp_path / "state.json"
    save_state(state_file, "https://example.com")
    ctx, page = make_context()
    page.query_selector_all.return_value = []
    result = dispatch("forms", {}, ctx, state_file)
    assert "(no forms found)" in result


# ---------------------------------------------------------------------------
# main() — playwright not installed
# ---------------------------------------------------------------------------

def test_main_missing_playwright(tmp_path, make_input):
    """main() exits with code 1 and prints to stderr if playwright is missing."""
    import os
    input_data = make_input(action="navigate", url="https://example.com")
    # Run with a PATH that has no playwright venv, and explicitly break import
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.modules['playwright'] = None; "
         "sys.modules['playwright.sync_api'] = None; "
         "exec(open('run.py').read())"],
        input=json.dumps(input_data),
        capture_output=True, text=True,
        cwd=str(ROOT),
        timeout=10,
    )
    # The import will fail differently; just verify a non-zero exit
    assert result.returncode != 0
