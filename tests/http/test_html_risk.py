"""HTML 风控页检测与 get_weibo_json 冷却/哨兵行为。"""

from __future__ import annotations

import os
import sys
import unittest
from unittest import mock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tests import _support  # noqa: E402

_support.bootstrap()

from util.http import http_client, weibo_json  # noqa: E402
from util.fetch import fetch_pages  # noqa: E402


class _Resp:
    def __init__(self, status=200, ctype="text/html", text="", raise_status=True):
        self.status_code = status
        self.headers = {"Content-Type": ctype}
        self.text = text
        self.content = text.encode("utf-8")
        self._raise_status = raise_status

    def raise_for_status(self):
        if not self._raise_status or self.status_code >= 400:
            raise Exception(f"{self.status_code} error")

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


class LooksLikeHtmlRiskTest(unittest.TestCase):
    def test_content_type_html(self):
        self.assertTrue(
            weibo_json.looks_like_html_risk(
                _Resp(ctype="text/html; charset=utf-8", text="<html></html>")
            )
        )

    def test_doctype_body(self):
        self.assertTrue(
            weibo_json.looks_like_html_risk(
                _Resp(ctype="application/octet-stream", text="<!doctype html>\n<html>")
            )
        )

    def test_json_not_risk(self):
        self.assertFalse(
            weibo_json.looks_like_html_risk(
                _Resp(ctype="application/json", text='{"ok":1}')
            )
        )


class ApiHeadersTest(unittest.TestCase):
    def test_sec_fetch_mode_is_cors(self):
        headers = http_client.random_headers(
            True,
            {
                "user_agents": ["UA"],
                "accept_languages": ["zh"],
                "referer_list": ["https://m.weibo.cn/"],
            },
            {},
        )
        self.assertEqual(headers.get("sec-fetch-mode"), "cors")
        self.assertEqual(headers.get("x-requested-with"), "XMLHttpRequest")
        self.assertNotIn("upgrade-insecure-requests", headers)


class _HtmlSession:
    def __init__(self):
        self.calls = 0

    def get(self, *a, **k):
        self.calls += 1
        return _Resp(
            text="<!doctype html>\n<html lang='en'><head>"
            "<link rel='shortcut icon' href='https://weibo'></head>"
        )


def _risk_wb(refresh_result=False):
    wb = mock.Mock()
    wb.user_config = {"user_id": "123"}
    wb.query = ""
    wb.page_weibo_count = 20
    wb.session = _HtmlSession()
    wb.get_random_headers = lambda: {}
    wb.calculate_dynamic_delay = lambda: 0
    wb.update_crawl_stats = mock.Mock()
    wb.try_auto_refresh_cookie = mock.Mock(return_value=refresh_result)
    wb.anti_ban_config = {}
    wb.crawl_success = {}
    return wb


class GetWeiboJsonHtmlRiskTest(unittest.TestCase):
    def test_returns_sentinel_without_request_layer_cooldown(self):
        """刷新 Cookie 无效时立即交上层，不在请求层反复冷却重试。"""
        wb = _risk_wb(refresh_result=False)
        sleeps = []
        with mock.patch.object(weibo_json, "_sleep", side_effect=sleeps.append):
            result = weibo_json.get_weibo_json(wb, 2)

        self.assertEqual(result, weibo_json.HTML_RISK)
        self.assertEqual(wb.session.calls, 1)
        self.assertEqual(sleeps, [])
        self.assertTrue(wb.crawl_success.get("html_risk"))
        wb.try_auto_refresh_cookie.assert_called_once()
        wb.update_crawl_stats.assert_called_with(api_error=True)

    def test_retries_once_after_cookie_refresh(self):
        wb = _risk_wb(refresh_result=True)
        with mock.patch.object(weibo_json, "_sleep", lambda s: None):
            result = weibo_json.get_weibo_json(wb, 2)

        self.assertEqual(result, weibo_json.HTML_RISK)
        self.assertEqual(wb.session.calls, 2)


class GetOnePageHtmlRiskTest(unittest.TestCase):
    def test_html_risk_returns_sentinel(self):
        wb = mock.Mock()
        wb.get_weibo_json = lambda page: weibo_json.HTML_RISK
        wb.crawl_success = {}
        self.assertEqual(fetch_pages.get_one_page(wb, 2), weibo_json.HTML_RISK)
        self.assertIn("HTML风控", wb.crawl_success.get("reason", ""))


if __name__ == "__main__":
    unittest.main()
