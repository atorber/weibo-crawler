"""Tests for WeiboPublisher, browser cookie domain priority, and weibo_ctl publish CLI."""

from collections.abc import MutableMapping
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests import _support  # noqa: E402

_support.bootstrap()

from util import browser_cookie  # noqa: E402
from util.publish import weibo_publisher  # noqa: E402
from util.publish.weibo_publisher import (  # noqa: E402
    MAX_IMAGES,
    WeiboPublisher,
    is_allowed_weibo_image_url,
    normalize_weibo_image_url,
    parse_schedule_timestamp,
)


class _FakeCookieJar:
    def __init__(self):
        self._items = {}

    def set(self, name, value, **kwargs):
        self._items[name] = value

    def clear(self):
        self._items.clear()

    def __iter__(self):
        return iter(types.SimpleNamespace(name=k, value=v) for k, v in self._items.items())


class _FakeResponse:
    def __init__(self, payload, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeSession:
    def __init__(self, get_handlers=None, post_handlers=None):
        self.headers = {}
        self.cookies = _FakeCookieJar()
        self.get_handlers = get_handlers or {}
        self.post_handlers = post_handlers or {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        for key, fn in self.get_handlers.items():
            if key in url:
                return fn(url, self, **kwargs)
        return _FakeResponse({"ok": 1, "data": {}})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        for key, fn in self.post_handlers.items():
            if key in url:
                return fn(url, self, **kwargs)
        return _FakeResponse({"ok": 1, "data": {}})


def _auth_get_handlers(uid="1863732524", screen_name="测试账号", xsrf="xsrf_fresh"):
    def _cfg(url, sess, **kwargs):
        sess.cookies.set("XSRF-TOKEN", xsrf, domain=".weibo.com", path="/")
        return _FakeResponse({"ok": 1, "data": {}})

    def _detail(url, sess, **kwargs):
        return _FakeResponse(
            {"ok": 1, "data": {"verified_url": f"https://verified.weibo.com/?uid={uid}"}}
        )

    def _info(url, sess, **kwargs):
        return _FakeResponse({"ok": 1, "data": {"user": {"screen_name": screen_name}}})

    return {
        "/ajax/statuses/config": _cfg,
        "/ajax/profile/detail": _detail,
        "/ajax/profile/info": _info,
    }


class WeiboPublisherTest(unittest.TestCase):
    def test_ensure_session_refreshes_xsrf_and_extracts_uid_name(self):
        sess = _FakeSession(get_handlers=_auth_get_handlers(uid="998877", screen_name="测试博"))
        pub = WeiboPublisher(cookie="SUB=abc; XSRF-TOKEN=old_tok", session=sess, auto_refresh=False)
        res = pub.ensure_session()

        self.assertTrue(res["ok"])
        self.assertTrue(res["logged_in"])
        self.assertEqual(res["uid"], "998877")
        self.assertEqual(res["screen_name"], "测试博")
        self.assertEqual(sess.headers.get("X-XSRF-TOKEN"), "xsrf_fresh")

    def test_ensure_session_auto_refresh_retries_with_weibo_com_domain(self):
        attempts = {"detail": 0}

        def _detail(url, sess, **kwargs):
            attempts["detail"] += 1
            if attempts["detail"] == 1:
                return _FakeResponse({"ok": -100, "msg": "expired"})
            return _FakeResponse(
                {"ok": 1, "data": {"verified_url": "https://verified.weibo.com/?uid=112233"}}
            )

        handlers = _auth_get_handlers()
        handlers["/ajax/profile/detail"] = _detail
        sess = _FakeSession(get_handlers=handlers)
        pub = WeiboPublisher(cookie="SUB=stale", session=sess, auto_refresh=True)

        with mock.patch.object(
            weibo_publisher, "get_cookie_auto_config", return_value={"enabled": True, "refresh_on_expire": True, "browser": "chrome"}
        ), mock.patch.object(
            weibo_publisher,
            "extract_and_save_cookie",
            return_value={"success": True, "valid": True, "cookie": "SUB=fresh_sub; XSRF-TOKEN=tok2"},
        ) as mock_extract:
            res = pub.ensure_session()

        self.assertTrue(res["ok"])
        self.assertEqual(res["uid"], "112233")
        self.assertEqual(mock_extract.call_args.kwargs.get("prefer_domain"), "weibo.com")

    def test_upload_image_computes_crc_md5_and_strips_ajax_headers(self):
        img_bytes = b"\xff\xd8\xff\xe0TEST_JPEG_DATA"
        captured = {}

        def _upload(url, sess, **kwargs):
            captured["url"] = url
            captured["params"] = kwargs.get("params")
            captured["headers"] = kwargs.get("headers")
            captured["data"] = kwargs.get("data")
            return _FakeResponse({"ret": True, "pic": {"pid": "pid_abc123"}})

        sess = _FakeSession(
            get_handlers=_auth_get_handlers(uid="555666"),
            post_handlers={"interface/upload.php": _upload},
        )
        pub = WeiboPublisher(cookie="SUB=abc", session=sess, auto_refresh=False)

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(img_bytes)
            tmp_path = tf.name
        try:
            res = pub.upload_image(file_path=tmp_path)
        finally:
            os.remove(tmp_path)

        self.assertTrue(res["ok"])
        self.assertEqual(res["pid"], "pid_abc123")
        self.assertEqual(res["type"], "image/jpeg")
        self.assertEqual(captured["params"]["cs"], zlib.crc32(img_bytes) & 0xFFFFFFFF)
        self.assertEqual(captured["params"]["raw_md5"], hashlib.md5(img_bytes).hexdigest())
        self.assertEqual(captured["params"]["uid"], "555666")
        self.assertIsNone(captured["headers"].get("X-Requested-With"))
        self.assertIsNone(captured["headers"].get("X-XSRF-TOKEN"))
        self.assertEqual(captured["headers"].get("Content-Type"), "application/octet-stream")

    def test_upload_image_retries_alt_host_then_falls_back_to_multipart(self):
        seen_hosts = []

        def _binary(url, sess, **kwargs):
            seen_hosts.append(url)
            if "picupload.weibo.com" in url:
                raise weibo_publisher.RequestException("network glitch")
            return _FakeResponse({"ret": False, "errno": -8})

        def _multipart(url, sess, **kwargs):
            seen_hosts.append(url)
            return _FakeResponse({"code": "A00006", "data": {"pics": {"pic_1": {"pid": "fallback_pid"}}}})

        sess = _FakeSession(
            get_handlers=_auth_get_handlers(),
            post_handlers={"interface/upload.php": _binary, "interface/pic_upload.php": _multipart},
        )
        pub = WeiboPublisher(cookie="SUB=abc", session=sess, auto_refresh=False)
        res = pub.upload_image(data=b"pngbytes", filename="test.png", mime_type="image/png")

        self.assertTrue(res["ok"])
        self.assertEqual(res["pid"], "fallback_pid")
        self.assertTrue(any("picupload.weibo.com/interface/upload.php" in u for u in seen_hosts))
        self.assertTrue(any("image.api.weibo.com/interface/upload.php" in u for u in seen_hosts))
        self.assertTrue(any("picupload.weibo.com/interface/pic_upload.php" in u for u in seen_hosts))

    def test_publish_payload_with_pics_visible_and_schedule(self):
        posts = []

        def _update(url, sess, **kwargs):
            posts.append((url, kwargs.get("data")))
            return _FakeResponse(
                {
                    "ok": 1,
                    "msg": "发布成功",
                    "data": {
                        "idstr": "53670001",
                        "mblogid": "AbCdEf",
                        "visible": {"type": 1, "list_id": 0},
                        "user": {"id": 1863732524, "screen_name": "测试"},
                    },
                }
            )

        sess = _FakeSession(
            get_handlers=_auth_get_handlers(),
            post_handlers={"/ajax/statuses/update": _update, "/ajax/statuses/schedule/upload": _update},
        )
        pub = WeiboPublisher(cookie="SUB=abc", session=sess, auto_refresh=False)

        res = pub.publish(
            content="测试正文",
            visible=1,
            pics=[{"pid": "pid1", "type": "image/jpeg"}, {"pid": "pid2", "type": "image/png"}],
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["mid"], "53670001")
        self.assertEqual(res["url"], "https://weibo.com/1863732524/AbCdEf")
        self.assertEqual(posts[0][0], "https://weibo.com/ajax/statuses/update")
        self.assertEqual(posts[0][1]["visible"], 1)
        self.assertEqual(
            json.loads(posts[0][1]["pic_id"]),
            [{"type": "image/jpeg", "pid": "pid1"}, {"type": "image/png", "pid": "pid2"}],
        )

        # Scheduled publish (>10 min ahead)
        future_ms = 2_000_000_000_000
        with mock.patch("util.publish.weibo_publisher.time.time", return_value=1_999_999_000.0):
            s_res = pub.publish(content="定时测试", visible=0, schedule_time=future_ms)
        self.assertTrue(s_res["ok"])
        self.assertEqual(posts[1][0], "https://weibo.com/ajax/statuses/schedule/upload")
        self.assertEqual(posts[1][1]["visible"], 0)
        self.assertEqual(posts[1][1]["schedule_timestamp"], future_ms)

    def test_publish_validation_dry_run_and_verify_handling(self):
        sess = _FakeSession(
            get_handlers=_auth_get_handlers(),
            post_handlers={
                "/ajax/statuses/update": lambda u, s, **kw: _FakeResponse({"ok": 1, "data": {"verify": {"gt": 1}}})
            },
        )
        pub = WeiboPublisher(cookie="SUB=abc", session=sess, auto_refresh=False)

        # Invalid visible
        bad_vis = pub.publish(content="hi", visible=99)
        self.assertFalse(bad_vis["ok"])

        # Too short schedule lead time (<10m)
        with self.assertRaises(ValueError):
            parse_schedule_timestamp(2_000_000_000_000 + 60_000, now_ms=2_000_000_000_000)

        # Too many images
        too_many = pub.publish(content="hi", pics=["p"] * (MAX_IMAGES + 1))
        self.assertFalse(too_many["ok"])

        # Dry run skips POST
        dry = pub.publish(content="干跑", visible=0, dry_run=True)
        self.assertTrue(dry["ok"])
        self.assertTrue(dry["dry_run"])
        self.assertEqual(dry["payload"]["visible"], 0)
        self.assertFalse(any(c[0] == "POST" for c in sess.calls))

        # Verify challenge stops cleanly
        ver = pub.publish(content="触发校验", visible=1)
        self.assertFalse(ver["ok"])
        self.assertTrue(ver.get("need_verify"))

    def test_edit_visibility_delete_and_list_posts(self):
        captured = {}

        def _can_edit(url, sess, **kwargs):
            return _FakeResponse({"ok": 1, "status": {"text": "old", "visible": {"type": 1}}})

        def _mymblog(url, sess, **kwargs):
            return _FakeResponse(
                {
                    "ok": 1,
                    "data": {
                        "list": [
                            {
                                "idstr": "5367111",
                                "mblogid": "XYZ123",
                                "created_at": "Thu Nov 19 20:00:00 +0800 2026",
                                "text_raw": "测试列表",
                                "visible": {"type": 1},
                                "pic_ids": ["p1"],
                                "pic_infos": {"p1": {"bmiddle": {"url": "https://img/p1.jpg"}}},
                            }
                        ]
                    },
                }
            )

        handlers = _auth_get_handlers()
        handlers["/ajax/statuses/checkCanEdit"] = _can_edit
        handlers["/ajax/statuses/mymblog"] = _mymblog

        def _modify(url, sess, **kwargs):
            captured["modify"] = kwargs["data"]
            return _FakeResponse({"ok": 1, "msg": "编辑成功", "data": {"idstr": "5367111", "text_raw": "new"}})

        def _vis(url, sess, **kwargs):
            captured["vis"] = kwargs["data"]
            return _FakeResponse({"ok": 1, "statuses": [{"visible": {"type": 0}, "edit_count": 1}]})

        def _destroy(url, sess, **kwargs):
            captured["destroy"] = kwargs["data"]
            return _FakeResponse({"ok": 1, "msg": "删除成功"})

        sess = _FakeSession(
            get_handlers=handlers,
            post_handlers={
                "/ajax/statuses/modifyVisible": _vis,
                "/ajax/statuses/modify": _modify,
                "/ajax/statuses/destroy": _destroy,
            },
        )
        pub = WeiboPublisher(cookie="SUB=abc", session=sess, auto_refresh=False)

        edit_res = pub.edit("5367111", "new content", visible=1)
        self.assertTrue(edit_res["ok"])
        self.assertEqual(captured["modify"], {"mid": "5367111", "content": "new content", "visible": 1})

        vis_res = pub.modify_visibility("5367111", 0)
        self.assertTrue(vis_res["ok"])
        self.assertEqual(captured["vis"], {"ids": "5367111", "visible": 0})
        self.assertEqual(vis_res["visible_label"], "公开")

        list_res = pub.list_my_posts(page=1)
        self.assertTrue(list_res["ok"])
        self.assertEqual(list_res["items"][0]["mid"], "5367111")
        self.assertEqual(list_res["items"][0]["visible_label"], "仅自己可见")

        del_res = pub.delete("5367111")
        self.assertTrue(del_res["ok"])
        self.assertEqual(captured["destroy"], {"id": "5367111"})

    def test_browser_cookie_prefer_domain_ordering(self):
        fake_rookiepy = types.SimpleNamespace(
            chrome=lambda domains: [
                {"domain": ".weibo.cn", "name": "SUB", "value": "cn_sub"},
                {"domain": ".weibo.com", "name": "SUB", "value": "com_sub"},
                {"domain": "weibo.com", "name": "XSRF-TOKEN", "value": "com_xsrf"},
                {"domain": ".weibo.cn", "name": "XSRF-TOKEN", "value": "cn_xsrf"},
            ]
        )
        with mock.patch.dict(sys.modules, {"rookiepy": fake_rookiepy}):
            default_cookie, err1, _ = browser_cookie.extract_browser_cookies("chrome")
            com_cookie, err2, _ = browser_cookie.extract_browser_cookies(
                "chrome", prefer_domain="weibo.com"
            )

        self.assertIsNone(err1)
        self.assertIsNone(err2)
        self.assertIn("SUB=cn_sub", default_cookie)
        self.assertIn("SUB=com_sub", com_cookie)
        self.assertIn("XSRF-TOKEN=com_xsrf", com_cookie)

    def test_weibo_ctl_publish_cli_offline_dry_run(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ctl_path = os.path.join(repo_root, "skills", "weibo-viewer", "scripts", "weibo_ctl.py")

        with _support.stdlib_http_context():
            spec = importlib.util.spec_from_file_location("weibo_ctl", ctl_path)
            weibo_ctl = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(weibo_ctl)

        fake_pub = mock.MagicMock()
        fake_pub.publish.return_value = {
            "ok": True,
            "dry_run": True,
            "endpoint": "/ajax/statuses/update",
            "msg": "干跑校验通过（未实际发布）",
        }
        buf = io.StringIO()
        with mock.patch.object(
            weibo_ctl, "http_request", return_value={"code": -1, "msg": "offline"}
        ), mock.patch.object(
            weibo_ctl, "_load_offline_publisher", return_value=fake_pub
        ), mock.patch.object(
            sys, "argv", ["weibo_ctl.py", "publish", "post", "--text", "CLI测试", "--visible", "1", "--dry-run", "--json"]
        ), mock.patch("sys.stdout", buf):
            weibo_ctl.main()

        out_json = json.loads(buf.getvalue())
        self.assertTrue(out_json["ok"])
        self.assertTrue(out_json["dry_run"])
        fake_pub.publish.assert_called_once()

    def test_image_proxy_url_allowlist_and_normalization(self):
        self.assertEqual(
            normalize_weibo_image_url("  //wx3.sinaimg.cn/bmiddle/abc.jpg "),
            "https://wx3.sinaimg.cn/bmiddle/abc.jpg",
        )
        for valid_url in (
            "https://wx1.sinaimg.cn/bmiddle/abc.jpg",
            "https://tvax2.sinaimg.cn/crop.0.0.100/avatar.jpg",
            "https://f.video.weibocdn.com/foo.jpg",
            "//wx3.sinaimg.cn/large/xyz.jpg",
        ):
            self.assertTrue(is_allowed_weibo_image_url(valid_url), valid_url)

        for blocked_url in (
            "",
            "http://127.0.0.1/a.jpg",
            "https://sinaimg.cn.evil.com/a.jpg",
            "https://user@wx1.sinaimg.cn/a.jpg",
            "file:///etc/passwd",
        ):
            self.assertFalse(is_allowed_weibo_image_url(blocked_url), blocked_url)

    def test_list_my_posts_normalizes_protocol_relative_and_large_urls(self):
        handlers = _auth_get_handlers()
        handlers["/ajax/statuses/mymblog"] = lambda u, s, **kw: _FakeResponse(
            {
                "ok": 1,
                "data": {
                    "list": [
                        {
                            "idstr": "5367222",
                            "mblogid": "NORM1",
                            "text_raw": "图文测试",
                            "visible": {"type": 1},
                            "pic_ids": ["picA"],
                            "pic_infos": {
                                "picA": {
                                    "bmiddle": {"url": "//wx2.sinaimg.cn/bmiddle/picA.jpg"},
                                    "large": {"url": "//wx2.sinaimg.cn/large/picA.jpg"},
                                }
                            },
                        }
                    ]
                },
            }
        )
        sess = _FakeSession(get_handlers=handlers)
        pub = WeiboPublisher(cookie="SUB=abc", session=sess, auto_refresh=False)
        res = pub.list_my_posts(page=1)

        self.assertTrue(res["ok"])
        pic = res["items"][0]["pics"][0]
        self.assertEqual(pic["url"], "https://wx2.sinaimg.cn/bmiddle/picA.jpg")
        self.assertEqual(pic["large_url"], "https://wx2.sinaimg.cn/large/picA.jpg")

    def test_init_populates_headers_on_non_dict_mapping_session(self):
        class _CaseInsensitiveHeaders(MutableMapping):
            def __init__(self):
                self._store = {}

            def __getitem__(self, key):
                return self._store[key.lower()][1]

            def __setitem__(self, key, value):
                self._store[key.lower()] = (key, value)

            def __delitem__(self, key):
                del self._store[key.lower()]

            def __iter__(self):
                return (orig for orig, _ in self._store.values())

            def __len__(self):
                return len(self._store)

        headers = _CaseInsensitiveHeaders()
        self.assertNotIsInstance(headers, dict)

        sess = _FakeSession()
        sess.headers = headers
        pub = WeiboPublisher(cookie="SUB=abc; XSRF-TOKEN=tok_non_dict", session=sess, auto_refresh=False)

        self.assertEqual(pub.session.headers["Referer"], "https://weibo.com/")
        self.assertEqual(pub.session.headers["Origin"], "https://weibo.com")
        self.assertEqual(pub.session.headers["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(pub.session.headers["Accept"], "application/json, text/plain, */*")
        self.assertEqual(pub.session.headers["User-Agent"], weibo_publisher.DEFAULT_USER_AGENT)
        self.assertEqual(pub.session.headers["client-version"], weibo_publisher.DEFAULT_CLIENT_VERSION)
        self.assertEqual(pub.session.headers["server-version"], weibo_publisher.DEFAULT_SERVER_VERSION)

        token = pub._sync_xsrf_header()
        self.assertEqual(token, "tok_non_dict")
        self.assertEqual(pub.session.headers["X-XSRF-TOKEN"], "tok_non_dict")


if __name__ == "__main__":
    unittest.main()
