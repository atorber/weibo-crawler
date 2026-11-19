# ✍️ 微博发布与博文管理

除数据采集外，Weibo Crawler 还集成了基于现网 `https://weibo.com/`（`weibo-pro-next`）协议的**微博发布与个人博文管理能力**，支持纯文本、多图上传、定时发布、可见性控制、在线编辑、删除与个人主页时间线实时管理。

---

## 四层架构概览

发布与博文管理功能贯穿项目的四个核心交互层，满足个人日常运营、自动化集成与 AI Agent 托管等不同场景：

| 层级 | 模块 / 入口 | 核心能力 | 参考文档 |
| :--- | :--- | :--- | :--- |
| **1. 核心发布引擎** | `util/publish/weibo_publisher.py` (`WeiboPublisher`) | 会话握手与 `XSRF-TOKEN` 自动刷新、单/多图上传、发布/定时发布、`checkCanEdit` 预检编辑、可见范围调整、删除、个人时间线拉取 | [Python SDK 示例](#python-sdk-示例) |
| **2. RESTful API** | `service.py` (`/api/publish/*`) | 提供 9 个标准 HTTP 接口，含图床防盗链代理与本地发布历史记录（`log/publish_history.json`） | [API 端点文档](/api/endpoints#_7-微博发布与博文管理) |
| **3. Web 可视化控制台** | `/publish` 页面 | 发博表单、本地图片预览 + 代理回显、多可见范围切换、编辑弹窗、二次确认删除及时间线切换 | [Web 控制台操作指南](#web-控制台-publish-操作指南) |
| **4. AI Agent 技能 CLI** | `skills/weibo-viewer/scripts/weibo_ctl.py publish ...` | 支持在线 API 优先 + 离线直调 `WeiboPublisher` 双通道执行 | [Agent 技能指南](/guide/agent-skill#_7-微博发布与博文管理-publish) |

---

## 前置条件与 Cookie 要求

微博发布与博文管理操作对登录凭据有严格要求：

1. **必须使用 `weibo.com` 个人登录态 Cookie**：需包含有效 `SUB` 与 `XSRF-TOKEN` 字段，**不支持匿名访客 Cookie**，也不支持仅登录 `m.weibo.cn` 而缺少 `weibo.com` 会话态的凭据。
2. **优先域提取与自动刷新**：
   - 系统内置的浏览器 Cookie 提取引擎支持 `prefer_domain="weibo.com"` 优先提取主站登录态；
   - `WeiboPublisher.ensure_session()` 会在请求前自动通过 `/ajax/statuses/config` 与 `/ajax/profile/detail` 握手并刷新 `XSRF-TOKEN` 请求头；
   - 若开启 `auto_refresh`，Cookie 失效时会尝试自动从本机已登录浏览器刷新主站凭据。

::: tip 推荐配置方式
打开 Web 控制台后，进入「发布管理」或「总览控制」，点击 **🌐 浏览器提取** 从本地 Chrome / Edge / Firefox / Safari 等浏览器一键导入 `weibo.com` 登录态（详见 [Cookie 获取与验证](/guide/cookie)）。
:::

---

## Web 控制台 `/publish` 操作指南

启动 Web 控制台（`python service.py` 或 `pm2 start ecosystem.config.js`）后，直接访问 [http://127.0.0.1:15001/publish](http://127.0.0.1:15001/publish) 即可进入发布与博文管理界面。

### 1. 发博登录态检测卡片
页面顶部实时检测并展示：
- 当前账号昵称、数字 UID 与 `XSRF-TOKEN` 校验状态；
- 若未登录或仅配置了访客 Cookie，卡片会给出明确提示，并提供一键从本地浏览器提取 `weibo.com` Cookie 的快捷按钮。

### 2. 发布 / 定时发布微博
在发布编辑器中支持以下能力：
- **正文编辑**：支持纯文本、`#话题#` 标签与 `@昵称` 提及；
- **多图上传（最多 18 张）**：支持拖拽或选择本地图片（JPEG / PNG / GIF / WebP），选择时通过 `URL.createObjectURL` 即时预览，上传后获得 `pid` 与图床地址并通过防盗链代理渲染预览图，且支持调整顺序或移除单图；
- **可见范围选择**：支持 5 种可见级别，**默认选用 `1`（仅自己可见）** 以防止误发公开微博；
- **定时发布**：可选指定 `schedule_time`（格式如 `YYYY-MM-DD HH:MM` 或毫秒时间戳），系统强制校验定时时间必须**晚于当前时间至少 10 分钟**；
- **Dry-Run 预检开关**：开启后仅校验登录态、可见范围参数与表单组装，不会真正向微博服务器发出帖子。

### 3. 可见性枚举 (`visible`)

| 取值 | 含义 | 说明 |
| :--- | :--- | :--- |
| `0` | 公开 | 所有人可见 |
| `1` | 仅自己可见 | 私密微博（控制台默认选中，推荐调试/测试时使用） |
| `6` | 好友圈 | 仅互相关注好友可见 |
| `10` | 粉丝可见 | 仅关注自己的粉丝可见 |
| `5` | 群可见 | 指定粉丝群可见 |

### 4. 已发布博文管理列表
控制台下方提供实时个人博文管理面板：
- **数据源切换**：
  - `remote` 模式：实时调用微博接口拉取个人主页最新已发布微博（含完整正文与配图）；若线上接口失败则自动回退到本地发布历史；
  - `local` 模式：直接读取控制台记录的本地历史 `log/publish_history.json`。
- **在线操作**：
  - **修改可见范围**：直接在卡片上切换 `公开 / 仅自己可见 / 好友圈 / 粉丝可见 / 群可见`；
  - **编辑微博**：点击编辑按钮后，系统会先调用 `checkCanEdit` 检查该微博当前是否允许编辑，校验通过后再弹出编辑框并提交修改；
  - **删除微博**：弹出二次确认后执行永久删除；
  - **配图预览**：列表缩略图统一经 `/api/publish/image_proxy` 代理加载，避免本地环境请求新浪图床被防盗链拦截。

---

## Python SDK 示例

除了 Web 界面与 REST API，你也可以在自己的 Python 脚本中直接调用 `WeiboPublisher`：

```python
from util.publish import WeiboPublisher

# 自动从 config/config.json（或根目录 config.json）、cookie 文件 / 环境变量加载凭据
publisher = WeiboPublisher()

# 1. 验证 weibo.com 登录态并刷新 XSRF-TOKEN
session = publisher.ensure_session()
print(session)

# 2. 发布仅自己可见的图文微博（建议先设置 dry_run=True 验证表单）
res = publisher.publish(
    content="Python SDK 发布测试 #自动化#",
    visible=1,
    images=["demo.jpg"],
    dry_run=False,
)
print("发布结果:", res.get("mid"), res.get("url"))

mid = res["mid"]

# 3. 修改可见范围（例如改为公开 0）
publisher.modify_visibility(mid, visible=0)

# 4. 先预检再编辑正文
can_edit = publisher.check_can_edit(mid)
if can_edit.get("can_edit"):
    publisher.edit(mid, content="编辑后的微博正文")

# 5. 获取个人主页微博列表
posts = publisher.list_my_posts(page=1)

# 6. 删除指定微博
# publisher.delete(mid)
```

更多服务接口调用方式可参考 [RESTful API 端点文档](/api/endpoints#_7-微博发布与博文管理) 与 [AI Agent 技能 CLI](/guide/agent-skill#_7-微博发布与博文管理-publish)。

---

## 安全与风控说明

1. **编辑权限限制**：微博官方对编辑功能有账号会员等级（如 VIP）、发博时长与单条微博编辑次数上限限制。系统每次编辑都会默认先执行 `checkCanEdit` 预检，不可编辑时会如实返回原因，避免无效修改请求。
2. **人机校验拦截**：当操作触发微博风控返回 `data.verify`（验证码 / 人机核验）时，工具链会明确提示阻断并保留错误信息，**不会绕过或自动破解验证**，需用户在真实浏览器中访问 `https://weibo.com/` 完成验证后重试。
3. **图床防盗链代理与 SSRF 防护**：新浪 CDN（`*.sinaimg.cn` / `*.weibocdn.com`）会对非 `weibo.com` 来源的浏览器请求返回 `HTTP 403`。`GET /api/publish/image_proxy` 会携带 `Referer: https://weibo.com/` 代理拉取图片流，同时在服务端严格执行**域名白名单校验**并对最多 2 跳重定向逐跳复验目标主机，防止 SSRF 攻击。
