---
layout: home

hero:
  name: "Weibo Crawler"
  text: "Weibo 原生透传网关 & 微博爬虫存档引擎"
  tagline: "双层架构：一层提供 1:1 微博原生透传接口赋能构建自定义客户端；一层提供全量/增量爬虫任务、多格式持久化存档与开放查询"
  image:
    src: /logo.svg
    alt: Weibo Crawler
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quick-start
    - theme: alt
      text: 🔌 透传网关与客户端开发
      link: /guide/passthrough
    - theme: alt
      text: 控制台体验
      link: /guide/quick-start#方式一：web-可视化控制台操作（推荐）
    - theme: alt
      text: 配置参数手册
      link: /guide/config
    - theme: alt
      text: RESTful API
      link: /api/
    - theme: alt
      text: 🤖 Agent 技能
      link: /guide/agent-skill

features:
  - icon: 🔌
    title: "层面一：Weibo 原生接口透明透传网关"
    details: 只需将 weibo.com、api.weibo.com、picupload.weibo.com 或 m.weibo.cn 替换为 http://127.0.0.1:15001 即可 1:1 调用原生接口，自动代管 Cookie、X-XSRF-TOKEN、source 与失效自动刷新。
    link: /guide/passthrough
  - icon: ✍️
    title: "层面一：基于透传构建的发布与私信客户端"
    details: 内置基于透传层封装的微博发布管理 (/publish, 多图/定时/可见性/编辑/删除) 与私信群聊工作台 (/chat, 会话/历史/附件收发/撤回/已读)。
    link: /guide/publish
  - icon: 🕷️
    title: "层面二：持续增量爬虫任务与反封禁引擎"
    details: 支持多博主队列批量全量/增量采集、7×24 小时定时巡检、自适应频率限制、动态拟人休眠与存档核对/变化审计报告。
    link: /guide/intro
  - icon: 💾
    title: "层面二：多介质存档与开放数据检索"
    details: 支持 Markdown 永久存档、SQLite、MySQL、MongoDB、CSV、JSON 与 Webhook，完整归档一级评论/二级回复并提供 /api/data/weibos 多维查询。
    link: /guide/output
  - icon: 🖥️
    title: 现代 Web 可视化控制台
    details: 侧边栏按「爬虫任务与存档查询」和「透传网关与微博客户端」双层分区，支持实时监控大屏、私信调试台与日志流排查。
  - icon: 🤖
    title: AI Agent 技能 (weibo-viewer)
    details: 内置标准化 Agent 扩展包，支持大模型智能体自主调度爬虫、检索历史归档、发布博文、收发私信或直调任意原生透传接口。
    link: /guide/agent-skill
  - icon: 🔑
    title: 浏览器 Cookie 免密读取与热恢复
    details: 一键探测提取 Chrome、Edge、Firefox、Safari 本地登录态，同时为透传网关与爬虫任务提供 403/21301 过期自动热替换无缝重试。
  - icon: 📸
    title: 原图/视频/实况下载与 Docker 部署
    details: 支持无损大图、高清 MP4 视频、Live Photo 动态视频提取及 EXIF 拍摄时间回写；提供 PM2 与 Docker 容器化常驻方案。
---

<div class="vp-doc" style="margin-top: 3.5rem;">

<div style="text-align: center; margin-bottom: 2rem;">
  <h2 style="font-size: 2rem; font-weight: 800; border-top: none; margin-bottom: 0.5rem;">🖥️ 现代化 Web 控制台</h2>
  <p style="color: var(--vp-c-text-2); font-size: 1.05rem; max-width: 720px; margin: 0 auto;">
    告别黑盒命令行与复杂配置代码，只需一条命令即可开启全功能的可视化任务调度与状态监控大屏。
  </p>
</div>

<div style="border-radius: 12px; overflow: hidden; box-shadow: 0 16px 40px rgba(0, 0, 0, 0.25); border: 1px solid var(--vp-c-divider); margin-bottom: 3.5rem;">
  <img src="/images/console-dashboard.png" alt="Weibo Crawler Web 控制台总览" style="width: 100%; display: block;" />
</div>

## ⚡ 30秒极速体验

::: code-group

```bash [Web 控制台一键启动（推荐）]
# 1. 克隆代码仓库
git clone https://github.com/atorber/weibo-crawler.git
cd weibo-crawler

# 2. 一键启动（自动检查/安装依赖、初始化配置并打开 http://127.0.0.1:15001）
./start.sh          # macOS / Linux
start.bat           # Windows（支持直接双击运行）

# 或使用 PM2 后台常驻运行 Web 控制台
pm2 start ecosystem.config.js
```

```bash [命令行直接运行]
# 1. 复制配置文件到 config/ 目录（同时向后兼容根目录 config.json）
cp config/config.json.example config/config.json

# 2. 填写 config/config.json 中的 cookie 和 user_id_list

# 3. 运行爬虫（可先执行 --check-config 检查配置差异）
python weibo.py
```

:::

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.5rem; margin-top: 2.5rem;">
  <div style="padding: 1.5rem; border-radius: 8px; background-color: var(--vp-c-bg-soft); border: 1px solid var(--vp-c-divider);">
    <h3 style="font-size: 1.15rem; margin-top: 0;">🎯 目标博主队列维护</h3>
    <p style="color: var(--vp-c-text-2); font-size: 0.92rem; line-height: 1.6;">
      支持维护多个博主 UID 队列，为不同博主独立配置采集起始日期与关键词过滤，支持一键单选即刻执行。
    </p>
    <img src="/images/console-targets.png" alt="目标管理" style="border-radius: 6px; margin-top: 10px; border: 1px solid var(--vp-c-divider);" />
  </div>

  <div style="padding: 1.5rem; border-radius: 8px; background-color: var(--vp-c-bg-soft); border: 1px solid var(--vp-c-divider);">
    <h3 style="font-size: 1.15rem; margin-top: 0;">📤 独立数据存储与测试</h3>
    <p style="color: var(--vp-c-text-2); font-size: 0.92rem; line-height: 1.6;">
      集成 CSV、JSON、SQLite、MySQL、MongoDB、Webhook、Markdown，每个介质配备独立开关与实时连通性探测。
    </p>
    <img src="/images/console-storage.png" alt="数据存储" style="border-radius: 6px; margin-top: 10px; border: 1px solid var(--vp-c-divider);" />
  </div>
</div>

</div>

