# Web 控制台与双层架构 API 概览

项目根目录下的 `service.py` 同时承载了本项目的**两大架构层面**，既提供可视化的 **Web 管理控制台**，也提供面向开发者的 **Weibo 原生透传网关** 与 **爬虫存档查询 RESTful API**：

### 🔌 层面一：Weibo 原生透传网关 & 客户端开发底座
- **Weibo 原生接口 1:1 透明透传**：只需将 `https://weibo.com`、`https://api.weibo.com`、`https://picupload.weibo.com` 或 `https://m.weibo.cn` 替换为 `http://127.0.0.1:15001` 即可直接调用微博原生路径，自动代管 Cookie、`source=209678993`、`X-XSRF-TOKEN` 及过期自动刷新（详见 [Weibo 原生透传网关指南](/guide/passthrough) 与 [接口端点文档](/api/endpoints)）
- **网关自描述探针**：`GET /api/passthrough/info` 实时查看当前网关 Cookie 就绪状态与 4 大上游域名映射规则
- **✍️ 微博发布客户端 (`/publish` & `/api/publish/*`)**：基于 `/ajax/*` 与 `/interface/*` 透传构建，支持纯文本/多图（最多 18 张）/定时微博、可见性切换、`checkCanEdit` 编辑与删除（详见 [微博发布与博文管理](/guide/publish)）
- **💬 微博私信与群聊客户端 (`/chat` & `/api/chat/*`)**：基于 `/webim/*` 透传构建，支持联系人/群聊检索、历史消息、图文附件收发、3 分钟内消息撤回、删除、一键已读与 WebIM 原生透传调试台

### 🕷️ 层面二：微博爬虫任务调度 & 存档数据查询
- **🎛️ 爬虫任务调度 (`/api/service/*`)**：一键启动、停止、重启爬虫子进程，开启 7×24 小时持续监听定时增量巡检
- **👥 爬取目标管理 (`/targets` & `/api/users*`)**：可视化管理目标博主队列，支持批量导入导出与单博主触发采集
- **⚙️ 参数配置与存储矩阵 (`/settings`, `/output` & `/api/config`)**：分类表单与 JSON 源码双向同步，支持 Markdown/SQLite/MySQL/MongoDB/CSV/JSON/Webhook 7 种介质
- **🗄️ 存档数据开放检索 (`/data` & `/api/data/weibos`)**：按博主、日期范围、正文关键词多维分页检索本地 SQLite 归档微博与实时日志流 (`/logs`)

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-api.png" alt="RESTful API 接口中心" style="width: 100%; display: block;" />
</div>

---

## 启动服务

在根目录下执行：

```bash
python service.py
```

默认将在 `http://127.0.0.1:15001` 启动服务，并在浏览器中打开控制台。

::: tip 生产环境部署
如需在生产环境常驻运行，可使用仓库内置的 PM2 配置或结合 Gunicorn 启动：
```bash
# 方式 A：使用内置 ecosystem.config.js 通过 PM2 守护运行（监听 0.0.0.0:15001）
pm2 start ecosystem.config.js

# 方式 B：使用 Gunicorn 多进程托管
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:15001 service:app
```
:::

---

## Web 控制台独立页面路由

Web 控制台已内置标准化独立路由系统，支持在浏览器地址栏直接输入访问或添加书签：

| 功能板块 | 独立路由地址 | 对应功能 |
| :--- | :--- | :--- |
| **总览控制** | `/` 或 `/dashboard` | 核心运行指标、Cookie 探测与进程调度 |
| **发布管理** | `/publish` | 微博发布（纯文本/多图/定时）、可见性切换、编辑、删除与个人博文列表 |
| **私信管理** | `/chat` | 微博私信与群聊工作台：会话列表、历史消息、图文附件收发、撤回与已读 |
| **目标管理** | `/targets` | 目标博主队列维护与单博主采集触发 |
| **参数配置** | `/settings` | 爬虫参数调整与智能反封禁策略 |
| **数据存储** | `/output` | 7 种数据输出介质配置与即时连通性测试 |
| **实时日志** | `/logs` | 终端风格实时彩色流式日志 |
| **数据预览** | `/data` | 多维筛选（博主/发布时间/关键字）历史微博 |
| **API 文档** | `/api-docs` 或 `/docs` | 内置交互式 RESTful API 接口中心与 cURL 范例 |

