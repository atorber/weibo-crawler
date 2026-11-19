#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weibo Viewer & Controller CLI Helper
Provides programmatic control over the Weibo crawler and querying capabilities
for AI agents and terminal users. Supports both HTTP API and direct SQLite fallback.
"""

import sys
import os
import json
import argparse
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# Resolve workspace root by traversing upwards until weibo.py is found
def find_workspace_root():
    curr = os.path.abspath(os.path.dirname(__file__))
    while curr and curr != os.path.dirname(curr):
        if os.path.exists(os.path.join(curr, "weibo.py")):
            return curr
        curr = os.path.dirname(curr)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

WORKSPACE_ROOT = find_workspace_root()
DEFAULT_API_BASE = os.environ.get("WEIBO_API_BASE", "http://127.0.0.1:15001")
DB_PATH = os.path.join(WORKSPACE_ROOT, "weibodata.db")
CONFIG_PATH = os.path.join(WORKSPACE_ROOT, "config.json")
LOG_PATH = os.path.join(WORKSPACE_ROOT, "log")


def http_request(path, method="GET", payload=None, timeout=5):
    """Send HTTP request to Weibo Console API."""
    url = f"{DEFAULT_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            return json.loads(content) if content else {}
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8")
        try:
            return json.loads(err_msg)
        except Exception:
            return {"code": e.code, "msg": err_msg or str(e)}
    except Exception as e:
        return {"code": -1, "msg": f"Connection to {url} failed: {e}"}


def get_sqlite_conn():
    """Get SQLite connection if database file exists."""
    if os.path.exists(DB_PATH):
        return sqlite3.connect(DB_PATH)
    return None


def cmd_status(args):
    """Get status of the crawler service."""
    res = http_request("/api/status")
    if res.get("code") == 200:
        data = res.get("data", {})
        running = data.get("is_running", False)
        status_text = "🟢 RUNNING" if running else "⚪ IDLE"
        metrics = data.get("metrics", {})
        
        print(f"Service Status : {status_text} ({data.get('status', 'IDLE')})")
        print(f"Process PID    : {data.get('pid') or 'N/A'}")
        print(f"Current Target : {data.get('current_user') or 'None'}")
        print(f"Running Time   : {data.get('duration', 0)}s")
        print(f"Total Weibos   : {metrics.get('total_weibos', 0)}")
        print(f"Total Users    : {metrics.get('user_count', 0)}")
        print(f"DB Connected   : {'Yes' if metrics.get('db_connected') else 'No'}")
        if args.json:
            print("\n--- JSON OUTPUT ---")
            print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(f"⚠️  Console API ({DEFAULT_API_BASE}) offline. Checking local database...")
        if os.path.exists(DB_PATH):
            conn = get_sqlite_conn()
            c = conn.cursor()
            c.execute("SELECT count(*) FROM weibo")
            w_count = c.fetchone()[0]
            c.execute("SELECT count(*) FROM user")
            u_count = c.fetchone()[0]
            conn.close()
            print(f"SQLite DB      : {DB_PATH}")
            print(f"DB Weibo Count : {w_count}")
            print(f"DB User Count  : {u_count}")
        else:
            print(f"SQLite DB not found at {DB_PATH}")


def cmd_start(args):
    """Start the crawler task."""
    payload = {}
    if args.users:
        payload["user_id_list"] = [u.strip() for u in args.users.split(",") if u.strip()]
    if args.since_date:
        payload["since_date"] = args.since_date
    if args.original_only:
        payload["only_crawl_original"] = 1

    res = http_request("/api/service/start", method="POST", payload=payload)
    if res.get("code") == 200:
        print("✅ Crawler started successfully.")
        print(f"Message: {res.get('msg')}")
    else:
        print(f"❌ Failed to start crawler: {res.get('msg')}")


def cmd_stop(args):
    """Stop the running crawler process."""
    res = http_request("/api/service/stop", method="POST")
    if res.get("code") == 200:
        print("✅ Crawler stopped successfully.")
    else:
        print(f"❌ Failed to stop crawler: {res.get('msg')}")


def cmd_restart(args):
    """Restart the service and crawler."""
    res = http_request("/api/service/restart", method="POST")
    if res.get("code") == 200:
        print("✅ Service restart initiated.")
    else:
        print(f"❌ Failed to restart service: {res.get('msg')}")


def cmd_users(args):
    """List or update target users."""
    if args.action == "list":
        res = http_request("/api/users")
        if res.get("code") == 200:
            user_list = res.get("data", [])
            print(f"📋 Total target users: {len(user_list)}")
            for idx, user in enumerate(user_list, 1):
                if isinstance(user, dict):
                    uid = user.get("id") or user.get("user_id")
                    name = user.get("screen_name") or user.get("name") or "Unknown"
                    since = user.get("since_date") or "N/A"
                    print(f"  {idx}. [{uid}] {name} (Since: {since})")
                else:
                    print(f"  {idx}. {user}")
            if args.json:
                print(json.dumps(user_list, indent=2, ensure_ascii=False))
        else:
            # Fallback to config.json
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                users = cfg.get("user_id_list", [])
                print(f"📋 Total target users (from config.json): {len(users)}")
                for idx, uid in enumerate(users, 1):
                    print(f"  {idx}. {uid}")
            else:
                print("Config file not found.")
    elif args.action == "add":
        if not args.uid:
            print("Error: --uid is required for 'add'")
            sys.exit(1)
        res = http_request("/api/users", method="POST", payload={"user_id": args.uid})
        if res.get("code") == 200:
            print(f"✅ User {args.uid} added successfully.")
        else:
            print(f"❌ Failed to add user: {res.get('msg')}")
    elif args.action == "remove":
        if not args.uid:
            print("Error: --uid is required for 'remove'")
            sys.exit(1)
        res = http_request(f"/api/users/{args.uid}", method="DELETE")
        if res.get("code") == 200:
            print(f"✅ User {args.uid} removed successfully.")
        else:
            print(f"❌ Failed to remove user: {res.get('msg')}")


def cmd_query(args):
    """Query Weibo data with filters."""
    # Try HTTP API first
    params = {}
    if args.keyword:
        params["keyword"] = args.keyword
    if args.user_id:
        params["user_id"] = args.user_id
    if args.start_date:
        params["start_date"] = args.start_date
    if args.end_date:
        params["end_date"] = args.end_date
    params["page_size"] = args.limit or 10
    params["page"] = args.page or 1

    query_str = urllib.parse.urlencode(params)
    res = http_request(f"/api/data/weibos?{query_str}")
    
    records = []
    total = 0
    if res.get("code") == 200:
        data = res.get("data", {})
        records = data.get("items") or data.get("list") or data.get("records") or []
        total = data.get("total", len(records))
    else:
        # Fallback to direct SQLite query
        conn = get_sqlite_conn()
        if not conn:
            print(f"❌ Failed to fetch data: HTTP API error and SQLite DB not found ({res.get('msg')})")
            return
        
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        sql = "SELECT * FROM weibo WHERE 1=1"
        sql_params = []
        if args.user_id:
            sql += " AND user_id = ?"
            sql_params.append(args.user_id)
        if args.keyword:
            sql += " AND (text LIKE ? OR topics LIKE ?)"
            sql_params.extend([f"%{args.keyword}%", f"%{args.keyword}%"])
        if args.start_date:
            sql += " AND created_at >= ?"
            sql_params.append(f"{args.start_date} 00:00:00")
        if args.end_date:
            sql += " AND created_at <= ?"
            sql_params.append(f"{args.end_date} 23:59:59")
            
        # Count total
        count_sql = "SELECT count(*) FROM (" + sql + ")"
        c.execute(count_sql, sql_params)
        total = c.fetchone()[0]
        
        # Order and limit
        order_col = "created_at"
        if args.sort in ["attitudes_count", "comments_count", "reposts_count"]:
            order_col = args.sort
        sql += f" ORDER BY {order_col} DESC LIMIT ? OFFSET ?"
        offset = (args.page - 1) * args.limit
        sql_params.extend([args.limit, offset])
        
        c.execute(sql, sql_params)
        rows = c.fetchall()
        for r in rows:
            records.append(dict(r))
        conn.close()

    if args.json:
        print(json.dumps({"total": total, "count": len(records), "records": records}, indent=2, ensure_ascii=False))
        return

    print(f"\n🔍 Query Results: Found {total} total records (Showing {len(records)} on page {args.page})\n" + "="*80)
    for idx, item in enumerate(records, 1):
        uname = item.get("screen_name") or item.get("user_id")
        created_at = item.get("created_at") or "Unknown Date"
        att = item.get("attitudes_count", 0)
        comm = item.get("comments_count", 0)
        rep = item.get("reposts_count", 0)
        bid = item.get("bid") or item.get("id")
        text = (item.get("text") or "").strip()
        pics = item.get("pics") or ""
        video = item.get("video_url") or ""
        media_info = []
        if pics:
            pics_cnt = len(pics.split(',')) if isinstance(pics, str) else len(pics)
            media_info.append(f"📷 {pics_cnt} Pics")
        if video:
            media_info.append("🎬 Video")

        print(f"[{idx}] {uname} | 🕒 {created_at} | 🔗 https://weibo.com/{item.get('user_id')}/{bid}")
        print(f"    👍 {att}  💬 {comm}  🔄 {rep}  {' | '.join(media_info)}")
        print(f"    📝 {text[:160]}{'...' if len(text) > 160 else ''}")
        print("-" * 80)


def cmd_logs(args):
    """View recent crawler logs."""
    res = http_request(f"/api/logs?limit={args.lines}")
    if res.get("code") == 200:
        logs = res.get("logs", [])
        if isinstance(logs, list):
            for line in logs:
                print(line.rstrip())
        else:
            print(logs)
    else:
        # Fallback to local log directory
        if os.path.exists(LOG_PATH):
            log_files = [f for f in os.listdir(LOG_PATH) if f.endswith(".log")]
            if log_files:
                log_files.sort(key=lambda f: os.path.getmtime(os.path.join(LOG_PATH, f)), reverse=True)
                latest_log = os.path.join(LOG_PATH, log_files[0])
                print(f"Reading from {latest_log}:")
                with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    for line in lines[-args.lines:]:
                        print(line.rstrip())
            else:
                print("No log files found in log directory.")
        else:
            print(f"Cannot retrieve logs: {res.get('msg')}")


def cmd_cookie(args):
    """Inspect or extract browser Cookie."""
    if args.extract:
        browser = args.browser or "chrome"
        print(f"Attempting to extract cookie from {browser}...")
        res = http_request("/api/cookie/import_browser", method="POST", payload={"browser": browser})
        if res.get("code") == 200:
            print(f"✅ Successfully extracted cookie from {browser}!")
            cookie_preview = res.get("data", {}).get("cookie", "")[:30] + "..."
            print(f"Cookie: {cookie_preview}")
        else:
            print(f"❌ Failed to extract cookie: {res.get('msg')}")
    else:
        res = http_request("/api/cookie/check", method="POST")
        if res.get("code") == 200:
            data = res.get("data", {})
            valid = data.get("valid", False)
            status_symbol = "✅ VALID" if valid else "❌ INVALID / EXPIRED"
            print(f"Cookie Status: {status_symbol}")
            print(f"Details      : {data.get('message') or data.get('msg')}")
        else:
            print(f"Status check failed: {res.get('msg')}")


def _load_offline_publisher():
    """Import WeiboPublisher locally when console service is offline."""
    if WORKSPACE_ROOT not in sys.path:
        sys.path.insert(0, WORKSPACE_ROOT)
    from util.publish.weibo_publisher import WeiboPublisher

    return WeiboPublisher(project_root=WORKSPACE_ROOT)


def _print_publish_output(res_data, ok, message, as_json=False, extra_lines=None):
    if as_json:
        print(json.dumps(res_data, indent=2, ensure_ascii=False))
        return
    if ok:
        print(f"✅ {message}")
        for line in extra_lines or []:
            print(line)
    else:
        print(f"❌ {message}")


def cmd_publish(args):
    """Publish or manage Weibo posts (online API first, offline WeiboPublisher fallback)."""
    action = args.action
    as_json = getattr(args, "json", False)

    if action == "status":
        res = http_request("/api/publish/status", timeout=15)
        if res.get("code") == -1:
            pub = _load_offline_publisher()
            d = pub.ensure_session()
            ok = bool(d.get("logged_in"))
            _print_publish_output(
                d,
                ok,
                d.get("message") or ("已就绪" if ok else "未登录"),
                as_json=as_json,
                extra_lines=[f"UID: {d.get('uid') or 'N/A'} | Screen Name: {d.get('screen_name') or 'N/A'}"],
            )
            if not ok:
                sys.exit(1)
            return
        d = res.get("data", {})
        ok = res.get("code") == 200 and bool(d.get("logged_in"))
        _print_publish_output(
            res,
            ok,
            d.get("message") or res.get("msg") or "",
            as_json=as_json,
            extra_lines=[f"UID: {d.get('uid') or 'N/A'} | Screen Name: {d.get('screen_name') or 'N/A'}"],
        )
        if not ok:
            sys.exit(1)
        return

    if action == "post":
        vis = 0 if args.visible is None else args.visible
        images = [os.path.abspath(p) for p in (args.images or [])]
        payload = {
            "content": args.text or "",
            "visible": vis,
            "images": images,
            "schedule_time": args.schedule,
            "topic_id": args.topic_id,
            "dry_run": bool(args.dry_run),
        }
        res = http_request("/api/publish/post", method="POST", payload=payload, timeout=60)
        if res.get("code") == -1:
            pub = _load_offline_publisher()
            d = pub.publish(**payload)
            ok = bool(d.get("ok"))
            _print_publish_output(
                d,
                ok,
                d.get("msg") or ("发布成功" if ok else "发布失败"),
                as_json=as_json,
                extra_lines=[
                    f"MID: {d.get('mid') or 'N/A'} | Visible: {d.get('visible_label', vis)}",
                    f"URL: {d.get('url') or 'N/A'}",
                ] if ok and not args.dry_run else [],
            )
            if not ok:
                sys.exit(1)
            return
        ok = res.get("code") == 200 and bool(res.get("success"))
        d = res.get("data", {})
        _print_publish_output(
            res,
            ok,
            res.get("message") or res.get("msg") or "",
            as_json=as_json,
            extra_lines=[
                f"MID: {d.get('mid') or 'N/A'} | Visible: {d.get('visible_label', vis)}",
                f"URL: {d.get('url') or 'N/A'}",
            ] if ok and not args.dry_run else [],
        )
        if not ok:
            sys.exit(1)
        return

    if action == "edit":
        if not args.mid:
            print("❌ --mid is required for 'edit'")
            sys.exit(1)
        images = [os.path.abspath(p) for p in (args.images or [])]
        payload = {
            "mid": args.mid,
            "content": args.text or "",
            "visible": args.visible,
            "images": images,
            "check_first": not args.no_check,
            "dry_run": bool(args.dry_run),
        }
        res = http_request("/api/publish/edit", method="POST", payload=payload, timeout=60)
        if res.get("code") == -1:
            pub = _load_offline_publisher()
            d = pub.edit(**payload)
            ok = bool(d.get("ok"))
            _print_publish_output(
                d,
                ok,
                d.get("msg") or ("编辑成功" if ok else "编辑失败"),
                as_json=as_json,
            )
            if not ok:
                sys.exit(1)
            return
        ok = res.get("code") == 200 and bool(res.get("success"))
        _print_publish_output(res, ok, res.get("message") or res.get("msg") or "", as_json=as_json)
        if not ok:
            sys.exit(1)
        return

    if action == "visibility":
        if not args.mid or args.visible is None:
            print("❌ Both --mid and --visible are required for 'visibility'")
            sys.exit(1)
        payload = {"mid": args.mid, "visible": args.visible}
        res = http_request("/api/publish/visibility", method="POST", payload=payload, timeout=15)
        if res.get("code") == -1:
            pub = _load_offline_publisher()
            d = pub.modify_visibility(args.mid, args.visible)
            ok = bool(d.get("ok"))
            _print_publish_output(
                d,
                ok,
                d.get("msg") or ("修改成功" if ok else "修改失败"),
                as_json=as_json,
            )
            if not ok:
                sys.exit(1)
            return
        ok = res.get("code") == 200 and bool(res.get("success"))
        _print_publish_output(res, ok, res.get("message") or res.get("msg") or "", as_json=as_json)
        if not ok:
            sys.exit(1)
        return

    if action == "delete":
        if not args.mid:
            print("❌ --mid is required for 'delete'")
            sys.exit(1)
        payload = {"mid": args.mid}
        res = http_request("/api/publish/delete", method="POST", payload=payload, timeout=15)
        if res.get("code") == -1:
            pub = _load_offline_publisher()
            d = pub.delete(args.mid)
            ok = bool(d.get("ok"))
            _print_publish_output(
                d,
                ok,
                d.get("msg") or ("删除成功" if ok else "删除失败"),
                as_json=as_json,
            )
            if not ok:
                sys.exit(1)
            return
        ok = res.get("code") == 200 and bool(res.get("success"))
        _print_publish_output(res, ok, res.get("message") or res.get("msg") or "", as_json=as_json)
        if not ok:
            sys.exit(1)
        return

    if action == "list":
        qs = urllib.parse.urlencode({"source": args.source, "page": args.page})
        res = http_request(f"/api/publish/posts?{qs}", timeout=15)
        if res.get("code") == -1:
            pub = _load_offline_publisher()
            d = pub.list_my_posts(page=args.page) if args.source != "local" else {"ok": False, "items": [], "msg": "服务离线且未启用远端拉取"}
            if as_json:
                print(json.dumps(d, indent=2, ensure_ascii=False))
                if not d.get("ok"):
                    sys.exit(1)
                return
            if not d.get("ok"):
                print(f"❌ {d.get('msg')}")
                sys.exit(1)
            items = d.get("items") or []
        else:
            d = res.get("data", {})
            if as_json:
                print(json.dumps(res, indent=2, ensure_ascii=False))
                return
            if d.get("remote_error"):
                print(f"⚠️  {d['remote_error']}")
            items = d.get("items") or []

        if not items:
            print("No posts found.")
            return
        for it in items:
            vis_label = it.get("visible_label") or it.get("visible_type")
            snippet = (it.get("text_raw") or "").replace("\n", " ")[:90]
            print(f"[{it.get('mid')}] ({vis_label}) {it.get('created_at', '')} | {snippet}")


def _service_online():
    res = http_request("/api/status", timeout=3)
    return res.get("code") != -1


def _build_chat_client(via="auto"):
    """Build a WeiboChatClient that rides on the Mode 1 /webim/* pass-through.

    - http : service online -> requests go to {WEIBO_API_BASE}/webim/<path>
    - local: service offline -> in-process WeiboPassthroughProxy.proxy_webim
    """
    if WORKSPACE_ROOT not in sys.path:
        sys.path.insert(0, WORKSPACE_ROOT)
    from util.chat.weibo_chat import WeiboChatClient

    mode = via
    if via == "auto":
        mode = "http" if _service_online() else "local"
    if mode == "http":
        return WeiboChatClient(project_root=WORKSPACE_ROOT, passthrough_base_url=DEFAULT_API_BASE)
    return WeiboChatClient(project_root=WORKSPACE_ROOT)


def _parse_kv_list(items):
    out = {}
    for item in items or []:
        if "=" not in item:
            print(f"❌ Invalid key=value pair: {item}")
            sys.exit(1)
        k, v = item.split("=", 1)
        out[k.strip()] = v
    return out


def _print_chat_trace(client):
    trace = getattr(client, "trace", None) or []
    if not trace:
        return
    print(f"🔌 via {client.transport} pass-through:")
    for t in trace:
        print(f"   {t['method']} {t['path']} -> {t['status']}")


def cmd_chat(args):
    """Weibo Direct Messages & Group Chats, built on the /webim/* native pass-through."""
    action = args.action
    as_json = bool(getattr(args, "json", False))
    client = _build_chat_client(getattr(args, "via", "auto"))

    def _finish(d, ok_key="ok", text_lines=None):
        ok = bool(d.get(ok_key))
        if as_json:
            out = dict(d)
            out.pop("raw", None) if not getattr(args, "raw_json", False) else None
            out["passthrough"] = client.trace
            print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
        else:
            if text_lines:
                for line in text_lines:
                    print(line)
            else:
                print(f"{'✅' if ok else '❌'} {d.get('message') or d.get('msg') or ''}")
            if args.verbose:
                _print_chat_trace(client)
        if not ok:
            sys.exit(1)

    if action == "status":
        d = client.check_auth()
        lines = (
            [f"✅ WebIM 已登录: {d.get('screen_name') or d.get('uid')} (UID: {d.get('uid')})"]
            if d.get("authenticated")
            else [f"❌ WebIM 未登录或失效: {d.get('message')}"]
        )
        _finish(d, ok_key="authenticated", text_lines=lines)
        return

    if action == "contacts":
        if args.keyword:
            d = client.search_contacts(keyword=args.keyword, count=args.limit)
        else:
            d = client.list_contacts(count=args.limit, cursor=args.max_id or 0, unfollow=bool(args.unfollow))
        lines = None
        if d.get("ok"):
            contacts = d.get("contacts") or []
            lines = ["No contacts found."] if not contacts else []
            for c in contacts:
                tag = "Group" if c.get("is_group") else "User"
                unread = f" [未读:{c.get('unread_count')}]" if c.get("unread_count") else ""
                snippet = (c.get("last_text") or "").replace("\n", " ")[:60]
                lines.append(f"[{tag} {c.get('id')}] {c.get('name')}{unread} | {snippet}")
        _finish(d, text_lines=lines)
        return

    if action == "messages":
        if not args.uid and not args.gid:
            print("❌ Either --uid or --gid is required for 'messages'")
            sys.exit(1)
        target_gid = args.gid or (args.uid if len(str(args.uid).strip()) >= 15 else "")
        if target_gid:
            d = client.get_group_messages(gid=target_gid, count=args.limit, max_mid=args.max_id or 0)
        else:
            d = client.get_conversation(
                uid=args.uid, count=args.limit, max_id=args.max_id or 0, unfollow=bool(args.unfollow)
            )
        lines = None
        if d.get("ok"):
            msgs = d.get("messages") or []
            lines = ["No messages found."] if not msgs else []
            for m in msgs:
                text = (m.get("text") or "").replace("\n", " ")
                lines.append(f"[{m.get('mid')}] {m.get('created_at', '')} {m.get('sender_name') or m.get('sender_uid')}: {text}")
        _finish(d, text_lines=lines)
        return

    if action == "send":
        if not args.uid and not args.gid:
            print("❌ Either --uid or --gid is required for 'send'")
            sys.exit(1)
        d = client.send_message(
            uid=args.uid or "",
            gid=args.gid or "",
            text=args.text or "",
            file_path=os.path.abspath(args.file) if args.file else None,
            dry_run=bool(args.dry_run),
        )
        ok = bool(d.get("ok"))
        lines = [f"{'✅' if ok else '❌'} {d.get('message') or d.get('msg')} (MID: {d.get('mid') or 'N/A'})"]
        _finish(d, text_lines=lines)
        return

    if action == "recall":
        if not args.mid:
            print("❌ --mid is required for 'recall'")
            sys.exit(1)
        _finish(client.recall_message(mid=args.mid, gid=args.gid or ""))
        return

    if action == "delete":
        if not args.mid and not args.uid and not args.gid:
            print("❌ Provide --mid (single message) or --uid/--gid (conversation) for 'delete'")
            sys.exit(1)
        _finish(client.delete_message(mid=args.mid or "", uid=args.uid or "", gid=args.gid or "", unfollow=bool(args.unfollow)))
        return

    if action == "read":
        if not args.uid and not args.gid and not args.unfollow:
            print("❌ Provide --uid, --gid, or --unfollow for 'read'")
            sys.exit(1)
        _finish(client.mark_read(uid=args.uid or "", gid=args.gid or "", unfollow=bool(args.unfollow)))
        return

    if action == "raw":
        if not args.path:
            print("❌ --path is required for 'raw' (e.g. 2/direct_messages/contacts.json)")
            sys.exit(1)
        params = _parse_kv_list(args.param)
        form = _parse_kv_list(args.data)
        method = (args.method or ("POST" if form else "GET")).upper()
        d = client.raw_request(method, args.path, params=params or None, form_data=form if method != "GET" else None)
        if as_json or True:
            print(json.dumps(d if as_json else d.get("data"), indent=2, ensure_ascii=False, default=str))
            if not as_json:
                print(f"\n🔌 {method} {d.get('path')} -> HTTP {d.get('status')} ({client.transport}) {d.get('upstream') or ''}")
        if not d.get("ok"):
            sys.exit(1)
        return


def cmd_passthrough(args):
    """Layer-1 Weibo Native Pass-Through Gateway CLI (`info` or `request`)."""
    if WORKSPACE_ROOT not in sys.path:
        sys.path.insert(0, WORKSPACE_ROOT)
    from util.passthrough import WeiboPassthroughProxy

    action = args.action
    as_json = bool(getattr(args, "json", False))

    if action == "info":
        res = http_request("/api/passthrough/info", timeout=5)
        if res.get("code") == -1:
            proxy = WeiboPassthroughProxy(project_root=WORKSPACE_ROOT)
            info = {
                "cookie_configured": bool(getattr(proxy, "_cookie_str", "")),
                "has_xsrf_token": bool(proxy._latest_xsrf_token()),
                "auto_refresh_enabled": bool(proxy.auto_refresh),
                "transport": "local (service offline)",
                "upstreams": [
                    "/ajax/<subpath> -> https://weibo.com/ajax/<subpath>",
                    "/webim/<subpath> -> https://api.weibo.com/webim/<subpath>",
                    "/interface/upload.php -> https://picupload.weibo.com/interface/upload.php",
                    "/api/container/getIndex | /comments/hotflow | ... -> https://m.weibo.cn/*",
                ],
            }
        else:
            info = res.get("data", res)
        if as_json:
            print(json.dumps(info, indent=2, ensure_ascii=False))
            return
        print("🔌 Weibo Native Pass-Through Gateway (Layer 1)")
        print(f"   Cookie Ready : {'Yes' if info.get('cookie_configured') else 'No'}")
        print(f"   XSRF-TOKEN   : {'Yes' if info.get('has_xsrf_token') else 'No'}")
        print("   Upstreams    :")
        for u in info.get("upstreams", []):
            if isinstance(u, dict):
                print(f"     • {u.get('local_route')} -> {u.get('upstream_base')}")
            else:
                print(f"     • {u}")
        return

    raw_path = (args.path or "").strip()
    if not raw_path:
        print("❌ --path is required for 'passthrough request' (e.g. /ajax/statuses/config or /webim/query_primary_info.json)")
        sys.exit(1)

    norm = raw_path.lstrip("/")
    params = _parse_kv_list(args.param)
    form = _parse_kv_list(args.data)
    method = (args.method or ("POST" if form else "GET")).upper()

    proxy = WeiboPassthroughProxy(project_root=WORKSPACE_ROOT)
    if norm.startswith("ajax/"):
        status, headers, content = proxy.proxy_weibo_ajax(
            norm[len("ajax/"):],
            method=method,
            query_params=params or None,
            form_data=form if method != "GET" else None,
        )
    elif norm.startswith("webim/"):
        status, headers, content = proxy.proxy_webim(
            norm[len("webim/"):],
            method=method,
            query_params=params or None,
            form_data=form if method != "GET" else None,
        )
    elif norm.startswith("interface/"):
        ep = norm[len("interface/"):]
        body_bytes = None
        if args.file:
            with open(os.path.abspath(args.file), "rb") as f:
                body_bytes = f.read()
        status, headers, content = proxy.proxy_picupload(
            ep, query_params=params or None, body=body_bytes
        )
    else:
        mobile_path = "api/config" if norm == "m/api/config" else norm
        status, headers, content = proxy.proxy_mobile_weibo(
            mobile_path, method=method, query_params=params or None
        )

    try:
        parsed_body = json.loads((content or b"").decode("utf-8"))
    except Exception:
        parsed_body = (content or b"").decode("utf-8", errors="replace")

    out = {
        "status": status,
        "upstream": (headers or {}).get("X-Weibo-Passthrough-Upstream", ""),
        "data": parsed_body,
    }
    print(json.dumps(out if as_json else parsed_body, indent=2, ensure_ascii=False, default=str))
    if not as_json:
        print(f"\n🔌 {method} /{norm} -> HTTP {status} ({out['upstream']})")
    if status >= 400:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Weibo Crawler & Data Viewer CLI Helper",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Status
    p_status = subparsers.add_parser("status", help="Get crawler and service status")
    p_status.add_argument("--json", action="store_true", help="Output raw JSON")

    # Start
    p_start = subparsers.add_parser("start", help="Start crawler task")
    p_start.add_argument("--users", type=str, help="Comma-separated user IDs to crawl")
    p_start.add_argument("--since-date", type=str, help="Start date (YYYY-MM-DD or days offset)")
    p_start.add_argument("--original-only", action="store_true", help="Crawl original posts only")

    # Stop
    subparsers.add_parser("stop", help="Stop running crawler process")

    # Restart
    subparsers.add_parser("restart", help="Restart crawler service")

    # Users
    p_users = subparsers.add_parser("users", help="Manage target users")
    p_users.add_argument("action", choices=["list", "add", "remove"], default="list", nargs="?")
    p_users.add_argument("--uid", type=str, help="Weibo user ID")
    p_users.add_argument("--json", action="store_true", help="Output raw JSON")

    # Query
    p_query = subparsers.add_parser("query", help="Query and search crawled Weibo posts")
    p_query.add_argument("--keyword", "-k", type=str, help="Search keyword in text or topics")
    p_query.add_argument("--user-id", "-u", type=str, help="Filter by user ID")
    p_query.add_argument("--start-date", type=str, help="Filter start date (YYYY-MM-DD)")
    p_query.add_argument("--end-date", type=str, help="Filter end date (YYYY-MM-DD)")
    p_query.add_argument("--sort", choices=["created_at", "attitudes_count", "comments_count", "reposts_count"], default="created_at")
    p_query.add_argument("--limit", "-l", type=int, default=10, help="Number of records to show")
    p_query.add_argument("--page", "-p", type=int, default=1, help="Page number")
    p_query.add_argument("--json", action="store_true", help="Output raw JSON")

    # Logs
    p_logs = subparsers.add_parser("logs", help="View recent logs")
    p_logs.add_argument("--lines", "-n", type=int, default=30, help="Number of lines to tail")

    # Cookie
    p_cookie = subparsers.add_parser("cookie", help="Check or extract Cookie")
    p_cookie.add_argument("--extract", action="store_true", help="Extract cookie from browser")
    p_cookie.add_argument("--browser", choices=["chrome", "edge", "firefox", "brave", "safari"], default="chrome")

    # Publish & Post Management
    p_pub = subparsers.add_parser("publish", help="Publish, edit, delete, or change visibility of Weibo posts")
    p_pub.add_argument("action", choices=["status", "post", "edit", "visibility", "delete", "list"], default="status", nargs="?")
    p_pub.add_argument("--text", "-t", type=str, help="Post text content")
    p_pub.add_argument("--images", "-i", nargs="+", help="Local image file path(s) to upload and attach")
    p_pub.add_argument("--visible", "-v", type=int, choices=[0, 1, 5, 6, 10], default=None, help="Visibility: 0=public, 1=self, 6=friends, 10=fans, 5=group")
    p_pub.add_argument("--schedule", type=str, help="Schedule publish time (YYYY-MM-DD HH:MM, >=10 min ahead)")
    p_pub.add_argument("--topic-id", type=str, help="Optional Chaohua/topic ID")
    p_pub.add_argument("--mid", type=str, help="Target post mid (for edit, visibility, delete)")
    p_pub.add_argument("--no-check", action="store_true", help="Skip checkCanEdit preflight before editing")
    p_pub.add_argument("--dry-run", action="store_true", help="Validate parameters without sending post/edit request")
    p_pub.add_argument("--source", choices=["remote", "local"], default="remote", help="Post list source")
    p_pub.add_argument("--page", type=int, default=1, help="Timeline page number (for list)")
    p_pub.add_argument("--json", action="store_true", help="Output raw JSON")

    # Direct Message & Group Chat Management
    p_chat = subparsers.add_parser("chat", help="Weibo Direct Messages & Group Chats (built on /webim/* pass-through)")
    p_chat.add_argument("action", choices=["status", "contacts", "messages", "send", "recall", "delete", "read", "raw"], default="status", nargs="?")
    p_chat.add_argument("--uid", type=str, help="Target 1-on-1 user UID")
    p_chat.add_argument("--gid", type=str, help="Target group chat GID (>=15 digits)")
    p_chat.add_argument("--text", "-t", type=str, help="Message text content")
    p_chat.add_argument("--file", "-f", type=str, help="Local image or attachment path to send")
    p_chat.add_argument("--mid", type=str, help="Target message ID (for recall or delete)")
    p_chat.add_argument("--keyword", "-k", type=str, help="Search keyword for contacts/groups")
    p_chat.add_argument("--unfollow", action="store_true", help="Target unfollowed message box (public)")
    p_chat.add_argument("--limit", "-l", type=int, default=20, help="Number of contacts or messages to fetch")
    p_chat.add_argument("--max-id", type=int, default=0, help="Pagination cursor (max_id / max_mid / cursor)")
    p_chat.add_argument("--dry-run", action="store_true", help="Validate chat message parameters without sending")
    p_chat.add_argument("--via", choices=["auto", "http", "local"], default="auto", help="Pass-through transport: http=service /webim/*, local=in-process proxy_webim")
    p_chat.add_argument("--method", type=str, help="HTTP method for 'raw' (default GET, or POST when --data given)")
    p_chat.add_argument("--path", type=str, help="Native WebIM path for 'raw', e.g. 2/direct_messages/contacts.json")
    p_chat.add_argument("--param", action="append", help="Query param key=value for 'raw' (repeatable)")
    p_chat.add_argument("--data", action="append", help="Form field key=value for 'raw' POST (repeatable)")
    p_chat.add_argument("--verbose", "-V", action="store_true", help="Print the /webim/* pass-through call trace")
    p_chat.add_argument("--json", action="store_true", help="Output raw JSON")

    # Layer 1 Native Pass-Through Gateway CLI
    p_pt = subparsers.add_parser("passthrough", help="Layer-1 Weibo Native Pass-Through Gateway (info or raw request across /ajax/*, /webim/*, /interface/*, m.weibo.cn)")
    p_pt.add_argument("action", choices=["info", "request"], default="info", nargs="?")
    p_pt.add_argument("--method", type=str, help="HTTP method (default GET, or POST when --data given)")
    p_pt.add_argument("--path", type=str, help="Pass-through path, e.g. /ajax/statuses/config, /webim/query_primary_info.json, /api/container/getIndex")
    p_pt.add_argument("--param", action="append", help="Query param key=value (repeatable)")
    p_pt.add_argument("--data", action="append", help="Form field key=value for POST (repeatable)")
    p_pt.add_argument("--file", "-f", type=str, help="Local binary file for /interface/upload.php")
    p_pt.add_argument("--json", action="store_true", help="Output raw JSON envelope")

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit(0)

    dispatch = {
        "status": cmd_status,
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "users": cmd_users,
        "query": cmd_query,
        "logs": cmd_logs,
        "cookie": cmd_cookie,
        "publish": cmd_publish,
        "chat": cmd_chat,
        "passthrough": cmd_passthrough,
    }
    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()
