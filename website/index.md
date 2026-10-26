---
layout: home

hero:
  name: "Weibo Crawler"
  text: "新浪微博数据采集利器"
  tagline: "持续爬取微博用户数据，支持增量采集、多格式输出、评论转发与高清多媒体下载"
  image:
    src: /logo.svg
    alt: Weibo Crawler
  actions:
    - theme: brand
      text: 快速开始
      link: /guide/quick-start
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
  - icon: 🖥️
    title: 现代 Web 可视化控制台
    details: 内置轻量响应式 Web 控制台，支持目标队列维护、参数可视化调控、实时图表大屏与日志流排查。
  - icon: 🤖
    title: AI Agent 技能 (weibo-viewer)
    details: 内置标准化 Agent 扩展包，支持大模型智能体自主调度爬虫、按关键词多维搜索与分析微博数据。
  - icon: 🔑
    title: 浏览器 Cookie 免密读取
    details: 无需繁琐 F12 抓包，一键自动探测提取 Chrome、Edge、Firefox、Safari、Brave 本地登录态。
  - icon: 🛡️
    title: 智能反封禁与限频引擎
    details: 内置自适应请求频率限制、会话最大爬取上限、错误熔断与动态拟人随机休眠保护。
  - icon: 💾
    title: 丰富输出与连通性测试
    details: 独立数据存储配置，支持 CSV、JSON、SQLite、MySQL、MongoDB、Webhook 与 Markdown，自带一键连通性测试。
  - icon: 📸
    title: 原图/视频/实况下载
    details: 支持无损大图、高清 MP4 视频、Live Photo 动态视频提取及拍摄时间 EXIF 自动回写。
  - icon: 🔄
    title: 定时增量与 Docker
    details: 支持增量去重抓取与单次限制，内置标准 Dockerfile 与 docker-compose，开箱即用。
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

```bash [Web 控制台启动（推荐）]
# 1. 克隆代码仓库
git clone https://github.com/atorber/weibo-crawler.git
cd weibo-crawler

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动 Web 控制台
python service.py
# 浏览器访问 http://127.0.0.1:15001 即刻体验
```

```bash [命令行直接运行]
# 1. 复制配置文件
cp config.json.example config.json

# 2. 填写 config.json 中的 cookie 和 user_id_list

# 3. 运行爬虫
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

