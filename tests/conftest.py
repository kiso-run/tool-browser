import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).parent.parent


@pytest.fixture
def make_input():
    def _make(action="snapshot", **kwargs):
        args = {"action": action}
        args.update(kwargs)
        return {
            "args": args,
            "session": "test-session",
            "workspace": "/tmp/test-browser-workspace",
            "session_secrets": {},
            "plan_outputs": [],
        }
    return _make


@pytest.fixture
def run_wrapper():
    """Run run.py as a subprocess with controlled stdin."""
    def _run(input_data, env=None):
        import os
        process_env = {"PATH": os.environ.get("PATH", "")}
        if env:
            process_env.update(env)
        return subprocess.run(
            [sys.executable, str(ROOT / "run.py")],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            env=process_env,
            timeout=10,
        )
    return _run


def make_mock_element(tag="a", text="Click me", attrs=None):
    """Build a mock Playwright element handle."""
    el = MagicMock()
    el.evaluate.return_value = tag
    attrs_dict = attrs or {}
    el.get_attribute.side_effect = lambda k: attrs_dict.get(k)
    el.inner_text.return_value = text
    return el


def make_mock_page(url="https://example.com", title="Test Page", elements=None):
    """Build a mock Playwright page."""
    page = MagicMock()
    page.url = url
    page.title.return_value = title
    page.query_selector_all.return_value = elements if elements is not None else []
    page.query_selector.return_value = None
    return page
