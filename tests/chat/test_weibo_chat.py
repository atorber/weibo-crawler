# -*- coding: utf-8 -*-

import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from tests import _support

_support.bootstrap()

from util.chat import WeiboChatClient, is_group_id  # noqa: E402


def _import_service_isolated():
    if "service" in sys.modules:
        return sys.modules["service"]
    tests_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    saved_path = list(sys.path)
    saved_http = sys.modules.get("http")
    try:
        sys.path[:] = [
            p for p in sys.path if os.path.abspath(p or ".") != tests_dir
        ]
        if saved_http is not None and tests_dir in os.path.abspath(
            getattr(saved_http, "__file__", "") or ""
        ):
            sys.modules.pop("http", None)
        import importlib
        import http.client  # noqa: F401
        import http.server  # noqa: F401
        return importlib.import_module("service")
    except Exception:
        return None
    finally:
        sys.path[:] = saved_path
        if saved_http is not None:
            sys.modules["http"] = saved_http
        else:
            sys.modules.pop("http", None)


service = _import_service_isolated()


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, handler):
        self._handler = handler
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self._handler(method, url, **kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


class WeiboChatClientUnitTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="weibo-chat-test-")
        os.makedirs(os.path.join(self.tmpdir, "config"), exist_ok=True)
        with open(
            os.path.join(self.tmpdir, "config", "config.json"), "w", encoding="utf-8"
        ) as f:
            json.dump({"cookie": "SUB=test_chat_sub; SUBP=test_subp"}, f)

    def tearDown(self):
        _support.remove_tree(self.tmpdir)

    def test_is_group_id_helper(self):
        self.assertFalse(is_group_id("1669879400"))
        self.assertTrue(is_group_id("4912345678901234"))

    def test_check_auth_contacts_and_search(self):
        def _handler(method, url, **kw):
            if "query_primary_info.json" in url:
                return _FakeResponse(
                    {
                        "profile": {
                            "id": 1863732524,
                            "screen_name": "测试博主",
                            "profileImageUrl": "https://tvax1.sinaimg.cn/a.jpg",
                        }
                    }
                )
            if "direct_messages/contacts.json" in url:
                return _FakeResponse(
                    {
                        "contacts": [
                            {
                                "unread_count": 2,
                                "user": {
                                    "id": 1669879400,
                                    "screen_name": "好友A",
                                    "type": 1,
                                    "profile_image_url": "https://tvax1.sinaimg.cn/u1.jpg",
                                },
                                "message": {
                                    "id": 53670001,
                                    "text": "最近好吗",
                                    "created_at": "2026-11-19 20:00:00",
                                },
                            },
                            {
                                "unread_count": 0,
                                "user": {
                                    "id": 4912345678901234,
                                    "name": "测试粉丝群",
                                    "type": 2,
                                },
                                "message": {"id": 53670002, "text": "欢迎入群"},
                            },
                        ],
                        "next_cursor": 0,
                        "totalNumber": 2,
                    }
                )
            if "messageboxsearch.json" in url:
                return _FakeResponse(
                    {
                        "result": {
                            "contacts": {
                                "users": [
                                    {"id": 1669879400, "screen_name": "好友A", "type": 1}
                                ]
                            },
                            "groups": {
                                "groups": [
                                    {"id": 4912345678901234, "name": "测试粉丝群"}
                                ]
                            },
                        }
                    }
                )
            return _FakeResponse({"ok": 1})

        sess = _FakeSession(_handler)
        client = WeiboChatClient(
            project_root=self.tmpdir, session=sess, auto_refresh=False
        )

        auth = client.check_auth()
        self.assertTrue(auth["authenticated"])
        self.assertEqual(auth["uid"], "1863732524")
        self.assertEqual(auth["screen_name"], "测试博主")

        contacts = client.list_contacts(count=20)
        self.assertTrue(contacts["ok"])
        self.assertEqual(len(contacts["contacts"]), 2)
        self.assertFalse(contacts["contacts"][0]["is_group"])
        self.assertTrue(contacts["contacts"][1]["is_group"])

        searched = client.search_contacts("测试")
        self.assertTrue(searched["ok"])
        self.assertEqual(len(searched["contacts"]), 2)

    def test_messages_send_upload_recall_delete_and_read(self):
        def _handler(method, url, **kw):
            if "direct_messages/conversation.json" in url:
                return _FakeResponse(
                    {
                        "direct_messages": [
                            {
                                "id": 5367111,
                                "text": "单聊消息",
                                "sender_id": 1669879400,
                                "sender_screen_name": "好友A",
                                "recipient_id": 1863732524,
                                "created_at": "2026-11-19 21:00:00",
                            }
                        ],
                        "total_number": 1,
                    }
                )
            if "groupchat/query_messages.json" in url:
                return _FakeResponse(
                    {
                        "messages": [
                            {
                                "id": 5367222,
                                "content": "群聊消息",
                                "from_uid": 1669879400,
                                "sender_info": {"screen_name": "群友B"},
                                "time": 1763557200,
                            }
                        ]
                    }
                )
            if "fileplatform/init.json" in url:
                return _FakeResponse(
                    {"fileToken": "tok_file_1", "length": 1048576, "selectId": "sel_1"}
                )
            if "uploadx.json" in url:
                return _FakeResponse({"fid": "fid_998877"})
            if "direct_messages/new.json" in url:
                return _FakeResponse(
                    {"id": 5367333, "text": "已发送私信", "created_at": "now"}
                )
            if "groupchat/send_message.json" in url:
                return _FakeResponse(
                    {"mid": 5367444, "content": "已发送群消息"}
                )
            if "direct_messages/recall.json" in url or "groupchat/recall.json" in url:
                return _FakeResponse({"id": 5367333, "result": True})
            if (
                "direct_messages/destroy" in url
                or "groupchat/delete_message.json" in url
            ):
                return _FakeResponse({"result": True})
            if (
                "set_unread_count.json" in url
                or "reset_unread_count.json" in url
                or "groupchat/clear_unread.json" in url
            ):
                return _FakeResponse({"result": True})
            return _FakeResponse({"result": True})

        sess = _FakeSession(_handler)
        client = WeiboChatClient(
            project_root=self.tmpdir, session=sess, auto_refresh=False
        )

        # 1. Fetch 1-on-1 & group messages
        conv = client.get_conversation(uid="1669879400")
        self.assertTrue(conv["ok"])
        self.assertEqual(conv["messages"][0]["mid"], "5367111")

        gconv = client.get_group_messages(gid="4912345678901234")
        self.assertTrue(gconv["ok"])
        self.assertEqual(gconv["messages"][0]["mid"], "5367222")

        # 2. Dry-run send
        dry = client.send_message(uid="1669879400", text="干跑测试", dry_run=True)
        self.assertTrue(dry["ok"])
        self.assertTrue(dry["dry_run"])

        # 3. Send 1-on-1 message with attachment upload
        sent = client.send_message(
            uid="1669879400",
            text="带图私信",
            file_bytes=b"\x89PNG\r\n\x1a\nFAKE_PNG",
            filename="test.png",
        )
        self.assertTrue(sent["ok"])
        self.assertEqual(sent["mid"], "5367333")
        self.assertEqual(sent["fid"], "fid_998877")

        # 4. Send group message
        gsent = client.send_message(gid="4912345678901234", text="大家好", at_all=True)
        self.assertTrue(gsent["ok"])
        self.assertEqual(gsent["mid"], "5367444")

        # 5. Recall, delete, and mark read
        self.assertTrue(client.recall_message(mid="5367333")["ok"])
        self.assertTrue(
            client.recall_message(mid="5367444", gid="4912345678901234")["ok"]
        )
        self.assertTrue(client.delete_message(mid="5367333")["ok"])
        self.assertTrue(client.delete_message(uid="1669879400")["ok"])
        self.assertTrue(
            client.delete_message(gid="4912345678901234", mid="5367444")["ok"]
        )
        self.assertTrue(client.mark_read(uid="1669879400")["ok"])
        self.assertTrue(client.mark_read(gid="4912345678901234")["ok"])
        self.assertTrue(client.mark_read(unfollow=True)["ok"])

        # 6. Verify all calls were routed through Mode 1 pass-through trace + raw_request
        self.assertEqual(client.transport, "in-process")
        self.assertGreaterEqual(len(client.trace), 10)
        self.assertTrue(all(t["path"].startswith("/webim/") for t in client.trace))
        raw_res = client.raw_request("GET", "2/direct_messages/conversation.json", params={"uid": "1669879400"})
        self.assertTrue(raw_res["ok"])
        self.assertEqual(raw_res["path"], "/webim/2/direct_messages/conversation.json")

    def test_http_passthrough_transport_mode(self):
        def _http_handler(method, url, **kw):
            if url.endswith("/webim/query_primary_info.json"):
                resp = _FakeResponse(
                    {"profile": {"id": 1863732524, "screen_name": "HTTP透传测试"}}
                )
                resp.headers = {
                    "X-Weibo-Passthrough-Upstream": "https://api.weibo.com/webim/query_primary_info.json"
                }
                return resp
            return _FakeResponse({"result": True})

        http_sess = _FakeSession(_http_handler)
        client = WeiboChatClient(
            project_root=self.tmpdir,
            session=http_sess,
            passthrough_base_url="http://127.0.0.1:15001",
            auto_refresh=False,
        )
        self.assertEqual(client.transport, "http")
        auth = client.check_auth()
        self.assertTrue(auth["authenticated"])
        self.assertEqual(auth["screen_name"], "HTTP透传测试")
        self.assertEqual(
            http_sess.calls[0][1],
            "http://127.0.0.1:15001/webim/query_primary_info.json",
        )
        self.assertEqual(client.trace[-1]["transport"], "http")
        self.assertEqual(client.trace[-1]["path"], "/webim/query_primary_info.json")


@unittest.skipIf(service is None, "Flask is not installed")
class ServiceChatApiIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.client = service.app.test_client()

    def test_chat_api_endpoints_and_html_route(self):
        # /chat HTML route renders console page
        r_html = self.client.get("/chat")
        self.assertEqual(r_html.status_code, 200)
        self.assertIn("私信管理".encode("utf-8"), r_html.data)

        fake_chat = mock.MagicMock()
        fake_chat.check_auth.return_value = {
            "authenticated": True,
            "uid": "1863732524",
            "screen_name": "测试号",
            "message": "ok",
        }
        fake_chat.list_contacts.return_value = {
            "ok": True,
            "contacts": [{"id": "1669879400", "name": "好友A", "is_group": False}],
            "message": "ok",
        }
        fake_chat.get_conversation.return_value = {
            "ok": True,
            "messages": [{"mid": "5367111", "text": "hello"}],
            "message": "ok",
        }
        fake_chat.send_message.return_value = {
            "ok": True,
            "mid": "5367999",
            "message": "私信发送成功",
        }
        fake_chat.recall_message.return_value = {"ok": True, "message": "消息已撤回"}
        fake_chat.delete_message.return_value = {"ok": True, "message": "已删除"}
        fake_chat.mark_read.return_value = {"ok": True, "message": "已标记为已读"}

        with mock.patch.object(service, "WeiboChatClient", return_value=fake_chat):
            r_st = self.client.get("/api/chat/status")
            self.assertEqual(r_st.status_code, 200)
            self.assertTrue(json.loads(r_st.data)["data"]["authenticated"])

            r_ct = self.client.get("/api/chat/contacts?count=10")
            self.assertEqual(r_ct.status_code, 200)
            self.assertEqual(
                json.loads(r_ct.data)["data"]["contacts"][0]["id"], "1669879400"
            )

            r_msg = self.client.get("/api/chat/messages?uid=1669879400")
            self.assertEqual(r_msg.status_code, 200)
            self.assertEqual(
                json.loads(r_msg.data)["data"]["messages"][0]["mid"], "5367111"
            )

            r_send = self.client.post(
                "/api/chat/send", json={"uid": "1669879400", "text": "你好"}
            )
            self.assertEqual(r_send.status_code, 200)
            self.assertEqual(json.loads(r_send.data)["data"]["mid"], "5367999")

            r_send_mp = self.client.post(
                "/api/chat/send",
                data={
                    "uid": "1669879400",
                    "text": "图片",
                    "file": (io.BytesIO(b"IMG"), "a.png"),
                },
                content_type="multipart/form-data",
            )
            self.assertEqual(r_send_mp.status_code, 200)

            r_rec = self.client.post("/api/chat/recall", json={"mid": "5367999"})
            self.assertEqual(r_rec.status_code, 200)

            r_del = self.client.post("/api/chat/delete", json={"mid": "5367999"})
            self.assertEqual(r_del.status_code, 200)

            r_read = self.client.post("/api/chat/read", json={"uid": "1669879400"})
            self.assertEqual(r_read.status_code, 200)

        # End-to-end: /api/chat/* shares service.passthrough_proxy (Mode 1 /webim/* proxy)
        from util.passthrough import WeiboPassthroughProxy

        def _e2e_handler(method, url, **kw):
            if "query_primary_info.json" in url:
                return _FakeResponse(
                    {"profile": {"id": 1863732524, "screen_name": "透传共享账号"}}
                )
            return _FakeResponse({"result": True})

        tmpdir = tempfile.mkdtemp(prefix="weibo-chat-e2e-")
        try:
            os.makedirs(os.path.join(tmpdir, "config"), exist_ok=True)
            with open(
                os.path.join(tmpdir, "config", "config.json"), "w", encoding="utf-8"
            ) as f:
                json.dump({"cookie": "SUB=e2e_sub"}, f)
            e2e_proxy = WeiboPassthroughProxy(
                project_root=tmpdir,
                session=_FakeSession(_e2e_handler),
                auto_refresh=False,
            )
            with mock.patch.object(service, "passthrough_proxy", e2e_proxy):
                r_e2e = self.client.get("/api/chat/status")
                self.assertEqual(r_e2e.status_code, 200)
                body = json.loads(r_e2e.data)
                self.assertTrue(body["data"]["authenticated"])
                self.assertEqual(body["data"]["screen_name"], "透传共享账号")
                self.assertEqual(
                    body["passthrough"][0]["path"], "/webim/query_primary_info.json"
                )
        finally:
            _support.remove_tree(tmpdir)


if __name__ == "__main__":
    unittest.main()
