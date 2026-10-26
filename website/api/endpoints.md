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
    }
  }
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

## 7. 兼容旧版端点 (Legacy API)

- `POST /refresh`: 兼容旧版触发接口，返回 `202 Accepted` 或 `409 Conflict`
- `GET /task/<task_id>`: 兼容旧版任务状态轮询
- `GET /weibos`: 导出最新 100 条抓取微博
- `GET /weibos/<weibo_id>`: 获取单条微博数据详情
