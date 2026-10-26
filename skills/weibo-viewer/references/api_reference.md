# Weibo Console REST API & Database Reference

This document provides a detailed reference for all API endpoints and database tables available in the Weibo Crawler system.

---

## 1. REST API Endpoints Overview

Default Base URL: `http://127.0.0.1:15001` (can be configured via `WEIBO_API_BASE` or `PORT`).

| Method | Endpoint | Description | Key Parameters / Payload |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/status` | Current service and crawler status | None |
| `POST` | `/api/service/start` | Start background crawler task | `{"user_id_list": [], "since_date": ""}` |
| `POST` | `/api/service/stop` | Stop running crawler task | None |
| `POST` | `/api/service/restart` | Restart Flask service and crawler process | None |
| `GET` | `/api/users` | List all configured target bloggers | None |
| `POST` | `/api/users` | Add target blogger(s) | `{"user_id": "1669879400"}` or batch list |
| `DELETE` | `/api/users/<user_id>` | Delete target blogger | None |
| `POST` | `/api/users/import` | Import bloggers from text | `{"text": "..."}` |
| `GET` | `/api/config` | Read current `config.json` | None |
| `POST` | `/api/config` | Save and reload `config.json` | JSON configuration object |
| `GET` | `/api/data/weibos` | Query and filter crawled Weibo posts | `page`, `page_size`, `user_id`, `keyword`, `start_date`, `end_date` |
| `GET` | `/api/logs` | Fetch recent log records | `limit` (default 100) |
| `POST` | `/api/logs/clear` | Clear log contents | None |
| `POST` | `/api/cookie/check` | Test current Cookie validity | None |
| `GET` | `/api/cookie/browsers` | Detect supported local browsers | None |
| `POST` | `/api/cookie/import_browser` | Extract Cookie from local browser | `{"browser": "chrome"}` |
| `POST` | `/api/test/mysql` | Test MySQL database connection | Host, port, user, password, db_name |
| `POST` | `/api/test/mongodb` | Test MongoDB connection | Host, port, user, password, db_name |
| `POST` | `/api/test/webhook` | Test Webhook notification trigger | `{"type": "wecom", "url": "..."}` |

---

## 2. SQLite Database Schema (`weibodata.db`)

When direct database querying is preferred, the SQLite database `weibodata.db` at workspace root contains the following tables:

### `weibo` Table
Stores individual Weibo post records:

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | TEXT PRIMARY KEY | Unique numeric ID of the post |
| `bid` | TEXT | Base62 identifier (used in URL: `weibo.com/<user_id>/<bid>`) |
| `user_id` | TEXT | Author's Weibo user ID |
| `screen_name` | TEXT | Author's display name |
| `text` | TEXT | Cleaned post text |
| `topics` | TEXT | Extracted topic tags (comma-separated) |
| `pics` | TEXT | Image URLs |
| `video_url` | TEXT | Video download URL |
| `live_photo_url` | TEXT | Live Photo video URL |
| `location` | TEXT | Post location check-in |
| `created_at` | TEXT | Formatted publication timestamp (`YYYY-MM-DD HH:MM:SS`) |
| `source` | TEXT | Post client or device source |
| `attitudes_count` | INTEGER | Likes count |
| `comments_count` | INTEGER | Comments count |
| `reposts_count` | INTEGER | Reposts count |
| `retweet_id` | TEXT | Original post ID if this is a retweet |
| `at_users` | TEXT | Mentioned @users |

### `user` Table
Stores author profiles:

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | TEXT PRIMARY KEY | Weibo user ID |
| `screen_name` | TEXT | Screen display name |
| `gender` | TEXT | Gender (m/f) |
| `statuses_count` | INTEGER | Total post count |
| `followers_count` | INTEGER | Followers count |
| `follow_count` | INTEGER | Followings count |
| `description` | TEXT | Bio description |
| `profile_url` | TEXT | Profile avatar URL |
| `verified` | INTEGER | Verification status |
| `verified_reason` | TEXT | Official verification description |

---

## 3. Direct SQLite SQL Examples

Agents can query the SQLite database directly using Python standard library:

```python
import sqlite3

conn = sqlite3.connect("weibodata.db")
cursor = conn.cursor()

# Top 5 most-liked posts
cursor.execute("""
    SELECT screen_name, attitudes_count, created_at, text 
    FROM weibo 
    ORDER BY attitudes_count DESC 
    LIMIT 5
""")
for row in cursor.fetchall():
    print(row)

conn.close()
```
