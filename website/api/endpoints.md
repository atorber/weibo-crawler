# 接口端点与调用规范

本文档详尽列出了 `service.py` 提供的标准化 RESTful API 接口端点、请求方式、入参规范与返回格式。

默认服务运行在 `http://127.0.0.1:15001`（或由启动参数 `--port` 指定）。

---

## 1. 爬虫调度与进程控制

### 1.1 获取系统运行状态

查询爬虫进程活跃状态、当前采集用户、时长及核心监控统计指标。

- **URL**: `/api/status`
- **Method**: `GET`
- **响应示例**:

```json
{
  "code": 200,
  "data": {
    "status": "RUNNING",
    "is_running": true,
    "pid": 61208,
    "start_time": 1729938000.0,
    "duration": "00:03:42",
    "current_user": "迪丽热巴",
    "crawled_count": 48,
    "error_message": null,
    "metrics": {
      "user_count": 5,
      "total_weibos": 2510,
      "db_connected": true,
      "log_entries_count": 136
    },
    "schedule": {
      "enabled": true,
      "interval_minutes": 30,
      "last_trigger_time": "2026-10-27 10:30:00",
      "run_count": 4,
      "next_run_in_seconds": 1520
    }
  }
}
```

---

### 1.5 获取或设置持续监听模式 (`/api/schedule`)

查询或修改定时自动增量巡检配置（`schedule_config`），支持开启时立即触发首轮巡检。

- **URL**: `/api/schedule`
- **Method**: `GET` / `POST`
- **POST 请求参数**:
  - `enabled` (布尔值): 是否开启持续监听模式
  - `interval_minutes` (整数): 每轮结束后的等待间隔（分钟，默认 30）
  - `run_immediately` (布尔值, 可选): 开启时若当前处于空闲状态，是否立即启动首轮巡检

```json
{
  "enabled": true,
  "interval_minutes": 30,
  "run_immediately": true
}
```

---

### 1.2 启动爬虫任务

触发后台启动 `weibo.py` 爬虫子进程。支持指定临时用户队列。

- **URL**: `/api/service/start`
- **Method**: `POST`
- **Content-Type**: `application/json`

#### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `user_id_list` | `list[str]` | 否 | 指定本次爬取的博主 UID 列表。若不传则采纳当前配置列表 |

#### 请求示例

```bash
curl -X POST http://127.0.0.1:15001/api/service/start \
  -H "Content-Type: application/json" \
  -d '{"user_id_list": ["1669879400"]}'
```

#### 响应示例

```json
{
  "code": 200,
  "success": true,
  "message": "启动成功，进程 PID: 61208",
  "data": {
    "status": "RUNNING",
    "pid": 61208
  }
}
```

---

### 1.3 停止爬虫任务

向正在运行的爬虫进程发送优雅停止信号（SIGTERM），并在超时后安全强制退出。

- **URL**: `/api/service/stop`
- **Method**: `POST`
- **响应示例**:

```json
{
  "code": 200,
  "success": true,
  "message": "爬虫已成功停止",
  "data": {
    "status": "STOPPED"
  }
}
```

---

### 1.4 重启爬虫任务

停止现有进程并立即重新拉起爬虫。

- **URL**: `/api/service/restart`
- **Method**: `POST`
- **Content-Type**: `application/json`
- **请求参数**: 可选 `{"user_id_list": [...]}`

---

## 2. 目标博主队列管理

### 2.1 获取博主列表

- **URL**: `/api/users`
- **Method**: `GET`
- **响应示例**:

```json
{
  "code": 200,
  "total": 1,
  "data": [
    {
      "id": "1669879400",
      "screen_name": "Dear-迪丽热巴",
      "since_date": "2024-01-01",
      "query": "日常,生活"
    }
  ]
}
```

---

### 2.2 添加或更新博主

- **URL**: `/api/users`
- **Method**: `POST`
- **Content-Type**: `application/json`

#### 请求参数

```json
{
  "id": "1669879400",
  "screen_name": "Dear-迪丽热巴",
  "since_date": "2024-01-01",
  "query": ""
}
```

---

### 2.3 删除博主

- **URL**: `/api/users/<user_id>`
- **Method**: `DELETE`

```bash
curl -X DELETE http://127.0.0.1:15001/api/users/1669879400
```

---

### 2.4 批量导入博主

- **URL**: `/api/users/import`
- **Method**: `POST`
- **Content-Type**: `application/json`

```json
{
  "text": "1669879400 迪丽热巴 2024-01-01\n1223178222 胡歌",
  "mode": "append"
}
```

---

## 3. Cookie 认证与浏览器提取

### 3.1 连通性与时延测试

- **URL**: `/api/cookie/check` 或 `/api/cookie/test`
- **Method**: `POST`
- **请求参数**: `{"cookie": "..."}` （可选，缺省则测试当前配置中的 Cookie）
- **响应示例**:

```json
{
  "code": 200,
  "valid": true,
  "message": "Cookie 有效！响应时延: 175ms",
  "user": {
    "id": "2837199120",
    "screen_name": "开发者"
  }
}
```

---

### 3.2 探测本地浏览器

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
    { "id": "edge", "name": "Microsoft Edge" }
  ]
}
```

---

### 3.3 一键免密提取 Cookie

::: warning 安全限制
此接口仅支持本地来源调用（`127.0.0.1` 或 `localhost`），防止局域网或公网未经授权提取客户端凭据。
:::

- **URL**: `/api/cookie/import_browser`
- **Method**: `POST`
- **请求参数**:
  - `browser` (字符串, 可选): `"auto"`、`"chrome"`、`"edge"` 等
  - `save` (布尔值, 可选): 提取成功后是否自动写入 `config.json`

```json
{
  "browser": "auto",
  "save": true
}
```

---

### 3.4 Cookie 自动更新与失效热恢复策略

查询或保存浏览器 Cookie 自动更新配置（`cookie_auto_config`）与后台守护同步状态。

- **URL**: `/api/cookie/auto_config`
- **Method**: `GET` / `POST`
- **POST 请求参数**:
  - `enabled` (布尔值): 是否开启浏览器 Cookie 自动更新
  - `browser` (字符串): 目标浏览器（`"auto"`, `"chrome"`, `"edge"`, `"firefox"`, `"safari"` 等）
  - `refresh_on_expire` (布尔值): 爬虫运行中遇到 403/432/认证失效时自动热更新并重试
  - `check_before_start` (布尔值): 启动爬虫前自动检测并刷新失效 Cookie
  - `interval_minutes` (整数): 后台定时同步周期（分钟，`0` 表示仅在失效或启动前触发）
  - `trigger_now` (布尔值, 可选): 保存时是否立即执行一次浏览器 Cookie 提取同步

```json
{
  "enabled": true,
  "browser": "auto",
  "refresh_on_expire": true,
  "check_before_start": true,
  "interval_minutes": 360,
  "trigger_now": false
}
```

---

## 4. 存储介质连通性测试

在保存或启动前，测试外部介质是否配置正确：

| 端点 | 请求方法 | 典型入参 |
| :--- | :--- | :--- |
| `/api/test/mysql` | `POST` | `{"host": "127.0.0.1", "port": 3306, "user": "root", "password": "..."}` |
| `/api/test/mongodb` | `POST` | `{"uri": "mongodb://localhost:27017/weibo"}` |
| `/api/test/webhook` | `POST` | `{"url": "https://api.example.com/webhook", "token": "..."}` |

#### 返回响应结构

```json
{
  "code": 200,
  "valid": true,
  "message": "连接成功！耗时 24ms"
}
```

---

## 5. 配置中心与实时日志

### 5.1 获取与保存配置
- **GET `/api/config`**: 返回原始文本 `raw` 与结构化字典 `parsed`
- **POST `/api/config`**: 接收 `{"raw": "..."}` 或 `{"parsed": {...}}`，执行语法校验并持久化

### 5.2 实时运行日志
- **GET `/api/logs`**:
  - Query 参数: `limit` (默认 200), `level` (默认 ALL), `keyword` (模糊检索)
- **POST `/api/logs/clear`**: 清空内存中的日志队列

---

## 6. 本地数据检索

- **URL**: `/api/data/weibos`
- **Method**: `GET`
- **Query 参数**:
  - `page` (整数, 默认 1): 当前页码
  - `page_size` (整数, 默认 10): 每页返回数量
  - `user_id` (字符串, 可选): 指定博主 UID 过滤
  - `start_date` (字符串, 可选): 发布起始日期（如 `2024-01-01`）
  - `end_date` (字符串, 可选): 发布截止日期（如 `2024-01-07`）
  - `keyword` (字符串, 可选): 微博正文/博主关键词搜索
- **响应示例**:

```json
{
  "code": 200,
  "data": {
    "total": 86,
    "page": 1,
    "page_size": 10,
    "items": [
      {
        "id": "49581902830182",
        "user_id": "1669879400",
        "screen_name": "Dear-迪丽热巴",
        "created_at": "2024-05-01 12:00:00",
        "content": "节日快乐！",
        "reposts_count": 1024,
        "comments_count": 512,
        "attitudes_count": 2048
      }
    ],
    "available_users": [
      { "user_id": "1669879400", "screen_name": "Dear-迪丽热巴" }
    ]
  }
}
```

---

## 7. 微博发布与博文管理

> 基于现网 `https://weibo.com/` (`weibo-pro-next`) 协议实现，需要 `weibo.com` 个人登录态（含 `SUB`、`XSRF-TOKEN`），不支持匿名访客 Cookie。操作指南请参阅 [微博发布与博文管理](/guide/publish)。

### 可见性枚举 (`visible`)

| 取值 | 含义 | 说明 |
| :--- | :--- | :--- |
| `0` | 公开 | 所有人可见 |
| `1` | 仅自己可见 | 私密微博（推荐测试时使用） |
| `6` | 好友圈 | 仅互相关注好友可见 |
| `10` | 粉丝可见 | 仅粉丝可见 |
| `5` | 群可见 | 粉丝群可见 |

### 7.1 检查发博登录态

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

### 7.2 上传微博图片

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

### 7.3 发布 / 定时发布微博

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

::: tip 定时发布与数量限制
- 最多支持附加 18 张图片；`pics` 传已上传返回的图片对象/PID，`images` 可传本地图片绝对路径列表由后端自动上传。
- 若提供 `schedule_time`（支持 `"YYYY-MM-DD HH:MM"` 或毫秒时间戳，且必须至少晚于当前时间 10 分钟），将自动走微博定时发布通道。
:::

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

### 7.4 检查微博是否可编辑

- **URL**: ``/api/publish/can_edit/<mid>``
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

### 7.5 编辑微博

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

### 7.6 修改微博可见范围

- **URL**: `/api/publish/visibility`
- **Method**: `POST`
- **请求体 (JSON)**:
```json
{
  "mid": "5367067832485479",
  "visible": 0
}
```

### 7.7 删除微博

- **URL**: `/api/publish/delete`
- **Method**: `POST`
- **请求体 (JSON)**:
```json
{
  "mid": "5367067832485479"
}
```

### 7.8 查询个人/控制台发布列表

- **URL**: `/api/publish/posts`
- **Method**: `GET`
- **Query 参数**:
  - `source`: `remote`（实时拉取个人主页微博，失败自动回退本地记录）或 `local`（仅查本地 `log/publish_history.json`）
  - `page`: 页码（默认 `1`）

### 7.9 微博图床防盗链图片代理

- **URL**: `/api/publish/image_proxy`
- **Method**: `GET`
- **Query 参数**:
  - `url`: 目标图片地址。服务端严格校验图床域名白名单（仅限 `*.sinaimg.cn` 与 `*.weibocdn.com`）并对最多 2 跳重定向复验目标主机以防止 SSRF，请求时自动附带 `Referer: https://weibo.com/` 解决新浪图床防盗链 403 问题。

---

## 8. 兼容旧版端点 (Legacy API)

- ``POST /refresh``: 兼容旧版触发接口，返回 `202 Accepted` 或 `409 Conflict`
- ``GET /task/<task_id>``: 兼容旧版任务状态轮询
- ``GET /weibos``: 导出最新 100 条抓取微博
- ``GET /weibos/<weibo_id>``: 获取单条微博数据详情
