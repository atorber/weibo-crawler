"""service 用户列表路径 / 读写源一致性测试。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tests import _support  # noqa: E402

_support.bootstrap()

service = _support.import_service_isolated()


@unittest.skipIf(service is None, "Flask / service 不可用")
class UserIdFilePathTest(unittest.TestCase):
    def test_file_mode_resolves_configured_txt(self):
        with mock.patch.object(
            service,
            "read_raw_config",
            return_value=("{}", {"user_id_list": "config/user_id_list.txt"}, True),
        ):
            path = service.get_user_id_file_path()
        self.assertEqual(
            path,
            service.config_paths.resolve_config_file(
                service.BASE_DIR, "config/user_id_list.txt"
            ),
        )

    def test_array_mode_returns_canonical_txt_path(self):
        with mock.patch.object(
            service,
            "read_raw_config",
            return_value=("{}", {"user_id_list": ["111", "222"]}, True),
        ):
            path = service.get_user_id_file_path()
        self.assertEqual(
            path,
            service.config_paths.resolve_config_file(
                service.BASE_DIR, "config/user_id_list.txt"
            ),
        )


@unittest.skipIf(service is None, "Flask / service 不可用")
class UserTargetsSourceTest(unittest.TestCase):
    def test_array_mode_ignores_stale_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "user_id_list.txt"
            stale.write_text("999 stale_user\n", encoding="utf-8")
            with mock.patch.object(
                service,
                "read_raw_config",
                return_value=("{}", {"user_id_list": ["111", "222"]}, True),
            ), mock.patch.object(
                service, "get_user_id_file_path", return_value=str(stale)
            ):
                users = service.get_user_targets()
        self.assertEqual([u["id"] for u in users], ["111", "222"])

    def test_save_array_mode_writes_config_not_txt(self):
        saved = {}

        def fake_save(content_str):
            saved["parsed"] = json.loads(content_str)
            return saved["parsed"]

        with mock.patch.object(
            service,
            "read_raw_config",
            return_value=("{}", {"user_id_list": ["111"], "cookie": "x"}, True),
        ), mock.patch.object(service, "save_config_content", side_effect=fake_save):
            service.save_user_targets(
                [{"id": "333", "screen_name": "n"}, {"id": "444"}]
            )
        self.assertEqual(saved["parsed"]["user_id_list"], ["333", "444"])
        self.assertEqual(saved["parsed"]["cookie"], "x")


@unittest.skipIf(service is None, "Flask / service 不可用")
class ProcessControllerStartUsersTest(unittest.TestCase):
    def test_start_passes_users_to_cmd_and_env(self):
        ctrl = service.ProcessController()
        captured = {}

        class _FakeProc:
            pid = 4242

        def fake_popen(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = kwargs.get("env") or {}
            return _FakeProc()

        with mock.patch.object(ctrl, "is_running", return_value=False), mock.patch.object(
            service.subprocess, "Popen", side_effect=fake_popen
        ), mock.patch.object(
            service, "read_raw_config", return_value=("{}", {}, True)
        ), mock.patch.object(
            service, "get_cookie_auto_config", return_value={"enabled": False}
        ):
            ok, msg = ctrl.start(["1669879400", "123"])
        self.assertTrue(ok)
        self.assertIn("--users", captured["cmd"])
        self.assertEqual(
            captured["cmd"][captured["cmd"].index("--users") + 1 :],
            ["1669879400", "123"],
        )
        self.assertEqual(
            captured["env"].get("WEIBO_USER_ID_LIST"), "1669879400,123"
        )
        self.assertIn("4242", msg)


class ResolveUserOverrideTest(unittest.TestCase):
    def test_cli_beats_env(self):
        import weibo

        with mock.patch.dict(os.environ, {"WEIBO_USER_ID_LIST": "1,2"}, clear=False):
            self.assertEqual(
                weibo._resolve_user_id_list_override(["9"]),
                ["9"],
            )

    def test_env_split(self):
        import weibo

        with mock.patch.dict(
            os.environ, {"WEIBO_USER_ID_LIST": "11, 22 33"}, clear=False
        ):
            self.assertEqual(
                weibo._resolve_user_id_list_override(None),
                ["11", "22", "33"],
            )

    def test_none_when_empty(self):
        import weibo

        env = {k: v for k, v in os.environ.items() if k != "WEIBO_USER_ID_LIST"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertIsNone(weibo._resolve_user_id_list_override(None))


if __name__ == "__main__":
    unittest.main()
