# Weibo Crawler 双层架构 RESTful API 说明文档

本文档详细介绍了基于 Flask 构建的 **Weibo Crawler 双层架构后端服务**（`service.py`）提供的全部 HTTP 接口：

- **🔌 层面一（Weibo 原生接口透明透传网关 & 客户端开发底座）**：只需将 `weibo.com`、`api.weibo.com`、`picupload.weibo.com`、`m.weibo.cn` 的域名与端口替换为当前服务（默认 `http://127.0.0.1:15001`），即可 1:1 请求微博原生接口（`/ajax/*`、`/webim/*`、`/interface/*`、`/api/container/*` 等），或直接调用基于透传层封装的**微博发布客户端 (`/api/publish/*`)** 与 **私信群聊客户端 (`/api/chat/*`)**。
- **🕷️ 层面二（微博爬虫任务调度、持久化存档 & 开放数据查询）**：通过 `/api/service/*`、`/api/users*`、`/api/config`、`/api/data/weibos` 远程调度爬虫任务并检索 SQLite 归档数据。

---

## 目录

- [服务启动与基础说明](#服务启动与基础说明)
- [API 端点概览](#api-端点概览)
- [1. 服务与进程调度接口](#1-服务与进程调度接口)
  - [获取服务运行状态 (GET /api/status)](#11-获取服务运行状态)
  - [启动爬虫进程 (POST /api/service/start)](#12-启动爬虫进程)
  - [停止爬虫进程 (POST /api/service/stop)](#13-停止爬虫进程)
  - [重启爬虫进程 (POST /api/service/restart)](#14-重启爬虫进程)
- [2. 目标博主队列管理](#2-目标博主队列管理)
  - [获取目标博主列表 (GET /api/users)](#21-获取目标博主列表)
  - [添加或更新博主 (POST /api/users)](#22-添加或更新博主)
  - [删除目标博主 (DELETE /api/users/\<user_id\>)](#23-删除目标博主)
  - [批量导入博主 (POST /api/users/import)](#24-批量导入博主)
- [3. 配置管理接口](#3-配置管理接口)
  - [获取当前配置 (GET /api/config)](#31-获取当前配置)
  - [保存或更新配置 (POST /api/config)](#32-保存或更新配置)
- [4. Cookie 认证与浏览器提取](#4-cookie-认证与浏览器提取)
  - [测试 Cookie 连通性 (POST /api/cookie/check)](#41-测试-cookie-连通性)
  - [探测支持的浏览器 (GET /api/cookie/browsers)](#42-探测支持的浏览器)
  - [从本地浏览器免密提取 Cookie (POST /api/cookie/import_browser)](#43-从本地浏览器免密提取-cookie)
- [5. 存储介质连通性测试](#5-存储介质连通性测试)
  - [测试 MySQL 连接 (POST /api/test/mysql)](#51-测试-mysql-连接)
  - [测试 MongoDB 连接 (POST /api/test/mongodb)](#52-测试-mongodb-连接)
  - [测试 Webhook 接口 (POST /api/test/webhook)](#53-测试-webhook-接口)
- [6. 日志流与监控](#6-日志流与监控)
  - [获取实时运行日志 (GET /api/logs)](#61-获取实时运行日志)
  - [清空内存日志缓冲区 (POST /api/logs/clear)](#62-清空内存日志缓冲区)
- [7. 本地数据检索](#7-本地数据检索)
  - [分页查询已存入微博 (GET /api/data/weibos)](#71-分页查询已存入微博)
- [8. 微博发布与博文管理](#8-微博发布与博文管理)
  - [检查发博登录态 (GET /api/publish/status)](#81-检查发博登录态)
  - [上传微博图片 (POST /api/publish/upload_image)](#82-上传微博图片)
  - [发布 / 定时发布微博 (POST /api/publish/post)](#83-发布--定时发布微博)
  - [检查微博是否可编辑 (GET /api/publish/can_edit/\<mid\>)](#84-检查微博是否可编辑)
  - [编辑微博 (POST /api/publish/edit)](#85-编辑微博)
  - [修改微博可见范围 (POST /api/publish/visibility)](#86-修改微博可见范围)
  - [删除微博 (POST /api/publish/delete)](#87-删除微博)
  - [查询个人/控制台发布列表 (GET /api/publish/posts)](#88-查询个人控制台发布列表)
  - [微博图床防盗链图片代理 (GET /api/publish/image_proxy)](#89-微博图床防盗链图片代理)
- [9. Weibo 原生接口透明透传 (Native Pass-Through Proxy)](#9-weibo-原生接口透明透传-native-pass-through-proxy)
  - [PC 网页端 AJAX 全量透传 (`weibo.com/ajax/*`)](#91-pc-网页端-ajax-全量透传-weibocomajax)
  - [图床原生上传透传 (`picupload.weibo.com/interface/*`)](#92-图床原生上传透传-picuploadweibocominterface)
  - [移动版 H5 接口透传 (`m.weibo.cn/*`)](#93-移动版-h5-接口透传-mweibocn)
  - [调用示例与高级控制头](#94-调用示例与高级控制头)
- [10. 兼容旧版端点 (Legacy API)](#10-兼容旧版端点-legacy-api)
  - [异步刷新数据 (POST /refresh)](#101-异步刷新数据)
  - [查询任务状态 (GET /task/\<task_id\>)](#102-查询任务状态)
  - [获取微博列表 (GET /weibos)](#103-获取微博列表)
  - [获取单条微博 (GET /weibos/\<weibo_id\>)](#104-获取单条微博)
- [统一响应与错误码规范](#统一响应与错误码规范)

---

## 服务启动与基础说明

API 服务由 `service.py` 驱动，集成了 Web 可视化控制台与 HTTP 接口服务。

### 启动命令

```bash
# 默认在 15001 端口启动，监听所有网卡 (0.0.0.0)
python service.py

# 指定端口与监听地址
python service.py --port 15001 --host 0.0.0.0
```

> **端口冲突自动处理**：若指定端口被占用，服务会自动探测并递增绑定到下一个可用端口（如 15002），并在终端打印实际访问地址。

---

## API 端点概览

| 模块 | Method | URL | 功能说明 |
| :--- | :--- | :--- | :--- |
| **状态调度** | `GET` | `/api/status` | 获取服务整体运行状态、监控指标、持续监听倒计时与进程信息 |
| | `POST` | `/api/service/start` | 启动爬虫子进程（支持临时指定用户列表） |
| | `POST` | `/api/service/stop` | 停止当前运行中的爬虫进程 |
| | `POST` | `/api/service/restart` | 重启爬虫进程 |
| | `GET`/`POST` | `/api/schedule` | 查询或配置持续监听模式（定时自动增量巡检 `schedule_config`） |
| **目标管理** | `GET` | `/api/users` | 获取当前监控的目标博主列表 |
| | `POST` | `/api/users` | 添加或修改单个博主（UID、昵称、起始日期、过滤词） |
| | `DELETE`| `/api/users/<user_id>` | 移除指定博主 |
| | `POST` | `/api/users/import` | 批量文本导入博主列表（追加或覆盖） |
| **配置中心** | `GET` | `/api/config` | 获取当前生效的 `config.json` 原始内容与解析对象 |
| | `POST` | `/api/config` | 在线校验并保存配置（支持合并更新） |
| **Cookie认证** | `POST` | `/api/cookie/check` | 验证 Cookie 连通性、抓取时延及归属用户信息（支持失效自动重提） |
| | `GET` | `/api/cookie/browsers`| 探测本机已安装且支持免密提取的浏览器 |
| | `POST` | `/api/cookie/import_browser`| 一键从本地浏览器安全提取微博 Cookie |
| | `GET`/`POST` | `/api/cookie/auto_config` | 查询或配置浏览器 Cookie 自动更新与 403 失效热恢复策略 |
| **连通性测试** | `POST` | `/api/test/mysql` | 探测 MySQL 服务端版本、认证与网络时延 |
| | `POST` | `/api/test/mongodb` | 探测 MongoDB 集群状态、版本与网络时延 |
| | `POST` | `/api/test/webhook` | 探测 HTTP Webhook 端点连通性与鉴权响应 |
| **日志与数据** | `GET` | `/api/logs` | 实时拉取内存运行日志（支持等级与关键字过滤） |
| | `POST` | `/api/logs/clear` | 清空内存日志缓冲区 |
| | `GET` | `/api/data/weibos` | 分页检索 SQLite 本地数据库微博记录 |
| **发布管理** | `GET` | `/api/publish/status` | 检查 `weibo.com` 个人发布权限与 `XSRF-TOKEN` 状态 |
| | `POST` | `/api/publish/upload_image` | 上传本地/表单图片至微博图床并返回 `pid` 与预览 URL |
| | `POST` | `/api/publish/post` | 发布或定时发布微博（支持图文、可见范围与干跑校验） |
| | `GET` | `/api/publish/can_edit/<mid>` | 检查指定微博 `mid` 当前账号是否允许编辑 |
| | `POST` | `/api/publish/edit` | 编辑已发布微博正文、图片或可见范围 |
| | `POST` | `/api/publish/visibility` | 修改指定微博的可见范围（`0/1/5/6/10`） |
| | `POST` | `/api/publish/delete` | 删除指定 `mid` 的微博 |
| | `GET` | `/api/publish/posts` | 拉取当前账号远端微博列表与本地控制台发布历史 |
| | `GET` | `/api/publish/image_proxy` | 携带微博 `Referer` 代理拉取官方图床图片（防盗链兼容） |
| **原生透传** | `*` | `/ajax/<path:subpath>` | 1:1 透传 `https://weibo.com/ajax/<subpath>`（自动注入 Cookie/XSRF 与 403/过期重试） |
| | `POST` | `/interface/upload.php` | 1:1 透传 `https://picupload.weibo.com/interface/upload.php`（自动补全 `cs`/`raw_md5`/`uid`，支持 `i.api.weibo.com` 容灾回退） |
| | `POST` | `/interface/pic_upload.php` | 1:1 透传 `https://picupload.weibo.com/interface/pic_upload.php`（multipart `pic1` / `file` 或原始流） |
| | `GET` | `/api/container/getIndex`、`...` | 1:1 透传 `https://m.weibo.cn/*`（含 `comments/hotflow`、`statuses/show`、`detail/<weibo_id>`、`/m/api/config` 等） |
| **兼容旧版** | `POST` | `/refresh` | 触发采集任务（返回 202/409，带 task_id） |
| | `GET` | `/task/<task_id>` | 查询指定 task_id 的进度与状态 |
| | `GET` | `/weibos` | 获取最近 100 条抓取微博记录 |
| | `GET` | `/weibos/<weibo_id>` | 查询指定 ID 的单条微博详情 |

---

## 1. 服务与进程调度接口

### 1.1 获取服务运行状态
- **URL**: `/api/status`
- **Method**: `GET`
- **响应示例**:
```json
{
  "code": 200,
  "data": {
    "status": "RUNNING",
    "is_running": true,
    "pid": 58321,
    "start_time": 1729938000.0,
    "duration": "00:05:21",
    "current_user": "迪丽热巴",
    "crawled_count": 86,
    "error_message": null,
    "metrics": {
      "user_count": 3,
      "total_weibos": 1420,
      "db_connected": true,
      "log_entries_count": 182
    }
  }
}
```

### 1.2 启动爬虫进程
- **URL**: `/api/service/start`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **请求参数**:
  - `user_id_list` (数组, 可选): 本次运行仅采纳的用户 ID 列表。若不传则按配置文件的博主列表执行。
```json
{
  "user_id_list": ["1669879400"]
}
```
- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "message": "启动成功，进程 PID: 58321",
  "data": { "status": "RUNNING", "pid": 58321 }
}
```
*注：若当前已有爬虫正在运行，返回 `code: 400, success: false`。*

### 1.3 停止爬虫进程
- **URL**: `/api/service/stop`
- **Method**: `POST`
- **说明**: 发送 SIGTERM 优雅停止信号，若 3 秒内未退出则执行安全强制销毁。
- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "message": "爬虫已成功停止",
  "data": { "status": "STOPPED" }
}
```

### 1.4 重启爬虫进程
- **URL**: `/api/service/restart`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **请求参数**: 同启动接口，支持可选 `user_id_list`。

### 1.5 持续监听与定时增量巡检
- **URL**: `/api/schedule`
- **Method**: `GET` / `POST`
- **Content-Type**: `application/json`
- **POST 请求参数**:
  - `enabled` (布尔值): 是否开启持续监听模式（开启后每轮爬完自动等待指定间隔并拉起下一轮增量巡检）
  - `interval_minutes` (整数): 每轮结束后的等待间隔（分钟，默认 `30`）
  - `run_immediately` (布尔值, 可选): 开启时若当前处于空闲状态，是否立即启动首轮巡检
- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "started_now": true,
  "message": "已开启持续监听模式（每 30 分钟自动巡检增量微博）",
  "config": { "enabled": true, "interval_minutes": 30 },
  "status": {
    "enabled": true,
    "interval_minutes": 30,
    "last_trigger_time": "2026-10-27 10:30:00",
    "run_count": 1,
    "next_run_in_seconds": null
  }
}
```

---

## 2. 目标博主队列管理

### 2.1 获取目标博主列表
- **URL**: `/api/users`
- **Method**: `GET`
- **响应示例**:
```json
{
  "code": 200,
  "total": 2,
  "data": [
    {
      "id": "1669879400",
      "screen_name": "Dear-迪丽热巴",
      "since_date": "2024-01-01",
      "query": "活动,日常"
    },
    {
      "id": "1223178222",
      "screen_name": "胡歌",
      "since_date": "",
      "query": ""
    }
  ]
}
```

### 2.2 添加或更新博主
- **URL**: `/api/users`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **请求参数**:
| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `id` | `string` | 是 | 微博用户纯数字 UID |
| `screen_name` | `string` | 否 | 博主个性化备注或昵称 |
| `since_date` | `string` | 否 | 采集起始日期（如 `2024-01-01` 或相对天数 `7`） |
| `query` | `string` | 否 | 包含特定关键词筛选（逗号分隔） |
- **请求示例**:
```json
{
  "id": "1669879400",
  "screen_name": "Dear-迪丽热巴",
  "since_date": "2024-01-01",
  "query": ""
}
```

### 2.3 删除目标博主
- **URL**: `/api/users/<user_id>`
- **Method**: `DELETE`
- **响应示例**:
```json
{
  "code": 200,
  "message": "删除成功",
  "data": [ ...更新后的博主列表... ]
}
```

### 2.4 批量导入博主
- **URL**: `/api/users/import`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **请求参数**:
  - `text` (字符串, 必填): 多行文本，每行格式：`UID [昵称] [起始日期] [关键词]`
  - `mode` (字符串, 可选): `"append"`（默认追加）或 `"overwrite"`（全量覆盖）
- **请求示例**:
```json
{
  "text": "1669879400 迪丽热巴 2024-01-01\n1223178222 胡歌",
  "mode": "append"
}
```

---

## 3. 配置管理接口

### 3.1 获取当前配置
- **URL**: `/api/config`
- **Method**: `GET`
- **响应示例**:
```json
{
  "code": 200,
  "raw": "{\n    \"cookie\": \"...\",\n ...\n}",
  "parsed": {
    "cookie": "...",
    "write_mode": ["csv", "sqlite"],
    "anti_ban_config": {
      "random_delay_enabled": true,
      "random_delay_min": 6,
      "random_delay_max": 14
    }
  },
  "is_custom_config": true
}
```

### 3.2 保存或更新配置
- **URL**: `/api/config`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **请求参数**: 传入 `raw`（JSON 字符串）或 `parsed`（JSON 字典对象）均可。
- **请求示例**:
```json
{
  "parsed": {
    "only_crawl_original": 1,
    "write_mode": ["csv", "sqlite", "mysql"]
  }
}
```

---

## 4. Cookie 认证与浏览器提取

### 4.1 测试 Cookie 连通性
- **URL**: `/api/cookie/check` 或 `/api/cookie/test`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **请求参数**:
  - `cookie` (字符串, 可选): 需要测试的 Cookie 字符串。若不传则自动读取当前系统保存的 Cookie。
- **响应示例**:
```json
{
  "code": 200,
  "valid": true,
  "message": "Cookie 有效！响应时延: 182ms",
  "user": {
    "id": "2837199120",
    "screen_name": "极客开发者",
    "statuses_count": 312
  }
}
```

### 4.2 探测支持的浏览器
- **URL**: `/api/cookie/browsers`
- **Method**: `GET`
- **响应示例**:
```json
{
  "code": 200,
  "rookiepy_available": true,
  "browsers": [
    { "id": "auto", "name": "自动探测已登录浏览器 (推荐)" },
    { "id": "chrome", "name": "Google Chrome" },
    { "id": "edge", "name": "Microsoft Edge" },
    { "id": "firefox", "name": "Mozilla Firefox" },
    { "id": "safari", "name": "Apple Safari" },
    { "id": "brave", "name": "Brave Browser" },
    { "id": "arc", "name": "Arc Browser" },
    { "id": "opera", "name": "Opera Browser" }
  ]
}
```

### 4.3 从本地浏览器免密提取 Cookie
- **URL**: `/api/cookie/import_browser`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **安全约束**: **仅允许本地来源 (`127.0.0.1` / `localhost`) 调用**，非本地调用直接返回 403 阻断。
- **请求参数**:
  - `browser` (字符串, 可选): 浏览器标识符（如 `"auto"`, `"chrome"`, `"edge"`, 默认 `"auto"`）
  - `save` (布尔值, 可选): 提取成功后是否自动写入 `config.json`（默认 `false`）
- **请求示例**:
```json
{
  "browser": "auto",
  "save": true
}
```
- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "browser": "Google Chrome",
  "cookie": "SUB=_2A25xxxx...; SUBP=0033...;",
  "valid": true,
  "message": "成功从 Google Chrome 提取微博 Cookie！Cookie 有效！响应时延: 165ms",
  "user": { "screen_name": "开发者" }
}
```

### 4.4 Cookie 自动更新与失效热恢复策略
- **URL**: `/api/cookie/auto_config`
- **Method**: `GET` / `POST`
- **Content-Type**: `application/json`
- **POST 请求参数**:
  - `enabled` (布尔值): 是否开启浏览器 Cookie 自动提取与更新总开关
  - `browser` (字符串): 目标浏览器（`"auto"`, `"chrome"`, `"edge"`, `"firefox"`, `"safari"`, `"brave"`, `"arc"`, `"opera"`）
  - `refresh_on_expire` (布尔值): 爬虫运行中遇到 403/432/认证失效时，自动从浏览器提取新 Cookie 热更新并无缝重试
  - `check_before_start` (布尔值): 每次启动爬虫任务前自动检测并刷新失效 Cookie
  - `interval_minutes` (整数): 后台定时同步周期（分钟，`0` 表示仅在失效或启动前触发）
  - `trigger_now` (布尔值, 可选): 是否立即执行一次浏览器提取同步
- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "message": "Cookie 自动更新策略已保存",
  "config": {
    "enabled": true,
    "browser": "auto",
    "refresh_on_expire": true,
    "check_before_start": true,
    "interval_minutes": 360
  },
  "status": {
    "last_sync_time": "2026-10-27 10:00:00",
    "last_sync_status": "SUCCESS",
    "last_sync_message": "[定时周期更新] 成功从 Google Chrome 提取微博 Cookie！",
    "sync_count": 2
  }
}
```

---

## 5. 存储介质连通性测试

在正式保存或启动爬虫前，可通过以下端点即时验证远端数据库与接口连通性。

### 5.1 测试 MySQL 连接
- **URL**: `/api/test/mysql`
- **Method**: `POST`
- **请求参数**:
```json
{
  "host": "127.0.0.1",
  "port": 3306,
  "user": "root",
  "password": "yourpassword",
  "charset": "utf8mb4"
}
```
- **响应示例**:
```json
{
  "code": 200,
  "valid": true,
  "message": "连接成功！MySQL 版本: 8.0.32 (耗时 12ms)"
}
```

### 5.2 测试 MongoDB 连接
- **URL**: `/api/test/mongodb`
- **Method**: `POST`
- **请求参数**:
```json
{
  "uri": "mongodb://admin:pass@localhost:27017/weibo?authSource=admin"
}
```
- **响应示例**:
```json
{
  "code": 200,
  "valid": true,
  "message": "连接成功！MongoDB 版本: 6.0.5 (耗时 18ms)"
}
```

### 5.3 测试 Webhook 接口
- **URL**: `/api/test/webhook`
- **Method**: `POST`
- **说明**: 发送带有 `{"event": "ping"}` 的 HTTP POST 探测包。
- **请求参数**:
```json
{
  "url": "https://api.example.com/webhook",
  "token": "secret_token_123"
}
```
- **响应示例**:
```json
{
  "code": 200,
  "valid": true,
  "message": "响应成功！HTTP 状态码: 200 OK (耗时 89ms)"
}
```

---

## 6. 日志流与监控

### 6.1 获取实时运行日志
- **URL**: `/api/logs`
- **Method**: `GET`
- **Query 参数**:
  - `limit` (整数, 默认 200): 最大返回行数（最多 3000 行缓冲区）
  - `level` (字符串, 默认 `"ALL"`): 筛选级别（`ALL`, `INFO`, `WARNING`, `ERROR`）
  - `keyword` (字符串, 默认 `""`): 关键字模糊过滤
- **响应示例**:
```json
{
  "code": 200,
  "total": 2,
  "logs": [
    "2026-10-26 18:20:10 [INFO] 正在抓取博主: 迪丽热巴 (UID: 1669879400)...",
    "2026-10-26 18:20:12 [INFO] 获取第 1 页微博成功，共 10 条记录"
  ]
}
```

### 6.2 清空内存日志缓冲区
- **URL**: `/api/logs/clear`
- **Method**: `POST`
- **响应示例**:
```json
{
  "code": 200,
  "message": "内存日志已清空"
}
```

---

## 7. 本地数据检索

### 7.1 多维检索与分页查询微博
从本地 SQLite 数据库中检索已采集入库的微博，支持博主过滤、发布时间区间以及正文关键字搜索。
- **URL**: `/api/data/weibos`
- **Method**: `GET`
- **Query 参数**:
  - `page` (整数, 默认 1): 当前页码
  - `page_size` (整数, 默认 10): 每页条数
  - `user_id` (字符串, 可选): 指定博主 UID 过滤（支持输入博主纯数字 UID）
  - `start_date` (字符串, 可选): 发布起始日期（格式如 `2024-01-01` 或完整时间戳）
  - `end_date` (字符串, 可选): 发布截止日期（格式如 `2024-01-07`，自动覆盖至当日 23:59:59）
  - `keyword` (字符串, 可选): 微博正文/博主昵称关键词模糊搜索
- **响应示例**:
```json
{
  "code": 200,
  "data": {
    "exists": true,
    "total": 128,
    "page": 1,
    "page_size": 10,
    "items": [
      {
        "id": "49581902830182",
        "user_id": "1669879400",
        "screen_name": "Dear-迪丽热巴",
        "created_at": "2024-05-01 12:00:00",
        "content": "五一劳动节快乐！[太阳]",
        "reposts_count": 100000,
        "comments_count": 89201,
        "attitudes_count": 650123
      }
    ],
    "available_users": [
      { "user_id": "1669879400", "screen_name": "Dear-迪丽热巴" }
    ]
  }
}
```

---

## 8. 微博发布与博文管理

> 基于现网 `https://weibo.com/` (`weibo-pro-next`) 协议实现，需要 `weibo.com` 个人登录态（含 `SUB`、`XSRF-TOKEN`），不支持匿名访客 Cookie。

### 可见性枚举 (`visible`)

| 取值 | 含义 | 说明 |
| :--- | :--- | :--- |
| `0` | 公开 | 所有人可见 |
| `1` | 仅自己可见 | 私密微博（推荐测试时使用） |
| `6` | 好友圈 | 仅互相关注好友可见 |
| `10` | 粉丝可见 | 仅粉丝可见 |
| `5` | 群可见 | 粉丝群可见 |

### 8.1 检查发博登录态

- **URL**: `/api/publish/status`
- **Method**: `GET`
- **响应示例**:
```json
{
  "code": 200,
  "data": {
    "logged_in": true,
    "uid": "1863732524",
    "screen_name": "示例账号",
    "has_xsrf": true,
    "message": "Cookie 具备 weibo.com 发布权限（账号：示例账号）",
    "visible_options": [
      { "value": 0, "label": "公开" },
      { "value": 1, "label": "仅自己可见" },
      { "value": 6, "label": "好友圈" },
      { "value": 10, "label": "粉丝可见" },
      { "value": 5, "label": "群可见" }
    ]
  }
}
```

### 8.2 上传微博图片

- **URL**: `/api/publish/upload_image`
- **Method**: `POST`
- **请求方式**:
  - `multipart/form-data`：字段名 `file`
  - 或 `application/json`：`{"file_path": "/abs/path/to/photo.jpg"}`
- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "message": "上传成功",
  "data": {
    "pid": "0021x...",
    "type": "image/jpeg",
    "preview_url": "https://wx1.sinaimg.cn/bmiddle/0021x....jpg",
    "large_url": "https://wx1.sinaimg.cn/large/0021x....jpg"
  }
}
```

### 8.3 发布 / 定时发布微博

- **URL**: `/api/publish/post`
- **Method**: `POST`
- **请求体 (JSON)**:
```json
{
  "content": "测试一条图文微博 #自动化#",
  "visible": 1,
  "pics": [{ "pid": "0021x...", "type": "image/jpeg" }],
  "images": [],
  "schedule_time": null,
  "dry_run": false
}
```
> 若提供 `schedule_time`（支持 `"YYYY-MM-DD HH:MM"` 或毫秒时间戳，且必须至少晚于当前时间 10 分钟），将自动走微博定时发布通道。

- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "message": "发布成功",
  "data": {
    "ok": true,
    "mid": "5367067832485479",
    "mblogid": "Rs8JVaqAn",
    "url": "https://weibo.com/1863732524/Rs8JVaqAn",
    "visible": 1,
    "visible_label": "仅自己可见"
  }
}
```

### 8.4 检查微博是否可编辑

- **URL**: `/api/publish/can_edit/<mid>`
- **Method**: `GET`
- **响应示例**:
```json
{
  "code": 200,
  "success": true,
  "data": {
    "ok": true,
    "can_edit": true,
    "mid": "5367067832485479",
    "content": "原微博正文",
    "msg": "当前微博可编辑"
  }
}
```

### 8.5 编辑微博

- **URL**: `/api/publish/edit`
- **Method**: `POST`
- **请求体 (JSON)**:
```json
{
  "mid": "5367067832485479",
  "content": "修改后的微博正文",
  "visible": 1,
  "check_first": true,
  "dry_run": false
}
```

### 8.6 修改微博可见范围

- **URL**: `/api/publish/visibility`
- **Method**: `POST`
- **请求体 (JSON)**:
```json
{
  "mid": "5367067832485479",
  "visible": 0
}
```

### 8.7 删除微博

- **URL**: `/api/publish/delete`
- **Method**: `POST`
- **请求体 (JSON)**:
```json
{
  "mid": "5367067832485479"
}
```

### 8.8 查询个人/控制台发布列表

- **URL**: `/api/publish/posts`
- **Method**: `GET`
- **Query 参数**:
  - `source`: `remote`（实时拉取个人主页微博，失败自动回退本地记录）或 `local`（仅查本地 `log/publish_history.json`）
  - `page`: 页码（默认 `1`）

### 8.9 微博图床防盗链图片代理

- **URL**: `/api/publish/image_proxy`
- **Method**: `GET`
- **Query 参数**:
  - `url`: 仅限微博官方图床域名（`*.sinaimg.cn` / `*.weibocdn.com`），自动携带 `Referer: https://weibo.com/` 拉取图片流并做域名白名单与重定向 SSRF 校验。

---

## 9. Weibo 原生接口透明透传 (Native Pass-Through Proxy)

> 只需将官方域名替换为当前后端地址（默认 `http://127.0.0.1:15001`），即可直接沿用 `https://weibo.com`、`https://picupload.weibo.com` 与 `https://m.weibo.cn` 的原生路径、Query 参数与请求/响应体格式，由后端统一代管 Cookie、`X-XSRF-TOKEN`、协议头与过期自动重提刷新。

### 9.1 PC 网页端 AJAX 全量透传 (`weibo.com/ajax/*`)

- **本地路由**: `/ajax/<path:subpath>`（对应 `https://weibo.com/ajax/<subpath>`）
- **支持方法**: `GET`、`POST`、`PUT`、`DELETE`、`PATCH`、`HEAD`、`OPTIONS`
- **核心覆盖接口（包含项目调用及 `weibo-pro-next` 全部 `/ajax/*` 接口）**:
  - 认证与配置：`GET /ajax/statuses/config`、`GET /ajax/config/get_config`、`GET /ajax/profile/detail`、`GET /ajax/profile/info`
  - 个人列表与搜索：`GET /ajax/statuses/mymblog`、`GET /ajax/profile/searchblog`
  - 博文详情/长文/编辑历史：`GET /ajax/statuses/show`、`GET /ajax/statuses/longtext`、`GET /ajax/statuses/editHistory`
  - 评论与转发：`GET /ajax/statuses/buildComments`、`GET /ajax/statuses/repostTimeline`
  - 发布与博文管理：`POST /ajax/statuses/update`、`POST /ajax/statuses/schedule/upload`、`GET /ajax/statuses/checkCanEdit`、`POST /ajax/statuses/modify`、`POST /ajax/statuses/modifyVisible`、`POST /ajax/statuses/destroy`
  - 互动写操作：`POST /ajax/comments/create`、`POST /ajax/comments/reply`、`POST /ajax/statuses/destroyComment`、`POST /ajax/statuses/normal_repost`、`POST /ajax/statuses/setLike`、`POST /ajax/statuses/cancelLike`
- **协议处理说明**:
  - 自动补齐 `Referer: https://weibo.com/`、`Origin: https://weibo.com`、`X-Requested-With: XMLHttpRequest`、`client-version`、`server-version` 与 `X-XSRF-TOKEN`；
  - 若 `POST` 等写请求传入 `Content-Type: application/json`，后端默认按 `weibo-pro-next` 的 `cleanRequest` 规则过滤空值（保留整数 `0`，将嵌套列表/对象转为 JSON 字符串）并转为微博原生 `application/x-www-form-urlencoded` 表单发送；
  - 遇到 HTTP `400/401/403/419/432` 或 JSON `{"ok": -100}` 时自动刷新 `XSRF-TOKEN` 握手或从浏览器重提 Cookie 并自动重试一次。

### 9.2 图床原生上传透传 (`picupload.weibo.com/interface/*`)

| 本地路由 | 上游目标 | 方法 | 说明 |
| :--- | :--- | :--- | :--- |
| `/interface/upload.php` | `https://picupload.weibo.com/interface/upload.php`（失败自动回退 `i.api.weibo.com`） | `POST` | 支持 `application/octet-stream` 原始二进制或 `multipart/form-data` (`file`/`pic1`)；缺失参数时自动计算 `cs` (CRC32)、`raw_md5`、`file_size`、`uid`、`request_id`，并按原生协议剥离 `X-Requested-With` / `X-XSRF-TOKEN` |
| `/interface/pic_upload.php` | `https://picupload.weibo.com/interface/pic_upload.php` | `POST` | 默认注入 `app=miniblog&s=json&p=1&data=1`，兼容 `pic1` 或 `file` 表单字段上传及原始字节流 |

### 9.3 移动版 H5 接口透传 (`m.weibo.cn/*`)

针对爬虫与探索接口用到的全部 `https://m.weibo.cn` 端点提供白名单校验后 1:1 透传：

| 本地路由 | 上游目标 | 方法 | 说明 |
| :--- | :--- | :--- | :--- |
| `/api/container/getIndex` | `https://m.weibo.cn/api/container/getIndex` | `GET` | 用户信息、微博分页流与搜索 |
| `/api/comments/show` | `https://m.weibo.cn/api/comments/show` | `GET` | 评论最新流分页 |
| `/api/statuses/repostTimeline` | `https://m.weibo.cn/api/statuses/repostTimeline` | `GET` | 转发列表分页 |
| `/comments/hotflow` | `https://m.weibo.cn/comments/hotflow` | `GET` | 一级热门评论分页 |
| `/comments/hotFlowChild` | `https://m.weibo.cn/comments/hotFlowChild` | `GET` | 二级评论回复分页 |
| `/statuses/show` | `https://m.weibo.cn/statuses/show` | `GET` | 单条微博详情/可见性探测 |
| `/detail/<weibo_id>` | `https://m.weibo.cn/detail/<weibo_id>` | `GET` | 单条微博 H5 详情页（保留 HTML MIME，自动剥离 `X-Requested-With`） |
| `/m/api/config` 或 `/api/config?passthrough=1` | `https://m.weibo.cn/api/config` | `GET` | `m.weibo.cn` 登录态与全局配置探针（无 `?passthrough=1` 与 `X-Weibo-Passthrough: 1` 时 `/api/config` 仍返回本地控制台配置） |

### 9.4 微博私信与群聊 WebIM 原生透传 (`api.weibo.com/webim/*`)

- **本地路由**: `/webim/<path:subpath>` -> 1:1 透传至 `https://api.weibo.com/webim/<subpath>`
- **Method**: `GET`、`POST`、`PUT`、`DELETE`、`PATCH`、`HEAD`、`OPTIONS`
- **协议特性**:
  - `GET` 请求自动补齐 `source=209678993` 与毫秒时间戳 `t=<epoch_ms>`；
  - `POST` 请求自动携带 `Referer: https://api.weibo.com/chat`、`Origin: https://api.weibo.com`，支持原生 `application/x-www-form-urlencoded`、`multipart/form-data`（如 `/webim/uploadx.json`）或直接传入 `application/json`（自动转换为表单并补齐 `&source=209678993`）；
  - 当遇到 JSON `error_code == 21301`（`sub invalid`）或 HTTP `401/403/432/500` 时，自动触发浏览器 Cookie 刷新并重试。

### 9.5 调用示例与高级控制头

- **可选请求头**：
  - `X-Weibo-Cookie`：按单次请求临时覆盖项目配置的微博 Cookie（不会修改本地配置文件或触发本机浏览器提取）；若传入的 `Cookie` 请求头包含 `SUB` / `SUBP` / `XSRF-TOKEN` 等微博认证字段同样有效。
  - `X-Weibo-Raw-Body: 1`：禁止后端将 `POST` JSON 请求体自动转换为 `application/x-www-form-urlencoded`，原样透传原始请求体。
  - `X-Weibo-Passthrough: 1`：用于 `/api/config`，使其透传至 `https://m.weibo.cn/api/config`。
- **响应追踪头**：每个透传响应均附带 `X-Weibo-Passthrough-Upstream`，标明实际转发的上游完整 URL，且原样保留上游 HTTP 状态码与主体字节。

```bash
# 1. 查询博主主页微博列表（等价于请求 https://weibo.com/ajax/statuses/mymblog）
curl "http://127.0.0.1:15001/ajax/statuses/mymblog?uid=1669879400&page=1&feature=0"

# 2. 原生发博接口透传（支持表单或直接传 JSON 自动转表单）
curl -X POST "http://127.0.0.1:15001/ajax/statuses/update" \
  -H "Content-Type: application/json" \
  -d '{"content": "原生透传测试 #weibo#", "visible": 1}'

# 3. 图床原始二进制上传透传（自动补齐 cs / raw_md5 / uid）
curl -X POST "http://127.0.0.1:15001/interface/upload.php" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @photo.jpg

# 4. 移动版 H5 评论/容器接口透传（等价于 https://m.weibo.cn/...）
curl "http://127.0.0.1:15001/api/container/getIndex?type=uid&value=1669879400"
curl "http://127.0.0.1:15001/comments/hotflow?id=5367067832485479&mid=5367067832485479&max_id_type=0"
curl "http://127.0.0.1:15001/m/api/config"

# 5. 微博私信 WebIM 原生接口透传（等价于 https://api.weibo.com/webim/...）
curl "http://127.0.0.1:15001/webim/2/direct_messages/contacts.json?count=20"
curl -X POST "http://127.0.0.1:15001/webim/2/direct_messages/new.json" \
  -H "Content-Type: application/json" \
  -d '{"uid": "1669879400", "text": "WebIM 透传私信测试"}'
```

---

## 9.6 微博私信与群聊管理接口 (`/api/chat/*`)

基于 `https://api.weibo.com/chat` (`pcweibochat`) WebIM 协议封装的高层 RESTful API（控制台页面路由：`/chat`）：

| 方法 | 路径 | 说明 | 核心参数 |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/chat/status` | 校验私信 WebIM 登录态与当前账号信息 | 无 |
| `GET` | `/api/chat/contacts` | 获取或搜索私信联系人与群聊会话列表 | `count`, `cursor`, `unfollow=0\|1`, `include_group=0\|1`, `keyword` |
| `GET` | `/api/chat/messages` | 获取单聊 (`uid`) 或群聊 (`gid`) 历史消息 | `uid`, `gid`, `count`, `max_id`, `unfollow=0\|1` |
| `POST` | `/api/chat/send` | 发送单聊或群聊文字/图片/文件附件 | JSON `{uid, gid, text, file_path, at_all, dry_run}` 或 `multipart/form-data` (`file`) |
| `POST` | `/api/chat/recall` | 撤回 3 分钟内发送的单聊或群聊消息 | `{"mid": "...", "gid": "..."}` |
| `POST` | `/api/chat/delete` | 删除单条私信/群消息或删除整个会话 | `{"mid": "...", "uid": "...", "gid": "...", "unfollow": false}` |
| `POST` | `/api/chat/read` | 标记单聊、群聊或未关注人私信箱为已读 | `{"uid": "...", "gid": "...", "unfollow": false}` |

---

## 10. 兼容旧版端点 (Legacy API)

为了与历史第三方接入系统保持 100% 向后兼容，以下经典端点保持完整支持：

### 10.1 异步刷新数据
- **URL**: `/refresh`
- **Method**: `POST`
- **请求体**: `{"user_id_list": ["6067225218"]}` (可选)
- **状态码**: 
  - `202 Accepted`: 任务成功启动，返回 `task_id`（当前进程 PID）
  - `409 Conflict`: 当前已有正在执行的任务

### 10.2 查询任务状态
- **URL**: `/task/<task_id>`
- **Method**: `GET`
- **响应示例**:
```json
{
  "state": "PROGRESS",
  "progress": 50,
  "result": { "status": "RUNNING" }
}
```

### 10.3 获取微博列表
- **URL**: `/weibos`
- **Method**: `GET`
- **说明**: 直接返回最近 100 条抓取微博的数组列表。

### 10.4 获取单条微博
- **URL**: `/weibos/<weibo_id>`
- **Method**: `GET`
- **状态码**: 200（找到）或 404（不存在）。

---

## 统一响应与错误码规范

RESTful API 端点统一返回 JSON 格式响应：

| HTTP 状态码 / 字段 code | 含义 | 说明 |
| :--- | :--- | :--- |
| `200 OK` | 请求成功 | 接口正常返回数据 |
| `202 Accepted` | 任务已接收 | 异步进程启动成功 |
| `400 Bad Request` | 参数错误 | 请求体格式无效、UID 格式错误或配置项缺失 |
| `403 Forbidden` | 权限拒绝 | 安全受限（如从非 localhost 外部尝试提取浏览器 Cookie） |
| `404 Not Found` | 未找到资源 | 博主不存在或微博 ID 记录不存在 |
| `409 Conflict` | 状态冲突 | 爬虫进程当前已在运行中，拒绝并发重复启动 |
| `500 Internal Error` | 服务端异常 | 依赖缺失（如 PyMySQL 未安装）或系统内部错误 |
