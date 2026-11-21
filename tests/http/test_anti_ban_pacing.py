"""防限流：统一节奏、跨运行熔断、请求头一致性、长文详情跳过。"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tests import _support  # noqa: E402

_support.bootstrap()

from util.config import config_loader  # noqa: E402
from util.fetch import weibo_parse  # noqa: E402
from util.http import http_client, rate_limit, risk_guard  # noqa: E402
from util.storage import csv_json  # noqa: E402

EDGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36 Edg/136.0.0.0"
)
FIREFOX_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0"
ANDROID_UA = (
    "Mozilla/5.0 (Linux; Android 14; SM-S9180) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.6367.113 Mobile Safari/537.36"
)


class _Obj:
    pass


class PaceTest(unittest.TestCase):
    def test_elapsed_time_counts_toward_interval(self):
        wb = _Obj()
        wb._last_request_ts = time.time() - 6
        sleeps = []
        rate_limit.pace(wb, 10, sleeps.append)
        self.assertEqual(len(sleeps), 1)
        self.assertLess(sleeps[0], 4.5)
        self.assertGreater(sleeps[0], 3.5)

    def test_no_sleep_when_interval_already_passed(self):
        wb = _Obj()
        wb._last_request_ts = time.time() - 30
        sleeps = []
        self.assertEqual(rate_limit.pace(wb, 10, sleeps.append), 0.0)
        self.assertEqual(sleeps, [])
        self.assertAlmostEqual(wb._last_request_ts, time.time(), delta=1)

    def test_comment_delay_floor_when_anti_ban_enabled(self):
        wb = _Obj()
        wb.comment_request_delay_min = 1
        wb.comment_request_delay_max = 2
        wb.anti_ban_enabled = True
        wb.anti_ban_config = {"comment_delay_min": 3, "comment_delay_max": 6}
        self.assertEqual(rate_limit.comment_delay_range(wb), (3, 6))
        wb.anti_ban_enabled = False
        self.assertEqual(rate_limit.comment_delay_range(wb), (1, 2))


class RiskGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "risk_state.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_trip_doubles_and_caps(self):
        now = 1_000_000.0
        first = risk_guard.trip("r", 60, 150, path=self.path, now=now)
        second = risk_guard.trip("r", 60, 150, path=self.path, now=now + 10)
        third = risk_guard.trip("r", 60, 150, path=self.path, now=now + 20)
        self.assertEqual(
            [first["cooldown_minutes"], second["cooldown_minutes"], third["cooldown_minutes"]],
            [60, 120, 150],
        )

    def test_streak_resets_after_a_day(self):
        now = 1_000_000.0
        risk_guard.trip("r", 60, 360, path=self.path, now=now)
        later = risk_guard.trip("r", 60, 360, path=self.path, now=now + 2 * 24 * 3600)
        self.assertEqual(later["streak"], 1)

    def test_active_and_clear(self):
        now = time.time()
        risk_guard.trip("HTML 风控", 60, 360, path=self.path, now=now)
        state = risk_guard.active_cooldown(self.path, now=now + 60)
        self.assertIsNotNone(state)
        self.assertGreater(state["remaining_seconds"], 3000)
        self.assertIsNone(risk_guard.active_cooldown(self.path, now=now + 3601))
        self.assertTrue(risk_guard.clear(self.path))
        self.assertIsNone(risk_guard.active_cooldown(self.path, now=now))


class HeaderConsistencyTest(unittest.TestCase):
    def test_edge_hints_match_ua(self):
        hints = http_client.client_hints(EDGE_UA)
        self.assertIn('"Microsoft Edge";v="136"', hints["sec-ch-ua"])
        self.assertEqual(hints["sec-ch-ua-platform"], '"Windows"')
        self.assertEqual(hints["sec-ch-ua-mobile"], "?0")

    def test_firefox_sends_no_hints(self):
        headers = http_client.random_headers(True, {}, {}, user_agent=FIREFOX_UA)
        self.assertFalse(any(k.startswith("sec-ch-ua") for k in headers))

    def test_android_is_mobile(self):
        hints = http_client.client_hints(ANDROID_UA)
        self.assertEqual(hints["sec-ch-ua-mobile"], "?1")
        self.assertEqual(hints["sec-ch-ua-platform"], '"Android"')

    def test_profile_referer_and_xsrf(self):
        headers = http_client.random_headers(
            True,
            {},
            {},
            user_agent=EDGE_UA,
            referer=http_client.profile_referer("123"),
            xsrf_token="tok",
        )
        self.assertEqual(headers["Referer"], "https://m.weibo.cn/u/123")
        self.assertEqual(headers["x-xsrf-token"], "tok")
        self.assertEqual(headers["mweibo-pwa"], "1")

    def test_apply_user_agent_replaces_stale_hints(self):
        headers = {"sec-ch-ua": "old", "sec-ch-ua-platform": '"Windows"', "user-agent": "x"}
        http_client.apply_user_agent(headers, FIREFOX_UA)
        self.assertEqual(headers, {"user-agent": FIREFOX_UA})


class CrawlStatsTest(unittest.TestCase):
    def _wb(self):
        wb = _Obj()
        wb.anti_ban_enabled = True
        wb.anti_ban_config = {"request_delay_min": 8, "request_delay_max": 15}
        wb.crawl_stats = {
            "weibo_count": 0,
            "request_count": 400,
            "api_errors": 3,
            "start_time": time.time() - 600,
            "batch_count": 0,
            "last_batch_time": None,
        }
        return wb

    def test_success_resets_consecutive_errors(self):
        wb = self._wb()
        config_loader.update_crawl_stats(wb, request_count=1)
        self.assertEqual(wb.crawl_stats["api_errors"], 0)

    def test_dynamic_delay_never_exceeds_max(self):
        wb = self._wb()
        for _ in range(50):
            self.assertLessEqual(config_loader.calculate_dynamic_delay(wb), 15)


class SkipLongTextTest(unittest.TestCase):
    def _wb(self, item, write_mode=("markdown",)):
        wb = _Obj()
        wb.write_mode = list(write_mode)
        state = {"weibos": {"1": item}} if item is not None else {"weibos": {}}
        wb._ensure_archive_state = lambda: state
        return wb

    def _item(self, **extra):
        item = {"content_hash": "h", "md_path": "2024/a.md", "status": "active", "edit_count": 0}
        item.update(extra)
        return item

    def test_skip_when_archived_and_unedited(self):
        self.assertTrue(weibo_parse.can_skip_long_text(self._wb(self._item()), "1", {"edit_count": 0}))

    def test_fetch_when_edit_count_changed(self):
        self.assertFalse(weibo_parse.can_skip_long_text(self._wb(self._item()), "1", {"edit_count": 1}))

    def test_fetch_when_legacy_state_without_edit_count(self):
        item = self._item()
        del item["edit_count"]
        self.assertFalse(weibo_parse.can_skip_long_text(self._wb(item), "1", {"edit_count": 0}))

    def test_fetch_when_previous_long_text_incomplete(self):
        item = self._item(long_text_incomplete=True)
        self.assertFalse(weibo_parse.can_skip_long_text(self._wb(item), "1", {"edit_count": 0}))

    def test_fetch_when_overwriting_backend_enabled(self):
        wb = self._wb(self._item(), write_mode=("markdown", "mysql"))
        self.assertFalse(weibo_parse.can_skip_long_text(wb, "1", {"edit_count": 0}))

    def test_get_one_weibo_skips_detail_request(self):
        wb = self._wb(self._item())
        wb.get_long_weibo = mock.Mock()
        wb.parse_weibo = lambda info: {"id": info["id"], "text": "截断"}
        wb.standardize_date = lambda value: (value, value)
        info = {
            "mblog": {
                "id": "1",
                "isLongText": True,
                "pic_num": 0,
                "created_at": "2024-01-01 00:00:00",
                "edit_count": 0,
            }
        }
        weibo = weibo_parse.get_one_weibo(wb, info)
        wb.get_long_weibo.assert_not_called()
        self.assertTrue(weibo["long_text_skipped"])


class KeepArchivedTextTest(unittest.TestCase):
    def test_json_keeps_full_text_for_skipped_long_weibo(self):
        wb = _Obj()
        wb.user = {"id": "u"}
        data = {"weibo": [{"id": "1", "text": "完整全文", "retweet": {"text": "原微博全文"}}]}
        new = {
            "id": "1",
            "text": "截断",
            "attitudes_count": 9,
            "long_text_skipped": True,
            "retweet": {"text": "截断原文", "id": "2"},
        }
        merged = csv_json.update_json_data(wb, data, [new])["weibo"][0]
        self.assertEqual(merged["text"], "完整全文")
        self.assertEqual(merged["retweet"]["text"], "原微博全文")
        self.assertEqual(merged["attitudes_count"], 9)


class GuestCookieSaveTest(unittest.TestCase):
    def _extract(self, current_cookie, personal_login):
        from util import browser_cookie

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config_path = os.path.join(tmp.name, "config.json")
        with mock.patch.object(
            browser_cookie, "extract_browser_cookies",
            return_value=("tid=x; SUB=_2AkMguest", None, "Microsoft Edge"),
        ), mock.patch.object(
            browser_cookie, "verify_cookie_string",
            return_value={"valid": True, "personal_login": personal_login, "user": {}},
        ), mock.patch.object(
            browser_cookie, "_read_parsed_config", return_value={"cookie": current_cookie},
        ), mock.patch.object(browser_cookie, "CONFIG_PATH", config_path):
            result = browser_cookie.extract_and_save_cookie()
        return result, os.path.exists(config_path)

    def test_guest_cookie_does_not_overwrite_existing(self):
        result, written = self._extract("SUB=old_login", personal_login=False)
        self.assertFalse(written)
        self.assertFalse(result["saved"])
        self.assertFalse(result["success"])
        self.assertIn("游客", result["message"])

    def test_logged_in_cookie_is_saved(self):
        result, written = self._extract("SUB=old_login", personal_login=True)
        self.assertTrue(written)
        self.assertTrue(result["saved"])


class _JsonResp:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class VerifyCookieTest(unittest.TestCase):
    def _verify(self, mobile_payload):
        from util import browser_cookie

        def fake_get(url, **kwargs):
            if "m.weibo.cn/api/config" in url:
                if isinstance(mobile_payload, Exception):
                    raise mobile_payload
                return _JsonResp(mobile_payload)
            # weibo.com 接口对游客 Cookie 同样返回 ok=1
            return _JsonResp({"ok": 1, "data": {"verified_url": "uid=123"}})

        with mock.patch.object(browser_cookie.requests, "get", side_effect=fake_get):
            return browser_cookie.verify_cookie_string("tid=x; SUB=_2AkMguest")

    def test_guest_not_reported_as_logged_in(self):
        result = self._verify({"data": {"login": False}})
        self.assertTrue(result["valid"])
        self.assertFalse(result["personal_login"])
        self.assertIn("游客", result["message"])

    def test_mobile_login_is_authoritative(self):
        result = self._verify(
            {"data": {"login": True, "uid": "9", "user": {"screen_name": "me"}}}
        )
        self.assertTrue(result["personal_login"])
        self.assertEqual(result["user"]["id"], "9")

    def test_pc_probe_used_only_when_mobile_unreachable(self):
        result = self._verify(RuntimeError("timeout"))
        self.assertTrue(result["personal_login"])


if __name__ == "__main__":
    unittest.main()
