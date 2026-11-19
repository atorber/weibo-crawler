# 🔌 Weibo 原生透传网关与客户端开发

本项目采用**双层架构定位**，其中**层面一**是 **Weibo 原生接口透明透传网关 (Native Pass-Through Gateway)** 与**客户端开发底座**。

如果你希望用 Python、Node.js、Go 或任何语言**构建自己的微博客户端、自动化发博系统、私信客服或群聊机器人**，无需自行逆向复杂的 Cookie 注入、`X-XSRF-TOKEN` 握手、`source=209678993` 签名、图床 CRC32/MD5 校验或登录态失效恢复——**只需将微博官方域名替换为本地服务地址（默认 `http://127.0.0.1:15001`）**，即可 1:1 调用微博官方原生接口。

---

## 一、两大层面如何选型？

| 维度 | 层面一：Weibo 原生透传网关 & 客户端底座 | 层面二：微博爬虫任务 & 存档查询系统 |
| :--- | :--- | :--- |
| **核心能力** | 1:1 透传 `weibo.com`、`api.weibo.com`、`picupload.weibo.com`、`m.weibo.cn` 原生接口 + 内置发布/私信 SDK | 按目标博主队列批量抓取历史/增量微博，持久化归档至 Markdown/SQLite/MySQL/CSV 并开放检索 |
| **适用场景** | 构建自定义微博客户端、自动化运营发博、私信客服/群聊机器人、实时调用任意微博原生接口 | 博主历史微博全量备份、Markdown+本地高清媒体永久存档、学术/舆情数据集、大模型 RAG 知识库 |
| **入口路由** | ``/ajax/*``、``/webim/*``、``/interface/*``、``/api/container/*``、``/api/publish/*``、``/api/chat/*`` | ``/api/service/*``、``/api/users*``、``/api/data/weibos``、``weibo.py`` |

---

## 二、4 大上游域名 1:1 替换对照表

启动 `python service.py` 后，服务默认监听 `http://127.0.0.1:15001`（可通过 `GET /api/passthrough/info` 查看网关实时状态）：

| 上游官方域名与路径 | 本地透传路径 | 自动代管协议细节 |
| :--- | :--- | :--- |
| ``https://weibo.com/ajax/<subpath>`` | ``http://127.0.0.1:15001/ajax/<subpath>`` | 自动注入 `.weibo.com` Cookie、`X-XSRF-TOKEN`、`Referer: https://weibo.com/`、`X-Requested-With: XMLHttpRequest`；`POST` JSON 自动按 `cleanRequest` 转为 `x-www-form-urlencoded`；遇 403/`ok:-100` 自动重新握手或从浏览器刷新 Cookie 重试 |
| ``https://api.weibo.com/webim/<subpath>`` | ``http://127.0.0.1:15001/webim/<subpath>`` | 自动注入 `.weibo.com` Cookie、`Referer: https://api.weibo.com/chat`；`GET` 自动补齐 `source=209678993&t=<ms>`；`POST` JSON/表单自动补齐 `&source=209678993`；支持 ``/webim/uploadx.json`` 分片上传；遇 `error_code: 21301` 自动刷新 Cookie 重试 |
| ``https://picupload.weibo.com/interface/upload.php``<br>``https://picupload.weibo.com/interface/pic_upload.php`` | ``http://127.0.0.1:15001/interface/upload.php``<br>``http://127.0.0.1:15001/interface/pic_upload.php`` | 支持 `application/octet-stream` 原始字节流或 `multipart/form-data` (`file`/`pic1`)；自动计算 `cs` (CRC32)、`raw_md5`、`file_size`、`uid`、`request_id`；主域名 5xx 时自动回退 `i.api.weibo.com` |
| ``https://m.weibo.cn/<allowlisted_path>`` | ``/api/container/getIndex``、``/comments/hotflow``、``/comments/hotFlowChild``、``/api/comments/show``、``/api/statuses/repostTimeline``、``/statuses/show``、``/detail/<id>``、``/m/api/config`` | 自动注入 `.weibo.cn` Cookie 与 `Referer: https://m.weibo.cn/` |

---

## 三、快速上手：3 种调用方式

### 1. 直接替换域名调用原生接口 (cURL / 任意语言)

```bash
# 1. 查看透传网关就绪状态与挂载表
curl "http://127.0.0.1:15001/api/passthrough/info"

# 2. PC 端原生接口：拉取博主时间线 & 发送微博
curl "http://127.0.0.1:15001/ajax/statuses/mymblog?uid=1669879400&page=1&feature=0"
curl -X POST "http://127.0.0.1:15001/ajax/statuses/update" \
  -H "Content-Type: application/json" \
  -d '{"content": "基于原生透传网关发送测试 #Weibo#", "visible": 1}'

# 3. 私信 WebIM 原生接口：检查登录账号、拉取会话列表、发私信
curl "http://127.0.0.1:15001/webim/query_primary_info.json"
curl "http://127.0.0.1:15001/webim/2/direct_messages/contacts.json?count=20"
curl -X POST "http://127.0.0.1:15001/webim/2/direct_messages/new.json" \
  -H "Content-Type: application/json" \
  -d '{"uid": "1669879400", "text": "你好，这是一条通过 WebIM 透传发送的私信"}'

# 4. 图床原生上传：直接发送二进制图片获取 pid
curl -X POST "http://127.0.0.1:15001/interface/upload.php" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @./photo.jpg
```

### 2. 使用基于透传接口封装的 Python 客户端 SDK

项目内置的 `WeiboPublisher`（微博发布与管理）和 `WeiboChatClient`（私信与群聊）**完全构建在透传层 (`WeiboPassthroughProxy`) 之上**，既是开箱即用的高层 SDK，也是你构建自有客户端的最佳参考范例：

```python
from util.passthrough import WeiboPassthroughProxy
from util.publish import WeiboPublisher
from util.chat import WeiboChatClient

# 共享同一个透传网关实例（也可传 passthrough_base_url="http://127.0.0.1:15001" 走 HTTP 透传）
proxy = WeiboPassthroughProxy()

# 1. 微博发布客户端（底层调用 /ajax/* 与 /interface/* 透传）
pub = WeiboPublisher(proxy=proxy)
print(pub.publish(content="测试仅自己可见微博", visible=1, dry_run=True))

# 2. 私信与群聊客户端（底层调用 /webim/* 透传）
chat = WeiboChatClient(proxy=proxy)
print(chat.check_auth())
print(chat.list_contacts(count=10))
print(chat. raw_request("GET", "2/direct_messages/contacts.json", params={"count": 5}))
print("透传调用链路:", chat.trace)
```

### 3. 使用 CLI 命令行透传工具 (`weibo_ctl.py passthrough`)

```bash
# 查看透传网关状态
python3 skills/weibo-viewer/scripts/weibo_ctl.py passthrough info

# 直接从终端请求任意 /ajax/*、/webim/* 或 m.weibo.cn 透传接口
python3 skills/weibo-viewer/scripts/weibo_ctl.py passthrough request --path /ajax/statuses/config
python3 skills/weibo-viewer/scripts/weibo_ctl.py passthrough request --path /webim/query_primary_info.json
python3 skills/weibo-viewer/scripts/weibo_ctl.py passthrough request --path /api/container/getIndex --param type=uid --param value=1669879400
```

---

## 四、高级控制请求头

在调用任何透传接口时，均可通过以下 HTTP 请求头精细控制网关行为：

| 请求头 / 响应头 | 方向 | 说明 |
| :--- | :--- | :--- |
| `X-Weibo-Cookie` | 请求头 | 为当前单次请求临时指定自定义微博 Cookie（不会修改本地 `config.json`，适合多账号并发调用） |
| `X-Weibo-Raw-Body: 1` | 请求头 | 禁用网关对 `POST` JSON 请求体自动转换为 `application/x-www-form-urlencoded` 的行为，原样透传请求体 |
| `X-Weibo-Passthrough: 1` | 请求头 | 访问 `/api/config` 时若携带该头（或 `?passthrough=1`），将透传至 `https://m.weibo.cn/api/config` |
| `X-Weibo-Passthrough-Upstream` | 响应头 | 每个透传响应自动附带，标明本次实际命中的微博官方上游完整 URL |
