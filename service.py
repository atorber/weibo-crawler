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
def get_sqlite_stats_and_data(page=1, page_size=15, user_id=None, keyword=None):
    """Queries weibo data from sqlite database if present."""
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
            return {"exists": False, "total": 0, "items": []}

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
            return {"exists": True, "total": 0, "items": []}

        # Build query
        where_clauses = []
        params = []
        if user_id:
            where_clauses.append("user_id = ?")
            params.append(user_id)
        if keyword:
            where_clauses.append("text LIKE ?")
            params.append(f"%{keyword}%")

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
        }
    except Exception as e:
        logger.error(f"查询 SQLite 数据库出错: {e}")
        return {"exists": True, "total": 0, "error": str(e), "items": []}


# Initialize Flask App
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)
app.config["JSON_AS_ASCII"] = False
app.config["JSONIFY_MIMETYPE"] = "application/json;charset=utf-8"


# ==========================================
# Web Console HTML Routes
# ==========================================
@app.route("/")
@app.route("/console")
def console_home():
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
    return jsonify({"code": 200, "data": status_info})


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
# REST API: Cookie Check Utility
# ==========================================
@app.route("/api/cookie/check", methods=["POST"])
@app.route("/api/cookie/test", methods=["POST"])
def api_check_cookie():
    req = request.get_json(silent=True) or {}
    cookie_str = req.get("cookie")

    if not cookie_str:
        # Load from config
        _, parsed, _ = read_raw_config()
        cookie_str = parsed.get("cookie", "")

    if not cookie_str or cookie_str.strip() in ("your cookie", "YOUR_WEIBO_COOKIE_HERE"):
        return jsonify(
            {
                "code": 200,
                "valid": False,
                "message": "当前未配置 Cookie（处于免登录匿名模式）",
            }
        )

    # 1. 探针 1：测试微博网页端 (weibo.com PC)
    # 大多数用户直接从 PC 浏览器控制台复制 Cookie，因此优先检测 weibo.com
    headers_pc = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cookie": cookie_str,
        "Referer": "https://weibo.com/",
        "accept": "application/json, text/plain, */*",
    }
    try:
        r_pc = requests.get(
            "https://weibo.com/ajax/profile/detail", headers=headers_pc, timeout=6
        )
        if r_pc.status_code == 200:
            js = r_pc.json()
            if js.get("ok") == 1:
                data_pc = js.get("data", {})
                verified_url = data_pc.get("verified_url", "")
                m = re.search(r"uid=(\d+)", verified_url)
                uid = m.group(1) if m else ""
                screen_name = ""
                ip_location = data_pc.get("ip_location", "")
                if uid:
                    try:
                        r_u = requests.get(
                            f"https://weibo.com/ajax/profile/info?uid={uid}",
                            headers=headers_pc,
                            timeout=5,
                        )
                        if r_u.status_code == 200:
                            u_info = r_u.json().get("data", {}).get("user", {})
                            screen_name = u_info.get("screen_name", "")
                    except Exception:
                        pass
                name_display = screen_name or (f"UID: {uid}" if uid else "已登录用户")
                loc_display = f" ({ip_location})" if ip_location else ""
                return jsonify(
                    {
                        "code": 200,
                        "valid": True,
                        "message": f"Cookie 验证通过！登录账号：{name_display}{loc_display}",
                        "user": {"id": uid, "screen_name": name_display},
                    }
                )
    except Exception as e:
        logger.debug(f"PC probe failed: {e}")

    # 2. 探针 2：测试微博移动端 (m.weibo.cn H5)
    headers_mobile = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
        ),
        "Cookie": cookie_str,
        "Referer": "https://m.weibo.cn/",
        "accept": "application/json, text/plain, */*",
    }
    try:
        r_mob = requests.get(
            "https://m.weibo.cn/api/config", headers=headers_mobile, timeout=6
        )
        if r_mob.status_code == 200:
            js = r_mob.json()
            if js.get("data", {}).get("login") is True:
                user = js.get("data", {}).get("user", {})
                s_name = user.get("screen_name", "已登录用户")
                return jsonify(
                    {
                        "code": 200,
                        "valid": True,
                        "message": f"移动端 Cookie 验证通过！登录账号：{s_name}",
                        "user": {"id": user.get("id", ""), "screen_name": s_name},
                    }
                )
    except Exception as e:
        logger.debug(f"Mobile probe failed: {e}")

    # 3. 探针 3：测试公共只读抓取权限（针对访客 Cookie 或 SUB 凭据）
    try:
        r_pub = requests.get(
            "https://weibo.com/ajax/profile/info?custom=1669879400",
            headers=headers_pc,
            timeout=6,
        )
        if r_pub.status_code == 200 and r_pub.json().get("ok") == 1:
            return jsonify(
                {
                    "code": 200,
                    "valid": True,
                    "message": "Cookie 连通性测试通过（具备微博公共数据抓取权限，未绑定个人账号画像）",
                    "user": {"id": "", "screen_name": "有效凭证 (公共抓取)"},
                }
            )
    except Exception as e:
        logger.debug(f"Public probe failed: {e}")

    return jsonify(
        {
            "code": 200,
            "valid": False,
            "message": "Cookie 认证未通过或已过期，未能获取到有效数据权限，建议重新登录并复制最新 Cookie",
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
    keyword = request.args.get("keyword", None)

    res = get_sqlite_stats_and_data(
        page=page, page_size=page_size, user_id=user_id, keyword=keyword
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


if __name__ == "__main__":
    import argparse
    import socket

    parser = argparse.ArgumentParser(description="Weibo Crawler Web Console")
    parser.add_argument("--port", type=int, default=5001, help="Web Console Port (default: 5001)")
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
