"""Tests for _detect_captcha and its integration with snapshot."""
from unittest.mock import MagicMock

from run import _detect_captcha, snapshot
from conftest import make_mock_element, make_mock_page


class TestDetectCaptcha:
    def test_detects_recaptcha_iframe(self):
        page = MagicMock()
        page.query_selector.side_effect = (
            lambda sel: MagicMock() if "recaptcha" in sel else None
        )
        assert _detect_captcha(page) is True

    def test_detects_hcaptcha_class(self):
        page = MagicMock()
        page.query_selector.side_effect = (
            lambda sel: MagicMock() if sel == ".h-captcha" else None
        )
        assert _detect_captcha(page) is True

    def test_detects_data_sitekey(self):
        page = MagicMock()
        page.query_selector.side_effect = (
            lambda sel: MagicMock() if sel == "[data-sitekey]" else None
        )
        assert _detect_captcha(page) is True

    def test_returns_false_when_no_captcha(self):
        page = MagicMock()
        page.query_selector.return_value = None
        assert _detect_captcha(page) is False


class TestSnapshotCaptchaWarning:
    def test_snapshot_includes_captcha_warning(self):
        page = make_mock_page(elements=[make_mock_element("button", "Submit")])
        # Make query_selector return a match for recaptcha iframe
        original_qsa = page.query_selector_all.return_value

        def qs(sel):
            if "recaptcha" in sel:
                return MagicMock()
            return None
        page.query_selector.side_effect = qs

        result = snapshot(page)
        assert "CAPTCHA detected" in result
        assert "[1]" in result

    def test_snapshot_no_warning_without_captcha(self):
        page = make_mock_page(elements=[make_mock_element("button", "Submit")])
        page.query_selector.return_value = None
        result = snapshot(page)
        assert "CAPTCHA" not in result
        assert "[1]" in result
