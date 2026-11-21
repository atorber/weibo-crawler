"""分页抓取落库节奏：每页有新微博时立刻 write_data。"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta
from unittest import mock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tests import _support  # noqa: E402

_support.bootstrap()

from util.core.time_format import DTFORMAT  # noqa: E402
from util.fetch import fetch_pages  # noqa: E402


class _FakeBar:
    def update(self, n=1):
        pass

    def close(self):
        pass


def _fake_tqdm(iterable=None, **kwargs):
    """兼容旧式 tqdm(iterable) 与新式 tqdm(total=N)。"""
    if iterable is None:
        return _FakeBar()
    return iterable


class ImmediateWriteTest(unittest.TestCase):
    def test_writes_after_each_page_with_new_weibos(self):
        writes = []

        class WB:
            write_mode = ["sqlite"]
            anti_ban_enabled = False
            anti_ban_config = {}
            start_page = 1
            got_count = 0
            user = {"screen_name": "u", "id": "1"}
            user_config = {
                "since_date": (datetime.now() - timedelta(days=30)).strftime(DTFORMAT),
                "end_date": "",
            }
            crawl_success = {}
            crawl_stats = {
                "weibo_count": 0,
                "request_count": 0,
                "api_errors": 0,
                "start_time": None,
            }

            def get_user_info(self):
                return 0

            def get_page_count(self):
                return 3

            def _snapshot_archived_ids(self):
                pass

            def _finalize_crawl_success(self, last_page, page_count):
                self.crawl_success["success"] = True

            def write_data(self, wrote_count):
                writes.append((wrote_count, self.got_count))

            def get_one_page(self, page):
                # 每页新增 2 条
                self.got_count += 2
                if page >= 3:
                    return True
                return None

        with mock.patch.object(fetch_pages, "tqdm", _fake_tqdm), mock.patch.object(
            fetch_pages, "sleep"
        ):
            fetch_pages.get_pages(WB())

        # 第 1、2 页各写一次；第 3 页 is_end 前也已写入
        self.assertEqual(writes, [(0, 2), (2, 4), (4, 6)])

    def test_skips_write_when_page_adds_nothing(self):
        writes = []

        class WB:
            write_mode = ["sqlite"]
            anti_ban_enabled = False
            anti_ban_config = {}
            start_page = 1
            got_count = 0
            user = {"screen_name": "u", "id": "1"}
            user_config = {
                "since_date": (datetime.now() - timedelta(days=30)).strftime(DTFORMAT),
                "end_date": "",
            }
            crawl_success = {}
            crawl_stats = {
                "weibo_count": 0,
                "request_count": 0,
                "api_errors": 0,
                "start_time": None,
            }

            def get_user_info(self):
                return 0

            def get_page_count(self):
                return 2

            def _snapshot_archived_ids(self):
                pass

            def _finalize_crawl_success(self, last_page, page_count):
                pass

            def write_data(self, wrote_count):
                writes.append(wrote_count)

            def get_one_page(self, page):
                if page == 1:
                    self.got_count += 1
                    return None
                return True  # 第 2 页无新增并结束

        with mock.patch.object(fetch_pages, "tqdm", _fake_tqdm), mock.patch.object(
            fetch_pages, "sleep"
        ):
            fetch_pages.get_pages(WB())

        self.assertEqual(writes, [0])


def _loop_wb(page_results, *, is_guest=False, page_count=5):
    """分页循环用的最小 WB：get_one_page 依次返回 page_results（按调用次序）。"""

    class WB:
        write_mode = ["sqlite"]
        anti_ban_enabled = False
        anti_ban_config = {"html_risk_page_retries": 2, "html_risk_cooldown": 1}
        start_page = 1
        got_count = 0
        user = {"screen_name": "u", "id": "1"}
        user_config = {
            "since_date": (datetime.now() - timedelta(days=30)).strftime(DTFORMAT),
            "end_date": "",
        }
        crawl_success = {}
        crawl_stats = {"weibo_count": 0, "request_count": 0, "api_errors": 0, "start_time": None}

        def __init__(self):
            self.is_guest = is_guest
            self.risk_tripped = False
            self.pages_called = []
            self._results = list(page_results)

        def get_user_info(self):
            return 0

        def get_page_count(self):
            return page_count

        def _snapshot_archived_ids(self):
            pass

        def _finalize_crawl_success(self, last_page, page_count):
            self.crawl_success.setdefault("reason", "提前结束")

        def write_data(self, wrote_count):
            pass

        def get_one_page(self, page):
            self.pages_called.append(page)
            return self._results.pop(0) if self._results else True

    return WB()


class PageLoopRiskTest(unittest.TestCase):
    def _run(self, wb):
        sleeps = []
        with mock.patch.object(fetch_pages, "tqdm", _fake_tqdm), mock.patch.object(
            fetch_pages, "sleep", side_effect=sleeps.append
        ):
            fetch_pages.get_pages(wb)
        return sleeps

    def test_html_risk_cools_down_then_stops_run(self):
        risk = fetch_pages.HTML_RISK
        wb = _loop_wb([None, risk, risk, risk])
        self._run(wb)

        # 第 2 页：首次 + 2 次冷却重试，仍失败即结束，不再翻第 3 页
        self.assertEqual(wb.pages_called, [1, 2, 2, 2])
        self.assertTrue(wb.risk_tripped)
        self.assertIn("风控", wb.crawl_success["reason"])

    def test_html_risk_recovers_after_cooldown(self):
        risk = fetch_pages.HTML_RISK
        wb = _loop_wb([None, risk, None, True])
        self._run(wb)

        self.assertEqual(wb.pages_called, [1, 2, 2, 3])
        self.assertFalse(wb.risk_tripped)

    def test_guest_only_crawls_first_page(self):
        wb = _loop_wb([None, None, None], is_guest=True)
        self._run(wb)

        self.assertEqual(wb.pages_called, [1])
        self.assertIn("游客", wb.crawl_success["reason"])


if __name__ == "__main__":
    unittest.main()
