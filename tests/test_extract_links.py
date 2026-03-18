"""Tests for extract_links() — filtering, dedup, scoping."""
from unittest.mock import MagicMock

from conftest import make_mock_page
from run import extract_links


def _make_anchor(href, text):
    a = MagicMock()
    a.get_attribute.side_effect = lambda k: href if k == "href" else None
    a.inner_text.return_value = text
    return a


def test_filters_javascript_hrefs():
    page = make_mock_page()
    page.query_selector_all.return_value = [
        _make_anchor("javascript:void(0)", "Bad link"),
        _make_anchor("https://example.com/good", "Good link"),
    ]

    result = extract_links(page)
    assert "Bad link" not in result
    assert "Good link" in result
    assert "1. Good link" in result


def test_filters_hash_only_hrefs():
    page = make_mock_page()
    page.query_selector_all.return_value = [
        _make_anchor("#", "Hash link"),
        _make_anchor("https://example.com/real", "Real link"),
    ]

    result = extract_links(page)
    assert "Hash link" not in result
    assert "Real link" in result


def test_deduplicates_same_href():
    page = make_mock_page()
    page.query_selector_all.return_value = [
        _make_anchor("https://example.com/page", "Link A"),
        _make_anchor("https://example.com/page", "Link B"),
    ]

    result = extract_links(page)
    assert "1. Link A" in result
    assert "Link B" not in result


def test_filters_empty_text_links():
    page = make_mock_page()
    page.query_selector_all.return_value = [
        _make_anchor("https://example.com/empty", ""),
        _make_anchor("https://example.com/nonempty", "Visible"),
    ]

    result = extract_links(page)
    assert "1. Visible" in result
    # Only one numbered link
    assert "2." not in result


def test_scopes_to_css_selector():
    page = make_mock_page()
    page.query_selector_all.return_value = [
        _make_anchor("https://example.com/scoped", "Scoped link"),
    ]

    result = extract_links(page, selector=".sidebar")

    page.query_selector_all.assert_called_once_with(".sidebar a[href]")
    assert "Scoped link" in result


def test_no_selector_uses_body_scope():
    page = make_mock_page()
    page.query_selector_all.return_value = []

    result = extract_links(page)

    page.query_selector_all.assert_called_once_with("body a[href]")
    assert "(no links found)" in result


def test_no_links_shows_message():
    page = make_mock_page()
    page.query_selector_all.return_value = []

    result = extract_links(page)
    assert "(no links found)" in result


def test_header_included():
    page = make_mock_page(title="Links Page", url="https://example.com/links")
    page.query_selector_all.return_value = [
        _make_anchor("https://example.com/a", "A"),
    ]

    result = extract_links(page)
    assert result.startswith("Page: Links Page\nURL: https://example.com/links")
