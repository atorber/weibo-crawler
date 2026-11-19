# 项目简介（双层架构定位）

**Weibo Crawler** 采用清晰的**双层架构定位**，分别服务于两类核心需求场景：

1. **🔌 层面一：Weibo 原生接口透明透传网关 & 客户端开发底座**
   - **适用场景**：开发者希望使用任意语言构建**自定义微博客户端、自动化发博与运营工具、私信客服或群聊机器人**。
   - **核心能力**：只需将 `https://weibo.com`、`https://api.weibo.com`、`https://picupload.weibo.com` 或 `https://m.weibo.cn` 的域名与端口替换为本地服务（默认 `http://127.0.0.1:15001`），即可 1:1 调用微博原生接口，由网关自动代管 Cookie、`X-XSRF-TOKEN` 握手、`source=209678993` 参数、图床 CRC32/MD5 校验及登录态失效自动刷新重试；同时内置完全基于透传层封装的 **微博发布客户端 (`WeiboPublisher` / `/publish`)** 与 **私信群聊客户端 (`WeiboChatClient` / `/chat`)**。详见 [Weibo 原生透传网关与客户端开发](/guide/passthrough)。
2. **🕷️ 层面二：微博爬虫任务调度、持久化存档 & 开放数据查询引擎**
   - **适用场景**：用户需要对一个或多个目标博主进行**历史微博全量/增量备份、Markdown + 本地高清媒体永久存档、学术/舆情数据集构建、大模型 (LLM) RAG 知识库与历史微博检索**。
   - **核心能力**：支持多博主队列与 7×24 小时定时增量巡检，完整抓取正文、一级评论/二级回复、原图、视频与 Live Photo，同步落盘至 CSV、JSON、Markdown、SQLite、MySQL、MongoDB、Webhook，并通过 `/api/data/weibos` 与 AI Agent 技能开放多维查询。

![Weibo Crawler 现代化 Web 控制台](/images/console-dashboard.png)

---

## 核心双层架构设计

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                        共享基础层：认证与配置 (Auth & Config)                    │
│   config/config.json · util/browser_cookie.py · 免密提取 & 过期自动热刷新        │
└──────────────────────┬───────────────────────────────────┬────────────────────┘
                       │                                   │
                       ▼                                   ▼
┌─────────────────────────────────────────────┐ ┌───────────────────────────────┐
│  层面一：Weibo 原生透传网关 & 客户端开发底座     │ │  层面二：微博爬虫任务 & 存档查询  │
│  (Weibo Native Pass-Through & Client SDK)   │ │  (Crawler Task, Archive & DB) │
├─────────────────────────────────────────────┤ ├───────────────────────────────┤
│ 1. 1:1 原生透传路由 (替换域名端口即用):          │ │ 1. 任务调度与巡检引擎:           │
│    • /ajax/<path>       → weibo.com/ajax/*  │ │    • weibo.py 主爬虫子进程       │
│    • /webim/<path>      → api.weibo.com/*   │ │    • 持续监听定时增量巡检        │
│    • /interface/*.php   → picupload.weibo   │ │    • 目标博主队列 (/api/users)   │
│    • /api/container/*   → m.weibo.cn/*      │ │ 2. 多介质落盘与核对报告:         │
│    • /comments/hotflow* → m.weibo.cn/*      │ │    • Markdown / CSV / JSON    │
│ 2. 基于透传接口构建的官方客户端示范:            │ │    • SQLite / MySQL / MongoDB │
│    • WeiboPublisher (/api/publish/*, 发博)   │ │    • 存档核对 / 媒体检查 / 回填  │
│    • WeiboChatClient (/api/chat/*, 私信群聊) │ │ 3. 开放数据检索接口:             │
│                                             │ │    • /api/data/weibos, /weibos│
└─────────────────────────────────────────────┘ └───────────────────────────────┘
```

---

## 核心特性一览

### 1. 现代化可视化 Web 控制台
- **仪表盘监控与持续监听**：实时统计博主队列、抓取状态、Cookie 认证连通性检测，支持一键开启 **⏰ 持续监听模式（定时自动增量巡检）** 与实时倒计时展示。
- **免密从浏览器提取 Cookie 与 403 失效热恢复**：一键安全提取本地 Chrome、Edge、Firefox、Safari、Brave 等已登录浏览器的 Cookie；支持后台周期性自动同步，以及在爬虫运行中遇到 403/过期时自动从浏览器提取新 Cookie 热替换当前会话并无缝重试。
- **多数据源连通性测试**：在 Web 界面对 MySQL、MongoDB、Webhook 进行即时探测，故障前置排除。
- **实时日志大屏**：终端风格的彩色实时流式日志，掌握每一条微博的采集与下载进度。

### 2. 多用户连续与增量爬取
- **批量博主管理**：支持维护数十甚至上百个目标博主，配置可视化增删查改。
- **增量自动记忆**：支持 `since_date` 动态倒推及独立文件时间戳更新，仅拉取增量微博，杜绝重复采集。
- **追加模式 (Append Mode)**：检测到最新抓取重合即刻结束，大幅降低请求频次与网络流量。

### 3. 全方位智能反封禁保护
- **随机延迟与抖动**：支持设置随机休眠区间，模拟人类真实滑动浏览轨迹。
- **智能退避与熔断**：捕获 414/418/403 等异常信号后自动进行梯度休眠，避免 IP 被拉黑。
- **夜间自适应静默**：配置闲时降低爬取频率或暂停工作，守护账号长期健康。

### 4. 丰富的数据输出介质矩阵
- 默认支持 **CSV** 表格、**JSON** 结构化数据。
- 支持 **SQLite**、**MySQL** 与 **MongoDB**。
- 支持 HTTP **POST Webhook** 实时向外部中台、Kafka 网关或微服务推送数据。

### 5. 多媒体高清资产完整归档
- **原图 & 视频归档**：批量下载原创及转发微博的高清大图、高清视频和 Live Photo 动态照片。
- **EXIF 拍摄时间写入**：自动将微博发布时间写入图片的 EXIF 原始拍摄日期中，与手机相册完美协同。

### 6. AI Agent 技能集成 (weibo-viewer)
- 内置开箱即用的智能体 Skill 包，赋能大语言模型（LLM）与 Agent 系统（Antigravity、Claude Code、Cursor 等）。
- 具备双通道 CLI 调度工具与 REST API，支持 Agent 自动化启停任务、监控状态、对本地微博知识库进行高精度的关键词检索与舆情摘要，以及触发微博发布与博文管理。详情请参阅 [AI Agent 技能指南](/guide/agent-skill)。
- **规范相对路径**：所有媒体资源默认按模块英文相对路径分类管理（`img/`、`video/`、`live_photo/`），防止跨平台中文乱码。

### 7. ✍️ 微博发布与博文管理
- 基于现网 `https://weibo.com/`（`weibo-pro-next`）协议，提供独立控制台页面 `/publish`、`/api/publish/*` REST API、`WeiboPublisher` SDK 与 Agent CLI。
- 支持纯文本、`#话题#`、最多 18 张多图上传与定时发布（至少晚于当前 10 分钟）、可见范围控制（`0` 公开 / `1` 仅自己可见 / `6` 好友圈 / `10` 粉丝可见 / `5` 群可见）、`checkCanEdit` 预检编辑、删除及图床防盗链代理预览。详情请参阅 [微博发布与博文管理](/guide/publish)。

### 8. 📋 评论归档、存档核对与健康自检
- 支持一级评论与二级回复分页抓取、评论图片与表情下载、评论者白名单过滤及历史评论增量回填脚本（`scripts/weibo_comment_backfill.py`）。
- 内置每轮与全量存档核对、媒体完整性检查、编辑/可见性变化报告（`weibo_change_report`）、已不可见微博隔离区保护，以及部署自检与配置体检命令（`python scripts/weibo_selfcheck.py`、`python weibo.py --check-config`）。详情请参阅 [完整配置参数](/guide/config)。

---

## 运行环境

| 环境项 | 最低要求 | 推荐配置 |
| --- | --- | --- |
| 操作系统 | Windows / Linux / macOS | Ubuntu 22.04+ 或 macOS Sonoma / Sequoia |
| Python 版本 | Python 3.10+ | Python 3.10 ~ 3.12 |
| 网络连接 | 能稳定访问 `weibo.cn` / `m.weibo.cn` / `weibo.com` | 优质稳定的网络带宽或云服务器环境 |

