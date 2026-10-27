#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Weibo Crawler Web Console & RESTful API Service.

Provides a unified web console for:
- Monitoring & controlling the crawler (Start / Stop / Restart)
- Managing target user lists (visual table, batch import/export)
- Live log streaming & searching
- Full visual configuration & JSON editor
- Cookie testing & SQLite data exploration
"""

import collections
from datetime import datetime
import json
import logging
import logging.config
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time

from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
    send_from_directory,
)
import json5
import requests

from util.browser_cookie import (
    DEFAULT_COOKIE_AUTO_CONFIG,
    extract_and_save_cookie,
    extract_browser_cookies,
    get_cookie_auto_config,
    verify_cookie_string,
)
from weibo import get_config as get_weibo_config, handle_config_renaming

BASE_DIR = os.path.split(os.path.realpath(__file__))[0] + os.sep
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_CONFIG_PATH = os.path.join(BASE_DIR, "config.json.example")
USER_ID_FILE_PATH = os.path.join(BASE_DIR, "user_id_list.txt")
LOG_DIR = os.path.join(BASE_DIR, "log")

if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)

logging_conf = os.path.join(BASE_DIR, "logging.conf")
if os.path.isfile(logging_conf):
    try:
        logging.config.fileConfig(logging_conf)
    except Exception as e:
        print(f"Warning: Failed to load logging.conf: {e}")

logger = logging.getLogger("api")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("api")


class ProcessController:
    """Manages the weibo.py crawler as a controllable subprocess."""

    def __init__(self):
        self.process = None
        self.status = "IDLE"  # IDLE, RUNNING, STOPPED, SUCCESS, FAILED
        self.start_time = None
        self.end_time = None
        self.pid = None
        self.current_user = None
        self.current_user_id = None
        self.crawled_count = 0
        self.error_message = None
        self.log_buffer = collections.deque(maxlen=3000)
        self.lock = threading.Lock()
        self.monitor_thread = None

    def start(self, user_id_list=None):
        with self.lock:
            if self.is_running():
                return False, "爬虫服务当前正在运行中，请勿重复启动"

            # 启动前检查 Cookie 有效性，若开启了自动更新且当前 Cookie 已失效，则自动从浏览器提取刷新
            try:
                _, parsed_cfg, _ = read_raw_config()
                auto_cfg = get_cookie_auto_config(parsed_cfg)
                if auto_cfg.get("enabled") and (
                    auto_cfg.get("check_before_start", True)
                    or auto_cfg.get("refresh_on_expire", True)
                ):
                    cur_cookie = parsed_cfg.get("cookie", "")
                    chk = verify_cookie_string(cur_cookie)
                    if not chk.get("valid") or not chk.get("personal_login"):
                        self.log(
                            "--- [Cookie 自动更新] 启动前检测到当前 Cookie 未登录或已失效，正在尝试从浏览器自动提取更新 ---"
                        )
                        cookie_updater.sync_now(
                            reason="启动前检测到失效自动更新",
                            only_if_expired=False,
                        )
            except Exception as e:
                logger.debug(f"Pre-start cookie check error: {e}")

            # Reset state
            self.status = "RUNNING"
            self.start_time = time.time()
            self.end_time = None
            self.current_user = None
            self.current_user_id = None
            self.error_message = None

            # Prepare environment
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"

            # If user_id_list specified for this run, we can temporarily write or pass
            cmd = [sys.executable, os.path.join(BASE_DIR, "weibo.py")]

            try:
                self.process = subprocess.Popen(
                    cmd,
                    cwd=BASE_DIR,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                self.pid = self.process.pid
                self.log(f"--- 爬虫进程已启动 (PID: {self.pid}) ---")

                # Launch background reader thread
                self.monitor_thread = threading.Thread(
                    target=self._read_output, daemon=True
                )
                self.monitor_thread.start()

                return True, f"启动成功，进程 PID: {self.pid}"
            except Exception as e:
                self.status = "FAILED"
                self.error_message = str(e)
                self.log(f"--- 启动进程失败: {e} ---")
                return False, f"启动失败: {e}"

    def stop(self):
        with self.lock:
            if not self.is_running():
                self.status = "STOPPED"
                return True, "当前没有运行中的爬虫进程"

            self.log(f"--- 收到停止信号，正在终止进程 (PID: {self.pid}) ---")
            try:
                # First try graceful SIGTERM
                self.process.terminate()
                # Wait up to 3 seconds for exit
                for _ in range(30):
                    if self.process.poll() is not None:
                        break
                    time.sleep(0.1)

                # Force kill if still alive
                if self.process.poll() is None:
                    self.process.kill()
                    self.log("--- 进程未及时响应，已执行强制终止 (kill) ---")

                self.status = "STOPPED"
                self.end_time = time.time()
                self.log("--- 爬虫进程已停止 ---")
                return True, "爬虫已成功停止"
            except Exception as e:
                self.log(f"--- 终止进程时出错: {e} ---")
                return False, f"终止进程失败: {e}"

    def restart(self, user_id_list=None):
        self.stop()
        time.sleep(0.5)
        return self.start(user_id_list)

    def is_running(self):
        if self.process is not None:
            if self.process.poll() is None:
                return True
            else:
                # Process has terminated
                code = self.process.returncode
                if self.status == "RUNNING":
                    if code == 0:
                        self.status = "SUCCESS"
                    elif code in (-15, -9, 15, 9):
                        self.status = "STOPPED"
                    else:
                        self.status = "FAILED"
                        self.error_message = f"进程异常退出，退出码: {code}"
                    self.end_time = time.time()
        return False

    def _read_output(self):
        try:
            for line in iter(self.process.stdout.readline, ""):
                if not line:
                    break
                clean_line = line.rstrip()
                self.log(clean_line)
                self._parse_line(clean_line)
            self.process.stdout.close()
        except Exception as e:
            self.log(f"读取进程输出异常: {e}")
        finally:
            self.is_running()  # update exit code and status

    def _parse_line(self, line):
        # Detect current user or crawling events
        # e.g., "开始爬取用户: xxx" or "用户: xxx"
        m = re.search(r"用户[：:]\s*([^\s,]+)", line)
        if m:
            self.current_user = m.group(1)
        # e.g., count increments
        if "共采集到" in line or "爬取完成" in line:
            self.crawled_count += 1
        # Detect crawler hot cookie refresh events
        if "[Cookie 自动更新] 热更新成功" in line:
            try:
                cookie_updater.record_runtime_refresh(line)
            except Exception:
                pass

    def log(self, text):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{now}] {text}"
        self.log_buffer.append(entry)

    def get_status(self):
        running = self.is_running()
        duration = 0
        if self.start_time:
            if running:
                duration = int(time.time() - self.start_time)
            elif self.end_time:
                duration = int(self.end_time - self.start_time)

        return {
            "status": self.status,
            "is_running": running,
            "pid": self.pid if running else None,
            "start_time": (
                datetime.fromtimestamp(self.start_time).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if self.start_time
                else None
            ),
            "end_time": (
                datetime.fromtimestamp(self.end_time).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                if self.end_time
                else None
            ),
            "duration": duration,
            "current_user": self.current_user if running else None,
            "error_message": self.error_message,
        }

    def get_logs(self, limit=300, level="ALL", keyword=""):
        lines = list(self.log_buffer)

        # If log buffer in memory is small, try to read from log/all.log as well
        all_log_path = os.path.join(LOG_DIR, "all.log")
        if len(lines) < limit and os.path.isfile(all_log_path):
            try:
                with open(all_log_path, "r", encoding="utf-8", errors="ignore") as f:
                    file_lines = f.readlines()
                    combined = [
                        line.rstrip() for line in file_lines[-limit:]
                    ] + lines
                    # deduplicate roughly while preserving order
                    seen = set()
                    unique_lines = []
                    for item in combined:
                        if item not in seen:
                            seen.add(item)
                            unique_lines.append(item)
                    lines = unique_lines
            except Exception:
                pass

        if level != "ALL":
            lines = [l for l in lines if level in l]
        if keyword:
            kw = keyword.lower()
            lines = [l for l in lines if kw in l.lower()]

        return lines[-limit:]

    def clear_logs(self):
        self.log_buffer.clear()
        return True


controller = ProcessController()


class CookieAutoUpdater:
    """Background daemon that periodically syncs browser cookies or auto-updates on expiration."""

    def __init__(self):
        self.last_sync_time = None
        self.last_sync_ts = time.time()
        self.last_sync_status = "IDLE"  # IDLE, SUCCESS, FAILED
        self.last_sync_message = "尚未触发自动同步"
        self.last_browser = None
        self.sync_count = 0
        self.lock = threading.Lock()
        self.worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True
        )
        self.worker_thread.start()

    def record_runtime_refresh(self, log_line):
        with self.lock:
            self.last_sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_sync_ts = time.time()
            self.last_sync_status = "SUCCESS"
            self.last_sync_message = f"爬虫运行中触发热更新: {log_line}"
            self.sync_count += 1

    def sync_now(self, reason="周期同步", only_if_expired=False):
        with self.lock:
            try:
                _, parsed, _ = read_raw_config()
                auto_cfg = get_cookie_auto_config(parsed)
                browser = auto_cfg.get("browser", "auto")

                if only_if_expired:
                    cur_cookie = parsed.get("cookie", "")
                    chk = verify_cookie_string(cur_cookie)
                    if chk.get("valid") and chk.get("personal_login"):
                        self.last_sync_time = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        self.last_sync_ts = time.time()
                        self.last_sync_status = "SUCCESS"
                        self.last_sync_message = (
                            f"[{reason}] 巡检通过，当前 Cookie 有效 ({chk.get('message', '')})"
                        )
                        return {
                            "success": True,
                            "synced": False,
                            "valid": True,
                            "message": self.last_sync_message,
                        }

                res = extract_and_save_cookie(browser_name=browser)
                self.last_sync_time = res.get(
                    "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                self.last_sync_ts = time.time()
                self.last_browser = res.get("browser")

                if res.get("success") and res.get("valid"):
                    self.last_sync_status = "SUCCESS"
                    self.sync_count += 1
                    self.last_sync_message = (
                        f"[{reason}] {res.get('message', '同步成功')}"
                    )
                    controller.log(
                        f"🔄 [Cookie 自动更新] {self.last_sync_message}"
                    )
                else:
                    self.last_sync_status = "FAILED"
                    self.last_sync_message = (
                        f"[{reason}] 提取或验证未通过: {res.get('message', '')}"
                    )
                    controller.log(
                        f"⚠️ [Cookie 自动更新] {self.last_sync_message}"
                    )

                return res
            except Exception as e:
                self.last_sync_time = datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                self.last_sync_ts = time.time()
                self.last_sync_status = "FAILED"
                self.last_sync_message = f"[{reason}] 自动更新异常: {e}"
                return {
                    "success": False,
                    "valid": False,
                    "message": self.last_sync_message,
                }

    def _worker_loop(self):
        while True:
            time.sleep(20)
            try:
                _, parsed, _ = read_raw_config()
                auto_cfg = get_cookie_auto_config(parsed)
                if not auto_cfg.get("enabled"):
                    continue

                interval_min = auto_cfg.get("interval_minutes", 0)
                if interval_min > 0:
                    elapsed = time.time() - self.last_sync_ts
                    if elapsed >= interval_min * 60:
                        self.sync_now(
                            reason=f"定时周期更新 (每 {interval_min} 分钟)",
                            only_if_expired=False,
                        )
            except Exception as e:
                logger.debug(f"CookieAutoUpdater loop error: {e}")

    def get_status(self):
        _, parsed, _ = read_raw_config()
        auto_cfg = get_cookie_auto_config(parsed)
        next_sync_in = None
        if auto_cfg.get("enabled") and auto_cfg.get("interval_minutes", 0) > 0:
            rem = int(
                auto_cfg["interval_minutes"] * 60
                - (time.time() - self.last_sync_ts)
            )
            next_sync_in = max(0, rem)

        return {
            "last_sync_time": self.last_sync_time,
            "last_sync_status": self.last_sync_status,
            "last_sync_message": self.last_sync_message,
            "last_browser": self.last_browser,
            "sync_count": self.sync_count,
            "next_sync_in_seconds": next_sync_in,
        }


cookie_updater = CookieAutoUpdater()


def get_schedule_config(parsed_config=None):
    """Returns normalized schedule_config dictionary for continuous monitoring."""
    if parsed_config is None:
        _, parsed_config, _ = read_raw_config()
    raw_sched = parsed_config.get("schedule_config")
    if not isinstance(raw_sched, dict):
        raw_sched = {}
    enabled = bool(raw_sched.get("enabled", False))
    try:
        interval_minutes = max(1, int(raw_sched.get("interval_minutes", 30)))
    except (ValueError, TypeError):
        interval_minutes = 30
    return {
        "enabled": enabled,
        "interval_minutes": interval_minutes,
    }


class CrawlScheduler:
    """Background daemon that continuously monitors target bloggers by scheduling incremental crawls."""

    def __init__(self):
        self.last_reference_ts = time.time()
        self.last_trigger_time = None
        self.run_count = 0
        self.lock = threading.Lock()
        self.worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True
        )
        self.worker_thread.start()

    def reset_timer(self):
        with self.lock:
            self.last_reference_ts = time.time()

    def _worker_loop(self):
        while True:
            time.sleep(5)
            try:
                _, parsed, _ = read_raw_config()
                sched_cfg = get_schedule_config(parsed)
                if not sched_cfg.get("enabled"):
                    self.last_reference_ts = time.time()
                    continue

                # If crawler is currently running, reset reference timestamp so interval starts after completion
                if controller.is_running():
                    self.last_reference_ts = time.time()
                    continue

                interval_sec = sched_cfg["interval_minutes"] * 60
                elapsed = time.time() - self.last_reference_ts
                if elapsed >= interval_sec:
                    with self.lock:
                        self.last_reference_ts = time.time()
                        self.run_count += 1
                        self.last_trigger_time = datetime.now().strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                    controller.log(
                        f"⏰ [持续监听调度] 已到达定时巡检周期 (每 {sched_cfg['interval_minutes']} 分钟)，自动启动第 {self.run_count} 轮增量抓取..."
                    )
                    controller.start()
            except Exception as e:
                logger.debug(f"CrawlScheduler loop error: {e}")

    def get_status(self):
        _, parsed, _ = read_raw_config()
        sched_cfg = get_schedule_config(parsed)
        running = controller.is_running()
        next_run_in = None
        if sched_cfg.get("enabled") and not running:
            rem = int(
                sched_cfg["interval_minutes"] * 60
                - (time.time() - self.last_reference_ts)
            )
            next_run_in = max(0, rem)

        return {
            "enabled": sched_cfg["enabled"],
            "interval_minutes": sched_cfg["interval_minutes"],
            "last_trigger_time": self.last_trigger_time,
            "run_count": self.run_count,
            "next_run_in_seconds": next_run_in,
        }


crawl_scheduler = CrawlScheduler()

# Configuration helper functions
def read_raw_config():
    """Reads raw config string and parsed object."""
    target_path = (
        CONFIG_PATH if os.path.isfile(CONFIG_PATH) else EXAMPLE_CONFIG_PATH
    )
    if not os.path.isfile(target_path):
        return "", {}

    with open(target_path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        parsed = json5.loads(content)
    except Exception:
        try:
            parsed = json.loads(content)
        except Exception:
            parsed = {}

    return content, parsed, target_path == CONFIG_PATH


def save_config_content(content_str):
    """Validates and saves config string to config.json."""
    # Verify that it is valid JSON / JSON5
    try:
        parsed = json5.loads(content_str)
    except Exception as e:
        raise ValueError(f"配置文件语法有误 (JSON5解析失败): {e}")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(content_str)

    return parsed


# User ID list helpers
def get_user_targets():
    """Reads user target list from user_id_list.txt or config.json."""
    users = []
    if os.path.isfile(USER_ID_FILE_PATH):
        with open(USER_ID_FILE_PATH, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if parts and parts[0].isdigit():
                    uid = parts[0]
                    name = parts[1] if len(parts) > 1 else ""
                    since = parts[2] if len(parts) > 2 else ""
                    query = parts[3] if len(parts) > 3 else ""
                    users.append(
                        {
                            "id": uid,
                            "screen_name": name,
                            "since_date": since,
                            "query": query,
                            "line_num": idx,
                        }
                    )
    else:
        # Fall back to config.json's user_id_list
        _, parsed, _ = read_raw_config()
        uid_list = parsed.get("user_id_list", [])
        if isinstance(uid_list, list):
            for u in uid_list:
                users.append(
                    {
                        "id": str(u),
                        "screen_name": "",
                        "since_date": "",
                        "query": "",
                        "line_num": 0,
                    }
                )
    return users


def save_user_targets(users):
    """Saves user list to user_id_list.txt."""
    lines = []
    for u in users:
        parts = [str(u["id"])]
        if u.get("screen_name"):
            parts.append(str(u["screen_name"]))
        if u.get("since_date"):
            parts.append(str(u["since_date"]))
        if u.get("query"):
            parts.append(str(u["query"]))
        lines.append(" ".join(parts))

    with open(USER_ID_FILE_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


# SQLite Data query helper
def get_sqlite_stats_and_data(
    page=1,
    page_size=15,
    user_id=None,
    keyword=None,
    start_date=None,
    end_date=None,
):
    """Queries weibo data from sqlite database if present with user, date range, and keyword filters."""
    _, parsed, _ = read_raw_config()
    db_path = parsed.get("sqlite_db_path", os.path.join(BASE_DIR, "weibodata.db"))
    if not os.path.isabs(db_path):
        db_path = os.path.join(BASE_DIR, db_path)

    if not os.path.isfile(db_path):
        # try checking weibo/weibodata.db
        alt_path = os.path.join(BASE_DIR, "weibo", "weibodata.db")
        if os.path.isfile(alt_path):
            db_path = alt_path
        else:
            return {"exists": False, "total": 0, "items": [], "available_users": []}

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Check tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='weibo'"
        )
        if not cursor.fetchone():
            conn.close()
            return {"exists": True, "total": 0, "items": [], "available_users": []}

        # Retrieve available users for filter dropdown
        available_users = []
        try:
            cursor.execute(
                "SELECT DISTINCT user_id, screen_name FROM weibo WHERE user_id IS NOT NULL AND user_id != '' ORDER BY screen_name"
            )
            available_users = [
                {"user_id": str(r["user_id"]), "screen_name": str(r["screen_name"] or r["user_id"])}
                for r in cursor.fetchall()
            ]
        except Exception as e:
            logger.warning(f"Failed to fetch available users from weibo table: {e}")

        # Build query
        where_clauses = []
        params = []
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(str(user_id).strip())

        if keyword:
            kw_clean = str(keyword).strip()
            where_clauses.append("(text LIKE ? OR screen_name LIKE ?)")
            params.append(f"%{kw_clean}%")
            params.append(f"%{kw_clean}%")

        if start_date:
            sd_clean = str(start_date).strip()
            if len(sd_clean) == 10:
                sd_clean += " 00:00:00"
            where_clauses.append("created_at >= ?")
            params.append(sd_clean)

        if end_date:
            ed_clean = str(end_date).strip()
            if len(ed_clean) == 10:
                ed_clean += " 23:59:59"
            where_clauses.append("created_at <= ?")
            params.append(ed_clean)

        where_sql = (
            f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        )

        # Count total
        count_sql = f"SELECT COUNT(*) FROM weibo {where_sql}"
        cursor.execute(count_sql, params)
        total = cursor.fetchone()[0]

        # Query items
        offset = (page - 1) * page_size
        query_sql = f"SELECT * FROM weibo {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        cursor.execute(query_sql, params + [page_size, offset])
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()

        return {
            "exists": True,
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": rows,
            "available_users": available_users,
        }
    except Exception as e:
        logger.error(f"查询 SQLite 数据库出错: {e}")
        return {"exists": True, "total": 0, "error": str(e), "items": [], "available_users": []}


# Initialize Flask App
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.config["JSON_AS_ASCII"] = False
app.config["JSONIFY_MIMETYPE"] = "application/json;charset=utf-8"

@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ==========================================
# Web Console HTML Routes (Independent Routes for Sidebar Menus)
# ==========================================
@app.route("/")
@app.route("/console")
@app.route("/dashboard")
@app.route("/targets")
@app.route("/settings")
@app.route("/output")
@app.route("/logs")
@app.route("/data")
@app.route("/api-docs")
@app.route("/docs")
@app.route("/console/<path:subpath>")
def console_home(subpath=None):
    return render_template("index.html")


# ==========================================
# REST API: Status & Service Controls
# ==========================================
@app.route("/api/status", methods=["GET"])
def api_status():
    status_info = controller.get_status()
    # Add extra overview metrics
    users = get_user_targets()
    data_info = get_sqlite_stats_and_data(page=1, page_size=1)
    status_info["metrics"] = {
        "user_count": len(users),
        "total_weibos": data_info.get("total", 0),
        "db_connected": data_info.get("exists", False),
        "log_entries_count": len(controller.log_buffer),
    }
    status_info["schedule"] = crawl_scheduler.get_status()
    return jsonify({"code": 200, "data": status_info})


@app.route("/api/schedule", methods=["GET", "POST"])
def api_schedule():
    if request.method == "GET":
        _, parsed, _ = read_raw_config()
        return jsonify(
            {
                "code": 200,
                "config": get_schedule_config(parsed),
                "status": crawl_scheduler.get_status(),
            }
        )

    req = request.get_json(silent=True) or {}
    _, parsed, _ = read_raw_config()
    cur_sched = get_schedule_config(parsed)

    if "enabled" in req:
        cur_sched["enabled"] = bool(req["enabled"])
    if "interval_minutes" in req:
        try:
            cur_sched["interval_minutes"] = max(
                1, int(req["interval_minutes"])
            )
        except (ValueError, TypeError):
            pass

    parsed["schedule_config"] = cur_sched
    try:
        new_raw = json.dumps(parsed, indent=4, ensure_ascii=False)
        save_config_content(new_raw)
    except Exception as e:
        return (
            jsonify(
                {"code": 400, "success": False, "message": f"保存失败: {e}"}
            ),
            400,
        )

    crawl_scheduler.reset_timer()
    started_now = False
    if (
        cur_sched["enabled"]
        and req.get("run_immediately")
        and not controller.is_running()
    ):
        ok, _ = controller.start()
        started_now = ok

    state_msg = (
        f"已开启持续监听模式（每 {cur_sched['interval_minutes']} 分钟自动巡检增量微博）"
        if cur_sched["enabled"]
        else "已关闭持续监听模式（恢复单次运行）"
    )
    controller.log(f"⏰ [持续监听配置] {state_msg}")

    return jsonify(
        {
            "code": 200,
            "success": True,
            "started_now": started_now,
            "message": state_msg,
            "config": cur_sched,
            "status": crawl_scheduler.get_status(),
        }
    )


@app.route("/api/service/start", methods=["POST"])
def api_service_start():
    req_data = request.get_json(silent=True) or {}
    user_id_list = req_data.get("user_id_list")
    ok, msg = controller.start(user_id_list)
    return jsonify(
        {
            "code": 200 if ok else 400,
            "success": ok,
            "message": msg,
            "data": controller.get_status(),
        }
    )


@app.route("/api/service/stop", methods=["POST"])
def api_service_stop():
    ok, msg = controller.stop()
    return jsonify(
        {
            "code": 200 if ok else 400,
            "success": ok,
            "message": msg,
            "data": controller.get_status(),
        }
    )


@app.route("/api/service/restart", methods=["POST"])
def api_service_restart():
    req_data = request.get_json(silent=True) or {}
    user_id_list = req_data.get("user_id_list")
    ok, msg = controller.restart(user_id_list)
    return jsonify(
        {
            "code": 200 if ok else 400,
            "success": ok,
            "message": msg,
            "data": controller.get_status(),
        }
    )


# ==========================================
# REST API: Logs
# ==========================================
@app.route("/api/logs", methods=["GET"])
def api_get_logs():
    limit = int(request.args.get("limit", 200))
    level = request.args.get("level", "ALL")
    keyword = request.args.get("keyword", "")
    lines = controller.get_logs(limit=limit, level=level, keyword=keyword)
    return jsonify({"code": 200, "total": len(lines), "logs": lines})


@app.route("/api/logs/clear", methods=["POST"])
def api_clear_logs():
    controller.clear_logs()
    return jsonify({"code": 200, "message": "内存日志已清空"})


# ==========================================
# REST API: Configuration Management
# ==========================================
@app.route("/api/config", methods=["GET"])
def api_get_config():
    raw_str, parsed, is_custom = read_raw_config()
    return jsonify(
        {
            "code": 200,
            "raw": raw_str,
            "parsed": parsed,
            "is_custom_config": is_custom,
        }
    )


@app.route("/api/config", methods=["POST"])
def api_save_config():
    req_data = request.get_json()
    if not req_data:
        return jsonify({"code": 400, "message": "请求体为空"}), 400

    raw_content = req_data.get("raw")
    parsed_content = req_data.get("parsed")

    try:
        if raw_content is not None:
            parsed = save_config_content(raw_content)
        elif parsed_content is not None:
            # Format nicely as JSON string
            content_str = json.dumps(parsed_content, ensure_ascii=False, indent=4)
            parsed = save_config_content(content_str)
        else:
            return jsonify({"code": 400, "message": "缺少 raw 或 parsed 参数"}), 400

        return jsonify(
            {
                "code": 200,
                "message": "配置保存成功",
                "parsed": parsed,
            }
        )
    except Exception as e:
        return jsonify({"code": 400, "message": str(e)}), 400


# ==========================================
# REST API: User Target Management
# ==========================================
@app.route("/api/users", methods=["GET"])
def api_get_users():
    users = get_user_targets()
    return jsonify({"code": 200, "total": len(users), "data": users})


@app.route("/api/users", methods=["POST"])
def api_add_or_update_user():
    req = request.get_json() or {}
    uid = str(req.get("id", "")).strip()
    if not uid or not uid.isdigit():
        return jsonify({"code": 400, "message": "无效的用户 ID，必须为纯数字"}), 400

    screen_name = str(req.get("screen_name", "")).strip()
    since_date = str(req.get("since_date", "")).strip()
    query = str(req.get("query", "")).strip()

    users = get_user_targets()
    # Check if exists
    existing = False
    for u in users:
        if u["id"] == uid:
            u["screen_name"] = screen_name
            u["since_date"] = since_date
            u["query"] = query
            existing = True
            break
    if not existing:
        users.append(
            {
                "id": uid,
                "screen_name": screen_name,
                "since_date": since_date,
                "query": query,
            }
        )

    save_user_targets(users)
    return jsonify(
        {
            "code": 200,
            "message": "更新成功" if existing else "添加用户成功",
            "data": users,
        }
    )


@app.route("/api/users/<user_id>", methods=["DELETE"])
def api_delete_user(user_id):
    users = get_user_targets()
    new_users = [u for u in users if u["id"] != str(user_id)]
    if len(new_users) == len(users):
        return jsonify({"code": 404, "message": "未找到指定用户"}), 404

    save_user_targets(new_users)
    return jsonify({"code": 200, "message": "删除成功", "data": new_users})


@app.route("/api/users/import", methods=["POST"])
def api_import_users():
    req = request.get_json() or {}
    raw_text = req.get("text", "")
    mode = req.get("mode", "append")  # "append" or "overwrite"

    current_users = [] if mode == "overwrite" else get_user_targets()
    existing_ids = {u["id"] for u in current_users}

    count = 0
    for line in raw_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts and parts[0].isdigit():
            uid = parts[0]
            name = parts[1] if len(parts) > 1 else ""
            since = parts[2] if len(parts) > 2 else ""
            query = parts[3] if len(parts) > 3 else ""

            if uid in existing_ids:
                # Update existing
                for u in current_users:
                    if u["id"] == uid:
                        u["screen_name"] = name or u["screen_name"]
                        u["since_date"] = since or u["since_date"]
                        u["query"] = query or u["query"]
                        break
            else:
                current_users.append(
                    {
                        "id": uid,
                        "screen_name": name,
                        "since_date": since,
                        "query": query,
                    }
                )
                existing_ids.add(uid)
                count += 1

    save_user_targets(current_users)
    return jsonify(
        {
            "code": 200,
            "message": f"成功导入/更新用户，新增 {count} 个目标",
            "total": len(current_users),
        }
    )


# ==========================================
# REST API: Cookie Check & Auto-Update Utility
# ==========================================
@app.route("/api/cookie/check", methods=["POST"])
@app.route("/api/cookie/test", methods=["POST"])
def api_check_cookie():
    req = request.get_json(silent=True) or {}
    cookie_str = req.get("cookie")

    _, parsed, _ = read_raw_config()
    if not cookie_str:
        cookie_str = parsed.get("cookie", "")

    result = verify_cookie_string(cookie_str)
    auto_cfg = get_cookie_auto_config(parsed)

    # 如果当前未传入特定测试字符串、且检测出配置文件中的 Cookie 已失效，并且用户开启了失效自动更新：
    if (
        not req.get("cookie")
        and not result.get("valid", False)
        and auto_cfg.get("enabled")
        and auto_cfg.get("refresh_on_expire", True)
    ):
        sync_res = cookie_updater.sync_now(
            reason="连通性探针发现 Cookie 失效自动重提", only_if_expired=False
        )
        if sync_res.get("success") and sync_res.get("valid"):
            return jsonify(
                {
                    "code": 200,
                    "valid": True,
                    "auto_refreshed": True,
                    "message": f"原 Cookie 已失效，已自动从 {sync_res.get('browser')} 提取并恢复！{sync_res.get('message', '')}",
                    "user": sync_res.get("user", {}),
                    "auto_config": auto_cfg,
                    "auto_status": cookie_updater.get_status(),
                }
            )

    return jsonify(
        {
            "code": 200,
            "valid": result.get("valid", False),
            "message": result.get("message", ""),
            "user": result.get("user", {}),
            "auto_config": auto_cfg,
            "auto_status": cookie_updater.get_status(),
        }
    )


@app.route("/api/cookie/browsers", methods=["GET"])
def api_cookie_browsers():
    try:
        import rookiepy

        available = True
    except ImportError:
        available = False

    browsers = [
        {"id": "auto", "name": "自动探测已登录浏览器 (推荐)"},
        {"id": "chrome", "name": "Google Chrome"},
        {"id": "edge", "name": "Microsoft Edge"},
        {"id": "firefox", "name": "Mozilla Firefox"},
        {"id": "safari", "name": "Apple Safari"},
        {"id": "brave", "name": "Brave Browser"},
        {"id": "arc", "name": "Arc Browser"},
        {"id": "opera", "name": "Opera Browser"},
    ]
    return jsonify(
        {
            "code": 200,
            "rookiepy_available": available,
            "browsers": browsers,
        }
    )


@app.route("/api/cookie/import_browser", methods=["POST"])
def api_cookie_import_browser():
    # 安全保护：只允许本地请求读取本地浏览器 Cookie
    client_ip = request.remote_addr or ""
    if client_ip not in ("127.0.0.1", "::1", "localhost"):
        return (
            jsonify(
                {
                    "code": 403,
                    "success": False,
                    "message": "为了安全起见，从本地浏览器提取 Cookie 仅允许本地访问 (localhost) 调用",
                }
            ),
            403,
        )

    req = request.get_json(silent=True) or {}
    browser = req.get("browser", "auto")
    auto_save = req.get("save", False)

    cookie_str, err_msg, detected_browser = extract_browser_cookies(browser)
    if err_msg or not cookie_str:
        return jsonify(
            {
                "code": 400,
                "success": False,
                "message": err_msg or "未能从浏览器提取到有效微博 Cookie",
            }
        )

    # 校验提取出的 Cookie
    check_result = verify_cookie_string(cookie_str)

    if auto_save:
        try:
            _, parsed, _ = read_raw_config()
            parsed["cookie"] = cookie_str
            new_raw = json.dumps(parsed, indent=4, ensure_ascii=False)
            save_config_content(new_raw)
        except Exception as e:
            logger.error(f"Auto-saving cookie to config failed: {e}")

    return jsonify(
        {
            "code": 200,
            "success": True,
            "browser": detected_browser or browser,
            "cookie": cookie_str,
            "valid": check_result.get("valid", False),
            "user": check_result.get("user", {}),
            "message": f"成功从 {detected_browser or browser} 提取微博 Cookie！"
            + (
                " " + check_result.get("message", "")
                if check_result.get("valid")
                else ""
            ),
        }
    )


@app.route("/api/cookie/auto_config", methods=["GET", "POST"])
def api_cookie_auto_config():
    if request.method == "GET":
        _, parsed, _ = read_raw_config()
        return jsonify(
            {
                "code": 200,
                "config": get_cookie_auto_config(parsed),
                "status": cookie_updater.get_status(),
            }
        )

    req = request.get_json(silent=True) or {}
    _, parsed, _ = read_raw_config()
    cur_auto = get_cookie_auto_config(parsed)

    for key in (
        "enabled",
        "browser",
        "refresh_on_expire",
        "check_before_start",
        "interval_minutes",
    ):
        if key in req:
            cur_auto[key] = req[key]

    cur_auto = get_cookie_auto_config({"cookie_auto_config": cur_auto})
    parsed["cookie_auto_config"] = cur_auto

    try:
        new_raw = json.dumps(parsed, indent=4, ensure_ascii=False)
        save_config_content(new_raw)
    except Exception as e:
        return (
            jsonify({"code": 400, "success": False, "message": f"保存失败: {e}"}),
            400,
        )

    sync_res = None
    if req.get("trigger_now"):
        sync_res = cookie_updater.sync_now(
            reason="手动触发立即同步", only_if_expired=False
        )

    return jsonify(
        {
            "code": 200,
            "success": True,
            "message": "Cookie 自动更新策略已保存",
            "config": cur_auto,
            "status": cookie_updater.get_status(),
            "sync_result": sync_res,
        }
    )



# ==========================================
# REST API: Data Preview
# ==========================================
@app.route("/api/data/weibos", methods=["GET"])
def api_data_weibos():
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 10))
    user_id = request.args.get("user_id", None)
    if user_id:
        user_id = user_id.strip()
        if not user_id or user_id.lower() == "all":
            user_id = None

    keyword = request.args.get("keyword", None)
    if keyword:
        keyword = keyword.strip()
        if not keyword:
            keyword = None

    start_date = request.args.get("start_date", None)
    if start_date:
        start_date = start_date.strip()
        if not start_date:
            start_date = None

    end_date = request.args.get("end_date", None)
    if end_date:
        end_date = end_date.strip()
        if not end_date:
            end_date = None

    res = get_sqlite_stats_and_data(
        page=page,
        page_size=page_size,
        user_id=user_id,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
    )
    return jsonify({"code": 200, "data": res})


# ==========================================
# Legacy API Endpoints (100% Backwards Compatible)
# ==========================================
@app.route("/refresh", methods=["POST"])
def legacy_refresh():
    data = request.get_json(silent=True) or {}
    user_id_list = data.get("user_id_list")
    ok, msg = controller.start(user_id_list)
    return (
        jsonify(
            {
                "task_id": str(controller.pid),
                "status": "Task started" if ok else "Task already running",
                "state": controller.status,
                "progress": 0 if ok else 50,
                "user_id_list": user_id_list,
            }
        ),
        202 if ok else 409,
    )


@app.route("/task/<task_id>", methods=["GET"])
def legacy_task(task_id):
    st = controller.get_status()
    return jsonify(
        {
            "state": (
                "PROGRESS"
                if st["is_running"]
                else (
                    "SUCCESS"
                    if st["status"] == "SUCCESS"
                    else ("FAILED" if st["status"] == "FAILED" else "IDLE")
                )
            ),
            "progress": 50 if st["is_running"] else 100,
            "result": {"status": st["status"]},
        }
    )


@app.route("/weibos", methods=["GET"])
def legacy_weibos():
    data = get_sqlite_stats_and_data(page=1, page_size=100)
    return jsonify(data.get("items", [])), 200


@app.route("/weibos/<weibo_id>", methods=["GET"])
def legacy_weibo_detail(weibo_id):
    data = get_sqlite_stats_and_data(page=1, page_size=1000)
    for w in data.get("items", []):
        if str(w.get("id")) == str(weibo_id):
            return jsonify(w), 200
    return jsonify({"error": "Weibo not found"}), 404


# -------------------------------------------------------------
# Connectivity Test Endpoints (MySQL, MongoDB, Webhook)
# -------------------------------------------------------------
@app.route("/api/test/mysql", methods=["POST"])
def api_test_mysql():
    req = request.get_json(silent=True) or {}
    host = str(req.get("host", "localhost")).strip()
    port = int(req.get("port", 3306))
    user = str(req.get("user", "root")).strip()
    password = str(req.get("password", "")).strip()
    charset = str(req.get("charset", "utf8mb4")).strip() or "utf8mb4"

    if not host or not user:
        return jsonify({"code": 400, "valid": False, "message": "主机地址和用户名不能为空"}), 200

    try:
        import pymysql
    except ImportError:
        return jsonify({"code": 500, "valid": False, "message": "服务器环境缺少 PyMySQL 依赖，请先安装"}), 200

    import time
    start_time = time.time()
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            charset=charset,
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5
        )
        with conn.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            ver = cursor.fetchone()
            version_str = ver[0] if ver else "未知"
        conn.close()
        latency = int((time.time() - start_time) * 1000)
        return jsonify({
            "code": 200,
            "valid": True,
            "message": f"连接成功！MySQL 版本: {version_str} (耗时 {latency}ms)"
        })
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return jsonify({
            "code": 200,
            "valid": False,
            "message": f"连接失败 ({latency}ms): {str(e)}"
        })


@app.route("/api/test/mongodb", methods=["POST"])
def api_test_mongodb():
    req = request.get_json(silent=True) or {}
    uri = str(req.get("uri", "")).strip()

    if not uri:
        return jsonify({"code": 400, "valid": False, "message": "MongoDB 连接 URI 不能为空"}), 200

    try:
        import pymongo
    except ImportError:
        return jsonify({"code": 500, "valid": False, "message": "服务器环境缺少 pymongo 依赖，请先安装"}), 200

    import time
    start_time = time.time()
    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=4000, connectTimeoutMS=4000)
        client.admin.command('ping')
        info = client.server_info()
        version_str = info.get("version", "未知")
        client.close()
        latency = int((time.time() - start_time) * 1000)
        return jsonify({
            "code": 200,
            "valid": True,
            "message": f"连接成功！MongoDB 版本: {version_str} (耗时 {latency}ms)"
        })
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return jsonify({
            "code": 200,
            "valid": False,
            "message": f"连接失败 ({latency}ms): {str(e)}"
        })


@app.route("/api/test/webhook", methods=["POST"])
def api_test_webhook():
    req = request.get_json(silent=True) or {}
    url = str(req.get("url", "")).strip()
    token = str(req.get("token", "")).strip()

    if not url:
        return jsonify({"code": 400, "valid": False, "message": "Webhook URL 不能为空"}), 200

    if not (url.startswith("http://") or url.startswith("https://")):
        return jsonify({"code": 400, "valid": False, "message": "Webhook URL 必须以 http:// 或 https:// 开头"}), 200

    import time
    import requests
    start_time = time.time()
    try:
        headers = {
            "User-Agent": "weibo-crawler-webhook-test/1.0",
            "Content-Type": "application/json"
        }
        if token:
            headers["Authorization"] = f"Bearer {token}" if not token.lower().startswith("bearer ") else token

        test_payload = {
            "event": "ping",
            "message": "Weibo Crawler Webhook connectivity test",
            "timestamp": int(start_time)
        }
        resp = requests.post(url, json=test_payload, headers=headers, timeout=6)
        latency = int((time.time() - start_time) * 1000)
        status_code = resp.status_code
        reason = resp.reason or ""

        if 200 <= status_code < 300:
            return jsonify({
                "code": 200,
                "valid": True,
                "message": f"响应成功！HTTP 状态码: {status_code} {reason} (耗时 {latency}ms)"
            })
        else:
            return jsonify({
                "code": 200,
                "valid": False,
                "message": f"收到非成功响应：HTTP 状态码 {status_code} {reason} (耗时 {latency}ms)"
            })
    except requests.exceptions.Timeout:
        return jsonify({
            "code": 200,
            "valid": False,
            "message": "请求超时（超过 6 秒未收到响应），请检查接口服务与网络"
        })
    except Exception as e:
        latency = int((time.time() - start_time) * 1000)
        return jsonify({
            "code": 200,
            "valid": False,
            "message": f"请求异常 ({latency}ms): {str(e)}"
        })





if __name__ == "__main__":
    import argparse
    import socket

    parser = argparse.ArgumentParser(description="Weibo Crawler Web Console")
    parser.add_argument("--port", type=int, default=15001, help="Web Console Port (default: 15001)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Web Console Host")
    args = parser.parse_args()

    port = args.port

    def is_port_in_use(p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', p)) == 0

    if is_port_in_use(port):
        for candidate in range(port + 1, port + 20):
            if not is_port_in_use(candidate):
                print(f"⚠️ 提示: 端口 {port} 已被占用，已自动切换到空闲端口 {candidate}")
                port = candidate
                break

    print(f"\n=======================================================")
    print(f"🚀 Weibo Crawler Web 控制台已启动!")
    print(f"🔗 本地访问地址: http://127.0.0.1:{port}")
    print(f"=======================================================\n")
    logger.info(f"Weibo Crawler Web 控制台已启动: http://127.0.0.1:{port}")
    app.run(host=args.host, port=port, debug=False, threaded=True)
