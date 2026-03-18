"""Tests for _page_header()."""
from conftest import make_mock_page
from run import _page_header


def test_returns_title_and_url():
    page = make_mock_page(title="My Title", url="https://example.com/path")
    result = _page_header(page)
    assert result == "Page: My Title\nURL: https://example.com/path"
