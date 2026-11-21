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


class ImmediateWriteTest(unittest.TestCase):
    def test_writes_after_each_page_with_new_weibos(self):
        writes = []

        class WB:
            write_mode = ["sqlite"]
            anti_ban_enabled = False
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

        with mock.patch.object(fetch_pages, "tqdm", lambda x, **kw: x), mock.patch.object(
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

        with mock.patch.object(fetch_pages, "tqdm", lambda x, **kw: x), mock.patch.object(
            fetch_pages, "sleep"
        ):
            fetch_pages.get_pages(WB())

        self.assertEqual(writes, [0])


if __name__ == "__main__":
    unittest.main()
