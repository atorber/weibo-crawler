# 接口端点与调用示例

本文档列出了 `service.py` 提供的全部 HTTP 接口及请求/响应参数规格。

## 1. 刷新微博数据

异步触发爬取指定用户的微博数据。

- **URL**: `/api/refresh`
- **Method**: `POST`
- **Content-Type**: `application/json`

### 请求参数

| 参数名 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `user_id_list` | `list[str]` | 否 | 需要抓取的用户 ID 列表（若不提供则使用服务端默认配置） |
| `since_date` | `str` / `int` | 否 | 抓取起始时间或最近天数 |

### 请求示例

```bash
curl -X POST http://localhost:5000/api/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "user_id_list": ["1669879400", "1223178222"],
    "since_date": 3
  }'
```

### 响应示例

```json
{
  "code": 200,
  "message": "Task submitted successfully",
  "task_id": "c1f72832-6a45-42ec-99e1-224422731991"
}
```

---

## 2. 查询任务状态

根据返回的 `task_id` 查询异步采集任务的处理进度。

- **URL**: `/api/status`
- **Method**: `GET`
- **Query 参数**: `task_id` (string, 必填)

### 请求示例

```bash
curl http://localhost:5000/api/status?task_id=c1f72832-6a45-42ec-99e1-224422731991
```

### 响应示例

```json
{
  "task_id": "c1f72832-6a45-42ec-99e1-224422731991",
  "status": "completed",
  "progress": 100,
  "result": {
    "crawled_count": 42,
    "error_count": 0
  }
}
```

---

## 3. 获取所有微博

分页查询已存入 SQLite 数据库的微博数据。

- **URL**: `/api/weibo`
- **Method**: `GET`

### Query 参数

| 参数名 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `page` | `int` | `1` | 当前页码 |
| `page_size` | `int` | `20` | 每页返回的条数 |
| `user_id` | `str` | 可选 | 按指定博主 ID 过滤 |

### 响应示例

```json
{
  "code": 200,
  "data": [
    {
      "id": "4454572602912349",
      "bid": "ImTGkcdDn",
      "user_id": "1669879400",
      "screen_name": "Dear-迪丽热巴",
      "text": "今天的#星光大赏#",
      "created_at": "2019-12-28",
      "attitudes_count": 551894,
      "comments_count": 182010,
      "reposts_count": 1000000
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

---

## 4. 获取单条微博详情

根据微博 ID 获取某条微博的完整信息。

- **URL**: `/api/weibo/<id>`
- **Method**: `GET`

### 请求示例

```bash
curl http://localhost:5000/api/weibo/4454572602912349
```
