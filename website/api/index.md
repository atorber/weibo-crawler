# Web 控制台与 RESTful API

项目根目录下的 `service.py` 提供了可视化的 **Web 管理控制台** 与标准化 RESTful API 接口。

启动后你可以通过浏览器直接访问图形化控制台，也可以通过 HTTP 接口实现自动化集成：
- 🎛️ **服务调度控制**：一键启动、停止、重启爬虫进程，实时监控运行状态与任务耗时
- 👥 **爬取目标管理**：可视化管理目标博主队列，支持批量导入导出、单个博主单独触发采集
- ⚙️ **参数配置中心**：分类表单与 JSON 源码双向实时同步，集成 Cookie 连通性测试
- 📜 **实时日志终端**：黑客风格高亮终端，支持日志级别筛选、关键字过滤与自动滚屏
- 🗄️ **数据检索预览**：随时检索浏览本地 SQLite 采集入库的历史微博记录

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-api.png" alt="RESTful API 接口中心" style="width: 100%; display: block;" />
</div>

---

## 启动服务

在根目录下执行：

```bash
python service.py
```

默认将在 `http://127.0.0.1:5001` 启动服务，并在浏览器中打开控制台。

::: tip 生产环境部署
如需在生产环境部署，建议结合 Gunicorn 或 uWSGI：
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 service:app
```
:::

---

## Web 控制台独立页面路由

Web 控制台已内置标准化独立路由系统，支持在浏览器地址栏直接输入访问或添加书签：

| 功能板块 | 独立路由地址 | 对应功能 |
| :--- | :--- | :--- |
| **总览控制** | `/` 或 `/dashboard` | 核心运行指标、Cookie 探测与进程调度 |
| **目标管理** | `/targets` | 目标博主队列维护与单博主采集触发 |
| **参数配置** | `/settings` | 爬虫参数调整与智能反封禁策略 |
| **数据存储** | `/output` | 7 种数据输出介质配置与即时连通性测试 |
| **实时日志** | `/logs` | 终端风格实时彩色流式日志 |
| **数据预览** | `/data` | 多维筛选（博主/发布时间/关键字）历史微博 |
| **API 文档** | `/api-docs` 或 `/docs` | 内置交互式 RESTful API 接口中心与 cURL 范例 |

