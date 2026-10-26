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
        "cookie": cmd_cookie
    }
    dispatch[args.subcommand](args)


if __name__ == "__main__":
    main()
