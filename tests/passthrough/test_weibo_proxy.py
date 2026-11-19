"""Unit and Flask integration tests for native Weibo API pass-through proxy."""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock
from urllib.parse import parse_qs
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests import _support  # noqa: E402

_support.bootstrap()

from requests.exceptions import RequestException  # noqa: E402
from util.passthrough import (  # noqa: E402
    WeiboPassthroughProxy,
    clean_weibo_params,
    is_allowed_mobile_path,
    is_safe_subpath,
)

def _import_service_isolated():
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
    finally:
        sys.path[:] = saved_path
        if saved_http is not None:
            sys.modules["http"] = saved_http


try:
    service = _import_service_isolated()
except ImportError:  # pragma: no cover
    service = None


class _FakeCookieJar:
    def __init__(self):
        self._items = {}

    def set(self, name, value, **kwargs):
        domain = kwargs.get("domain", "")
        self._items[(domain, name)] = value

    def clear(self):
        self._items.clear()

    def __iter__(self):
        return iter(
            types.SimpleNamespace(domain=dom, name=name, value=val)
            for (dom, name), val in self._items.items()
        )


class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None, content=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers if headers is not None else {"Content-Type": "application/json; charset=utf-8"}
        if content is not None:
            self.content = content
        elif isinstance(payload, (dict, list)):
            self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        elif isinstance(payload, str):
            self.content = payload.encode("utf-8")
        else:
            self.content = b""
        self.text = self.content.decode("utf-8", errors="replace")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeSession:
    def __init__(self, handlers=None):
        self.headers = {}
        self.cookies = _FakeCookieJar()
        self.handlers = handlers or []
        self.calls = []

    def request(self, method, url, **kwargs):
        method_u = method.upper()
        self.calls.append((method_u, url, kwargs))
        for matcher, fn in self.handlers:
            if matcher(method_u, url, kwargs):
                res = fn(method_u, url, self, **kwargs)
                if isinstance(res, Exception):
                    raise res
                return res
        return _FakeResponse({"ok": 1, "data": {}, "url": url})

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def _make_proxy_with_tmp_cookie(cookie_str: str, session: _FakeSession, auto_refresh: bool = True):
    tmpdir = tempfile.mkdtemp(prefix="weibo-proxy-test-")
    cfg_dir = os.path.join(tmpdir, "config")
    os.makedirs(cfg_dir, exist_ok=True)
    with open(os.path.join(cfg_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"cookie": cookie_str}, f)
    proxy = WeiboPassthroughProxy(
        project_root=tmpdir,
        session=session,
        auto_refresh=auto_refresh,
    )
    return proxy, tmpdir


class WeiboPassthroughHelpersTest(unittest.TestCase):
    def test_is_safe_subpath(self):
        for good in (
            "statuses/mymblog",
            "profile/info",
            "shop/check/",
            "statuses/schedule/upload",
            "multimedia/getLiveInfoDetail",
        ):
            self.assertTrue(is_safe_subpath(good), good)

        for bad in (
            "",
            "/statuses/show",
            "../etc/passwd",
            "statuses/../config",
            "//evil.com/ajax",
            "http://evil.com/test",
            "https://weibo.com/ajax/test",
            "statuses\\show",
            "statuses/show?a=1",
            "statuses/show#frag",
            "statuses/show with space",
            "user@evil.com/path",
        ):
            self.assertFalse(is_safe_subpath(bad), bad)

    def test_is_allowed_mobile_path(self):
        for allowed in (
            "api/container/getIndex",
            "/api/config",
            "api/comments/show",
            "api/statuses/repostTimeline",
            "comments/hotflow",
            "comments/hotFlowChild",
            "statuses/show",
            "detail/5367067832485479",
            "detail/Rs8JVaqAn",
        ):
            self.assertTrue(is_allowed_mobile_path(allowed), allowed)

        for blocked in (
            "unknown/endpoint",
            "detail/bad/extra",
            "../comments/hotflow",
            "api/statuses/update",
        ):
            self.assertFalse(is_allowed_mobile_path(blocked), blocked)

    def test_clean_weibo_params_preserves_zero_and_serializes_nested(self):
        cleaned = clean_weibo_params(
            {
                "content": "hello",
                "visible": 0,
                "zero_str": "0",
                "empty": "",
                "none": None,
                "flag_false": False,
                "flag_true": True,
                "pic_id": [{"pid": "001abc", "type": "image/jpeg"}],
            }
        )
        self.assertEqual(cleaned["content"], "hello")
        self.assertEqual(cleaned["visible"], 0)
        self.assertEqual(cleaned["zero_str"], "0")
        self.assertTrue(cleaned["flag_true"])
        self.assertEqual(
            cleaned["pic_id"],
            json.dumps([{"pid": "001abc", "type": "image/jpeg"}], ensure_ascii=False),
        )
        self.assertNotIn("empty", cleaned)
        self.assertNotIn("none", cleaned)
        self.assertNotIn("flag_false", cleaned)


class WeiboPassthroughAjaxTest(unittest.TestCase):
    def tearDown(self):
        for attr in ("_tmpdirs",):
            for d in getattr(self, attr, []):
                _support.remove_tree(d)

    def _track_tmp(self, d):
        self._tmpdirs = getattr(self, "_tmpdirs", []) + [d]

    def test_ajax_get_endpoints_forward_upstream_and_headers(self):
        sess = _FakeSession(
            handlers=[
                (
                    lambda m, u, kw: "/ajax/profile/info" in u,
                    lambda m, u, s, **kw: _FakeResponse(
                        {"ok": 1, "data": {"user": {"id": 1669879400, "screen_name": "迪丽热巴"}}},
                        headers={"Content-Type": "application/json; charset=utf-8", "Content-Encoding": "gzip"},
                    ),
                ),
            ]
        )
        proxy, tmpdir = _make_proxy_with_tmp_cookie("SUB=sub1; XSRF-TOKEN=tok1", sess, auto_refresh=False)
        self._track_tmp(tmpdir)

        endpoints = [
            ("profile/info", {"uid": "1669879400"}),
            ("statuses/mymblog", {"uid": "1669879400", "page": "1", "feature": "0"}),
            ("statuses/buildComments", {"id": "5001", "is_mix": "0", "count": "20", "max_id": "0"}),
            ("statuses/show", {"id": "5001"}),
            ("statuses/longtext", {"id": "5001"}),
            ("statuses/repostTimeline", {"id": "5001", "page": "1"}),
            ("statuses/checkCanEdit", {"mid": "5001"}),
        ]
        for sub, qp in endpoints:
            status, headers, body = proxy.proxy_weibo_ajax(sub, method="GET", query_params=qp)
            self.assertEqual(status, 200)
            self.assertEqual(headers["X-Weibo-Passthrough-Upstream"], f"https://weibo.com/ajax/{sub}")
            self.assertNotIn("Content-Encoding", headers)
            data = json.loads(body.decode("utf-8"))
            self.assertEqual(data["ok"], 1)

        first_call = sess.calls[0]
        self.assertEqual(first_call[0], "GET")
        self.assertEqual(first_call[1], "https://weibo.com/ajax/profile/info")
        self.assertEqual(first_call[2]["headers"]["X-Requested-With"], "XMLHttpRequest")
        self.assertEqual(first_call[2]["headers"]["Referer"], "https://weibo.com/")
        self.assertEqual(first_call[2]["headers"]["X-XSRF-TOKEN"], "tok1")
        self.assertEqual(first_call[2]["params"], [("uid", "1669879400")])

    def test_ajax_post_json_and_form_bodies_and_write_endpoints(self):
        sess = _FakeSession()
        proxy, tmpdir = _make_proxy_with_tmp_cookie("SUB=sub1; XSRF-TOKEN=xsrf_val", sess, auto_refresh=False)
        self._track_tmp(tmpdir)

        # 1. JSON body automatically converted & cleaned to x-www-form-urlencoded
        status, _, body = proxy.proxy_weibo_ajax(
            "statuses/update",
            method="POST",
            json_body={"content": "hello", "visible": 0, "empty": "", "pic_id": [{"pid": "p1"}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["ok"], 1)

        _, url, kw = sess.calls[-1]
        self.assertEqual(url, "https://weibo.com/ajax/statuses/update")
        self.assertEqual(kw["headers"]["Content-Type"], "application/x-www-form-urlencoded; charset=UTF-8")
        self.assertEqual(kw["headers"]["X-XSRF-TOKEN"], "xsrf_val")
        parsed_form = parse_qs(kw["data"])
        self.assertEqual(parsed_form["content"], ["hello"])
        self.assertEqual(parsed_form["visible"], ["0"])
        self.assertNotIn("empty", parsed_form)
        self.assertEqual(parsed_form["pic_id"], ['[{"pid": "p1"}]'])

        # 2. Raw native x-www-form-urlencoded body forwarded directly across write endpoints
        for sub, raw in (
            ("statuses/update", b"content=raw_text&visible=1"),
            ("statuses/schedule/upload", b"content=sched&visible=0&schedule_timestamp=1900000000000"),
            ("statuses/modify", b"mid=5367&content=edited"),
            ("statuses/modifyVisible", b"ids=5367&visible=0"),
            ("statuses/destroy", b"id=5367"),
        ):
            st, _, _ = proxy.proxy_weibo_ajax(
                sub,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                body=raw,
            )
            self.assertEqual(st, 200)
            self.assertEqual(sess.calls[-1][1], f"https://weibo.com/ajax/{sub}")
            self.assertEqual(sess.calls[-1][2]["data"], raw)

    def test_ajax_xsrf_handshake_and_retry_on_403_and_ok_minus_100(self):
        # Case A: HTTP 403 -> XSRF handshake refreshes XSRF-TOKEN -> retry succeeds
        state_a = {"posts": 0}

        def _post_handler_a(m, u, s, **kw):
            state_a["posts"] += 1
            if state_a["posts"] == 1:
                return _FakeResponse({"ok": 0, "msg": "invalid xsrf"}, status_code=403)
            return _FakeResponse({"ok": 1, "retried_with": kw["headers"].get("X-XSRF-TOKEN")})

        def _cfg_handler_a(m, u, s, **kw):
            s.cookies.set("XSRF-TOKEN", "fresh_tok_a", domain=".weibo.com", path="/")
            return _FakeResponse({"ok": 1, "data": {}})

        sess_a = _FakeSession(
            handlers=[
                (lambda m, u, kw: "/ajax/statuses/config" in u, _cfg_handler_a),
                (lambda m, u, kw: m == "POST" and "/ajax/statuses/update" in u, _post_handler_a),
            ]
        )
        proxy_a, tmp_a = _make_proxy_with_tmp_cookie("SUB=sub_a; XSRF-TOKEN=stale_a", sess_a, auto_refresh=True)
        self._track_tmp(tmp_a)

        st, _, body = proxy_a.proxy_weibo_ajax("statuses/update", method="POST", body="content=hi&visible=1")
        self.assertEqual(st, 200)
        res_a = json.loads(body.decode("utf-8"))
        self.assertEqual(res_a["retried_with"], "fresh_tok_a")
        self.assertEqual(state_a["posts"], 2)

        # Case B: ok == -100 -> browser refresh + handshake -> retry succeeds
        state_b = {"gets": 0}

        def _mymblog_b(m, u, s, **kw):
            state_b["gets"] += 1
            if state_b["gets"] == 1:
                return _FakeResponse({"ok": -100, "msg": "login expired"})
            return _FakeResponse({"ok": 1, "data": {"list": [{"idstr": "99"}]}})

        def _cfg_handler_b(m, u, s, **kw):
            s.cookies.set("XSRF-TOKEN", "fresh_tok_b", domain=".weibo.com", path="/")
            return _FakeResponse({"ok": 1, "data": {}})

        sess_b = _FakeSession(
            handlers=[
                (lambda m, u, kw: "/ajax/statuses/config" in u, _cfg_handler_b),
                (lambda m, u, kw: "/ajax/statuses/mymblog" in u, _mymblog_b),
            ]
        )
        proxy_b, tmp_b = _make_proxy_with_tmp_cookie("SUB=old_b", sess_b, auto_refresh=True)
        self._track_tmp(tmp_b)

        with mock.patch(
            "util.passthrough.weibo_proxy.get_cookie_auto_config",
            return_value={"enabled": True, "refresh_on_expire": True, "browser": "chrome"},
        ), mock.patch(
            "util.passthrough.weibo_proxy.extract_and_save_cookie",
            return_value={"success": True, "valid": True, "cookie": "SUB=new_b; XSRF-TOKEN=fresh_tok_b"},
        ) as m_extract:
            st_b, _, body_b = proxy_b.proxy_weibo_ajax("statuses/mymblog", method="GET", query_params={"uid": "1"})

        self.assertEqual(st_b, 200)
        self.assertEqual(json.loads(body_b.decode("utf-8"))["data"]["list"][0]["idstr"], "99")
        m_extract.assert_called_once()
        self.assertEqual(m_extract.call_args.kwargs["prefer_domain"], "weibo.com")

    def test_ajax_rejects_traversal_and_isolates_caller_cookie(self):
        sess = _FakeSession()
        proxy, tmpdir = _make_proxy_with_tmp_cookie("SUB=proj_sub; XSRF-TOKEN=proj_xsrf", sess, auto_refresh=True)
        self._track_tmp(tmpdir)

        for bad in ("../statuses/show", "//evil.com/ajax/x", "statuses\\destroy"):
            st, _, body = proxy.proxy_weibo_ajax(bad, method="GET")
            self.assertEqual(st, 400)
            self.assertEqual(json.loads(body.decode("utf-8"))["ok"], 0)
        self.assertEqual(len(sess.calls), 0)

        # Caller-supplied X-Weibo-Cookie overrides header cookie and avoids browser refresh
        sess_err = _FakeSession(
            handlers=[
                (lambda m, u, kw: True, lambda m, u, s, **kw: _FakeResponse({"ok": -100, "msg": "bad caller"}, status_code=401)),
            ]
        )
        proxy_c, tmp_c = _make_proxy_with_tmp_cookie("SUB=proj_sub; XSRF-TOKEN=proj_xsrf", sess_err, auto_refresh=True)
        self._track_tmp(tmp_c)
        with mock.patch("util.passthrough.weibo_proxy.extract_and_save_cookie") as m_ext:
            st_c, _, _ = proxy_c.proxy_weibo_ajax(
                "statuses/update",
                method="POST",
                headers={"X-Weibo-Cookie": "SUB=caller_sub; XSRF-TOKEN=caller_xsrf"},
                body="content=hi&visible=1",
            )
        self.assertEqual(st_c, 401)
        self.assertEqual(sess_err.calls[0][2]["headers"]["X-XSRF-TOKEN"], "caller_xsrf")
        self.assertEqual(sess_err.calls[0][2]["headers"]["Cookie"], "SUB=caller_sub; XSRF-TOKEN=caller_xsrf")
        m_ext.assert_not_called()


class WeiboPassthroughPicuploadAndMobileTest(unittest.TestCase):
    def tearDown(self):
        for d in getattr(self, "_tmpdirs", []):
            _support.remove_tree(d)

    def _track_tmp(self, d):
        self._tmpdirs = getattr(self, "_tmpdirs", []) + [d]

    def test_picupload_binary_computes_metadata_strips_ajax_headers_and_falls_back(self):
        img_bytes = b"\xff\xd8\xff\xe0MOCK_JPEG_DATA"
        calls = []

        def _detail_ok(m, u, s, **kw):
            return _FakeResponse({"ok": 1, "data": {"verified_url": "https://verified.weibo.com/?uid=1863732524"}})

        def _primary_fail(m, u, s, **kw):
            calls.append((u, kw))
            raise RequestException("primary host unreachable")

        def _fallback_ok(m, u, s, **kw):
            calls.append((u, kw))
            return _FakeResponse({"ret": True, "pic": {"pid": "0021testPID"}})

        sess = _FakeSession(
            handlers=[
                (lambda m, u, kw: "/ajax/profile/detail" in u, _detail_ok),
                (lambda m, u, kw: "picupload.weibo.com/interface/upload.php" in u, _primary_fail),
                (lambda m, u, kw: "i.api.weibo.com/interface/upload.php" in u, _fallback_ok),
            ]
        )
        proxy, tmpdir = _make_proxy_with_tmp_cookie("SUB=sub1; XSRF-TOKEN=tok1", sess, auto_refresh=False)
        self._track_tmp(tmpdir)

        st, headers, body = proxy.proxy_picupload("upload.php", body=img_bytes)
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["pic"]["pid"], "0021testPID")
        self.assertEqual(headers["X-Weibo-Passthrough-Upstream"], "https://i.api.weibo.com/interface/upload.php")
        self.assertEqual(len(calls), 2)

        for _, kw in calls:
            self.assertEqual(kw["data"], img_bytes)
            self.assertEqual(kw["headers"]["Content-Type"], "application/octet-stream")
            self.assertEqual(kw["headers"]["Referer"], "https://weibo.com/")
            self.assertNotIn("X-Requested-With", kw["headers"])
            self.assertNotIn("X-XSRF-TOKEN", kw["headers"])
            self.assertEqual(kw["params"]["cs"], str(zlib.crc32(img_bytes) & 0xFFFFFFFF))
            self.assertEqual(kw["params"]["raw_md5"], hashlib.md5(img_bytes).hexdigest())
            self.assertEqual(kw["params"]["file_size"], str(len(img_bytes)))
            self.assertEqual(kw["params"]["uid"], "1863732524")
            self.assertTrue(kw["params"]["request_id"].isdigit())

    def test_picupload_multipart_maps_file_to_pic1_and_omits_xsrf(self):
        sess = _FakeSession(
            handlers=[
                (
                    lambda m, u, kw: "picupload.weibo.com/interface/pic_upload.php" in u,
                    lambda m, u, s, **kw: _FakeResponse(
                        {"code": "A00006", "data": {"pics": {"pic_1": {"pid": "mp001"}}}}
                    ),
                )
            ]
        )
        proxy, tmpdir = _make_proxy_with_tmp_cookie("SUB=sub1; XSRF-TOKEN=tok1", sess, auto_refresh=False)
        self._track_tmp(tmpdir)

        fake_file = types.SimpleNamespace(
            filename="photo.png",
            mimetype="image/png",
            stream=io.BytesIO(b"\x89PNG\r\n\x1a\nDATA"),
        )
        st, _, body = proxy.proxy_picupload("pic_upload.php", files={"file": fake_file})
        self.assertEqual(st, 200)
        self.assertEqual(json.loads(body.decode("utf-8"))["data"]["pics"]["pic_1"]["pid"], "mp001")

        _, url, kw = sess.calls[0]
        self.assertEqual(url, "https://picupload.weibo.com/interface/pic_upload.php")
        self.assertEqual(kw["params"]["app"], "miniblog")
        self.assertEqual(kw["params"]["s"], "json")
        self.assertIn("pic1", kw["files"])
        self.assertEqual(kw["files"]["pic1"][0], "photo.png")
        self.assertNotIn("X-Requested-With", kw["headers"])
        self.assertNotIn("X-XSRF-TOKEN", kw["headers"])

    def test_mobile_weibo_allowlisted_endpoints_and_detail_headers(self):
        sess = _FakeSession(
            handlers=[
                (
                    lambda m, u, kw: "m.weibo.cn/detail/" in u,
                    lambda m, u, s, **kw: _FakeResponse(
                        "<html>detail</html>",
                        headers={"Content-Type": "text/html; charset=utf-8"},
                    ),
                )
            ]
        )
        proxy, tmpdir = _make_proxy_with_tmp_cookie("SUB=m_sub", sess, auto_refresh=False)
        self._track_tmp(tmpdir)

        for mpath, qp in (
            ("api/container/getIndex", {"type": "uid", "value": "1669879400"}),
            ("comments/hotflow", {"id": "5367", "mid": "5367", "max_id_type": "0"}),
            ("comments/hotFlowChild", {"cid": "999", "max_id": "0", "max_id_type": "0"}),
            ("api/comments/show", {"id": "5367", "page": "1"}),
            ("api/statuses/repostTimeline", {"id": "5367", "page": "1"}),
            ("statuses/show", {"id": "5367"}),
            ("api/config", {}),
        ):
            st, headers, _ = proxy.proxy_mobile_weibo(mpath, query_params=qp)
            self.assertEqual(st, 200)
            self.assertEqual(headers["X-Weibo-Passthrough-Upstream"], f"https://m.weibo.cn/{mpath}")
            last_kw = sess.calls[-1][2]
            self.assertEqual(last_kw["headers"]["Referer"], "https://m.weibo.cn/")
            self.assertEqual(last_kw["headers"]["X-Requested-With"], "XMLHttpRequest")

        # Detail HTML page omits X-Requested-With
        st_d, headers_d, body_d = proxy.proxy_mobile_weibo("detail/5367")
        self.assertEqual(st_d, 200)
        self.assertIn("text/html", headers_d["Content-Type"])
        self.assertEqual(body_d, b"<html>detail</html>")
        self.assertNotIn("X-Requested-With", sess.calls[-1][2]["headers"])

        # Disallowed path returns 403
        st_bad, _, _ = proxy.proxy_mobile_weibo("api/statuses/update")
        self.assertEqual(st_bad, 403)


@unittest.skipIf(service is None, "Flask is not installed")
class ServicePassthroughIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="weibo-flask-proxy-")
        os.makedirs(os.path.join(self.tmpdir, "config"), exist_ok=True)
        with open(os.path.join(self.tmpdir, "config", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"cookie": "SUB=test_sub; XSRF-TOKEN=test_xsrf"}, f)

        def _handler(m, u, s, **kw):
            if "picupload.weibo.com/interface/upload.php" in u:
                return _FakeResponse({"ret": True, "pic": {"pid": "flaskUploadPid"}})
            if "picupload.weibo.com/interface/pic_upload.php" in u:
                return _FakeResponse({"code": "A00006", "data": {"pics": {"pic_1": {"pid": "flaskMpPid"}}}})
            if "/ajax/profile/detail" in u:
                return _FakeResponse({"ok": 1, "data": {"verified_url": "https://verified.weibo.com/?uid=777"}})
            if "m.weibo.cn/detail/" in u:
                return _FakeResponse("<html>ok</html>", headers={"Content-Type": "text/html"})
            return _FakeResponse({"ok": 1, "method": m, "url": u, "params": kw.get("params")})

        self.sess = _FakeSession(handlers=[(lambda m, u, kw: True, _handler)])
        self.proxy = WeiboPassthroughProxy(
            project_root=self.tmpdir, session=self.sess, auto_refresh=False
        )
        self.client = service.app.test_client()

    def tearDown(self):
        _support.remove_tree(self.tmpdir)

    def test_flask_routes_end_to_end(self):
        with mock.patch.object(service, "passthrough_proxy", self.proxy):
            # PC /ajax GET & POST
            r1 = self.client.get("/ajax/profile/info?uid=1669879400")
            self.assertEqual(r1.status_code, 200)
            self.assertEqual(r1.headers["X-Weibo-Passthrough-Upstream"], "https://weibo.com/ajax/profile/info")
            self.assertEqual(json.loads(r1.data)["ok"], 1)

            r2 = self.client.post("/ajax/statuses/update", json={"content": "hi", "visible": 1})
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(self.sess.calls[-1][1], "https://weibo.com/ajax/statuses/update")

            # picupload raw binary & multipart
            r3 = self.client.post(
                "/interface/upload.php",
                data=b"JPEG_BYTES",
                content_type="application/octet-stream",
            )
            self.assertEqual(r3.status_code, 200)
            self.assertEqual(json.loads(r3.data)["pic"]["pid"], "flaskUploadPid")

            r4 = self.client.post(
                "/interface/pic_upload.php",
                data={"pic1": (io.BytesIO(b"IMG"), "a.jpg")},
                content_type="multipart/form-data",
            )
            self.assertEqual(r4.status_code, 200)
            self.assertEqual(json.loads(r4.data)["data"]["pics"]["pic_1"]["pid"], "flaskMpPid")

            # Mobile passthrough routes
            for path in (
                "/api/container/getIndex?type=uid&value=1669879400",
                "/comments/hotflow?id=5367&mid=5367",
                "/comments/hotFlowChild?cid=11",
                "/api/comments/show?id=5367&page=1",
                "/api/statuses/repostTimeline?id=5367&page=1",
                "/statuses/show?id=5367",
                "/detail/5367",
                "/m/api/config",
            ):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200, path)

            # /api/config?passthrough=1 -> upstream m.weibo.cn/api/config (passthrough param stripped)
            r_pt = self.client.get("/api/config?passthrough=1")
            self.assertEqual(r_pt.status_code, 200)
            self.assertEqual(r_pt.headers["X-Weibo-Passthrough-Upstream"], "https://m.weibo.cn/api/config")
            self.assertIsNone(self.sess.calls[-1][2]["params"])

            # /api/config without passthrough stays Web Console config endpoint
            with mock.patch.object(service, "read_raw_config", return_value=("{}", {}, True)):
                r_cfg = self.client.get("/api/config")
            self.assertEqual(r_cfg.status_code, 200)
            cfg_js = json.loads(r_cfg.data)
            self.assertEqual(cfg_js["code"], 200)
            self.assertTrue(cfg_js["is_custom_config"])
            self.assertNotIn("X-Weibo-Passthrough-Upstream", r_cfg.headers)


if __name__ == "__main__":
    unittest.main()
