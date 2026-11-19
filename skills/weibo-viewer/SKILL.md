---
name: weibo-viewer
description: >-
  Control the Weibo crawler process (start, stop, restart, monitor status and logs) and query, search, or inspect crawled Weibo posts, target bloggers, and database contents. Use this skill whenever the user asks to crawl Weibo data, check crawler status/logs, list or add monitored users, or search/view stored Weibo posts.
---

# Weibo Viewer & Controller Skill

This skill equips the agent with full operational control over the Weibo Crawler system, including task scheduling, live process monitoring, target blogger management, and rich querying of scraped Weibo posts, media, and metrics.

---

## 🛠️ Primary Tool: `weibo_ctl.py` CLI Helper

A dedicated CLI script [weibo_ctl.py](./scripts/weibo_ctl.py) is provided to execute all operations reliably. It communicates with the local console daemon (`http://127.0.0.1:15001`) and automatically falls back to direct SQLite database operations if the web service is idle.

All commands support the `--json` flag to return structured machine-readable JSON directly to the agent.

---

## 🚀 Workflows & Common Operations

### 1. Check Crawler & Service Status
Use when verifying whether a crawling task is currently running or checking overall statistics:
```bash
python skills/weibo-viewer/scripts/weibo_ctl.py status
# Or output JSON for agent parsing:
python skills/weibo-viewer/scripts/weibo_ctl.py status --json
```

**Key Information Returned**:
- `Service Status`: Whether crawler is `IDLE` or `RUNNING`.
- `Total Weibos` & `Total Users`: Count of stored records in the database.
- `Process PID`: Subprocess ID if running.

---

### 2. Query and Search Crawled Weibo Posts
Use when the user asks to see recent posts, search for a specific topic or keyword, or inspect a blogger's timeline:

```bash
# General query (top 5 latest posts)
python skills/weibo-viewer/scripts/weibo_ctl.py query --limit 5

# Search by keyword (searches both text and topic tags)
python skills/weibo-viewer/scripts/weibo_ctl.py query --keyword "英伟达" --limit 5

# Filter by blogger user ID
python skills/weibo-viewer/scripts/weibo_ctl.py query --user-id 1445403190 --limit 10

# Filter by date range (YYYY-MM-DD)
python skills/weibo-viewer/scripts/weibo_ctl.py query --start-date 2026-10-01 --end-date 2026-10-26

# Sort by engagement (attitudes_count / comments_count / reposts_count)
python skills/weibo-viewer/scripts/weibo_ctl.py query --sort attitudes_count --limit 5

# Output raw JSON for programmatic analysis or summarization
python skills/weibo-viewer/scripts/weibo_ctl.py query --keyword "财报" --json
```

---

### 3. Manage Monitored Target Bloggers
Use when listing, adding, or removing Weibo user IDs from the crawler list:

```bash
# List all configured target bloggers
python skills/weibo-viewer/scripts/weibo_ctl.py users list

# Add a new blogger by user ID
python skills/weibo-viewer/scripts/weibo_ctl.py users add --uid 1669879400

# Remove a blogger from list
python skills/weibo-viewer/scripts/weibo_ctl.py users remove --uid 1669879400
```

---

### 4. Trigger & Control Crawling Tasks
Use when starting a new crawl job or stopping an existing one:

```bash
# Start crawler using current configuration
python skills/weibo-viewer/scripts/weibo_ctl.py start

# Start crawler with custom parameters (e.g., specific users and date range)
python skills/weibo-viewer/scripts/weibo_ctl.py start --users "1445403190,1669879400" --since-date 2026-10-20 --original-only

# Terminate running crawler process safely
python skills/weibo-viewer/scripts/weibo_ctl.py stop

# Restart crawler service
python skills/weibo-viewer/scripts/weibo_ctl.py restart
```

---

### 5. Inspect Logs & Troubleshoot
Use when the user asks why crawling stopped, if there are anti-scraping errors, or to view live activity:

```bash
# View last 30 lines of crawler logs
python skills/weibo-viewer/scripts/weibo_ctl.py logs --lines 30
```

---

### 6. Cookie Validity & Browser Extraction
Use when diagnosing authentication issues:

```bash
# Check if current Cookie is still valid
python skills/weibo-viewer/scripts/weibo_ctl.py cookie

# Automatically extract fresh Cookie from local Chrome browser
python skills/weibo-viewer/scripts/weibo_ctl.py cookie --extract --browser chrome
```

---

### 7. Publish & Manage Weibo Posts
Use when checking publishing login state, posting text/image/scheduled Weibo posts, changing visibility, editing, or deleting posts (online API first, offline fallback supported).

> **Safety Gate**: Always ask the user for explicit confirmation of the exact post text and visibility before publishing a public post (`--visible 0`), editing, or deleting a post (`delete`). Prefer `--visible 1` (self-only) or `--dry-run` for tests.

Visibility codes (`--visible`): `0` = Public (公开), `1` = Self-only (仅自己可见), `6` = Friends circle (好友圈), `10` = Fans-only (粉丝可见), `5` = Group (群可见).

```bash
# Check weibo.com personal publishing auth & XSRF status
python skills/weibo-viewer/scripts/weibo_ctl.py publish status

# Dry-run or publish a self-only post with images
python skills/weibo-viewer/scripts/weibo_ctl.py publish post --text "测试内容 #话题#" --images a.jpg b.png --visible 1 --dry-run
python skills/weibo-viewer/scripts/weibo_ctl.py publish post --text "测试内容" --visible 1

# Schedule a post (>= 10 minutes ahead)
python skills/weibo-viewer/scripts/weibo_ctl.py publish post --text "定时发布" --visible 0 --schedule "2026-11-20 09:00"

# List recent own posts, change visibility, edit, or delete
python skills/weibo-viewer/scripts/weibo_ctl.py publish list --source remote --page 1
python skills/weibo-viewer/scripts/weibo_ctl.py publish visibility --mid 5367067832485479 --visible 0
python skills/weibo-viewer/scripts/weibo_ctl.py publish edit --mid 5367067832485479 --text "修改后的正文"
python skills/weibo-viewer/scripts/weibo_ctl.py publish delete --mid 5367067832485479
```

---

### 8. Weibo Direct Messages & Group Chats (WebIM)
Use when checking WebIM auth status, listing contacts or group chats, reading conversation history, sending text/image/file messages, recalling messages (within 3 minutes), deleting messages/conversations, marking conversations as read, or calling any native `/webim/*` endpoint via `raw` (all built on top of the Mode 1 `/webim/*` pass-through: HTTP `/webim/*` when service is online, or in-process `WeiboPassthroughProxy.proxy_webim` when offline).

> **Safety Gate**: Always ask the user for explicit confirmation of the recipient (`--uid` / `--gid`) and message content before sending (`send`), recalling (`recall`), or deleting (`delete`) a message or conversation. Prefer `--dry-run` for validation.

```bash
# Check WebIM authentication status (add --verbose / -V to inspect /webim/* pass-through trace)
python skills/weibo-viewer/scripts/weibo_ctl.py chat status -V

# List contacts & group chats (or search by keyword / view unfollowed box)
python skills/weibo-viewer/scripts/weibo_ctl.py chat contacts --limit 20
python skills/weibo-viewer/scripts/weibo_ctl.py chat contacts --keyword "测试"
python skills/weibo-viewer/scripts/weibo_ctl.py chat contacts --unfollow

# Fetch 1-on-1 conversation messages or group chat messages
python skills/weibo-viewer/scripts/weibo_ctl.py chat messages --uid 1669879400 --limit 20
python skills/weibo-viewer/scripts/weibo_ctl.py chat messages --gid 4912345678901234 --limit 20

# Dry-run or send a 1-on-1 / group chat message (with optional image/file attachment)
python skills/weibo-viewer/scripts/weibo_ctl.py chat send --uid 1669879400 --text "你好" --dry-run
python skills/weibo-viewer/scripts/weibo_ctl.py chat send --uid 1669879400 --text "发送附件" --file ./pic.jpg
python skills/weibo-viewer/scripts/weibo_ctl.py chat send --gid 4912345678901234 --text "群消息测试"

# Recall (within 3 min), delete message/conversation, or mark read
python skills/weibo-viewer/scripts/weibo_ctl.py chat recall --mid 5367099999999999
python skills/weibo-viewer/scripts/weibo_ctl.py chat delete --mid 5367099999999999 --uid 1669879400
python skills/weibo-viewer/scripts/weibo_ctl.py chat read --uid 1669879400

# Call any of the 101 native /webim/* endpoints directly through the pass-through
python skills/weibo-viewer/scripts/weibo_ctl.py chat raw --path query_primary_info.json
python skills/weibo-viewer/scripts/weibo_ctl.py chat raw --path 2/direct_messages/contacts.json --param count=10
```

---

## 📚 Advanced Architecture & Direct API / SQL Access

For complex custom data analysis or automated scripting:
- Refer to [api_reference.md](./references/api_reference.md) for full RESTful API specifications and `weibodata.db` schema.
- Agents can query `weibodata.db` directly using SQLite if deep SQL joins (e.g., comments & reposts) or aggregations are needed.
