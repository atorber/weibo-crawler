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
      text: 配置参数手册
      link: /guide/config
    - theme: alt
      text: RESTful API
      link: /api/

features:
  - icon: 🎯
    title: 目标全面采集
    details: 支持单用户或批量连续爬取，获取完整用户信息（昵称、认证、关注粉丝等）与微博详情（正文、工具、点赞评论转发）。
  - icon: 🔄
    title: 增量与定期更新
    details: 自动记录历史爬取进度，支持动态日期与追加模式，结合 Crontab 或定时任务轻松实现自动增量采集。
  - icon: 💾
    title: 多种数据存储方式
    details: 开箱即用支持 CSV、JSON、SQLite，并无缝对接 MySQL、MongoDB 及 Webhook POST 转发。
  - icon: 📸
    title: 高清图片与视频下载
    details: 支持原创/转发微博的原图批量保存、视频高清下载、Live Photo 视频提取及 EXIF 拍摄时间自动回写。
  - icon: 💬
    title: 评论与转发深度采集
    details: 支持爬取微博一级评论与转发链条信息，满足舆情监控、社会网络分析与学术研究需求。
  - icon: 🐳
    title: Docker & API 服务支持
    details: 提供标准化 Dockerfile 与 docker-compose 配置，内置基于 Flask 的 RESTful API 接口与任务队列。
---

<div class="vp-doc" style="margin-top: 3rem; text-align: center;">

## 30秒极速体验

```bash
# 1. 克隆代码仓库
git clone https://github.com/atorber/weibo-crawler.git
cd weibo-crawler

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 复制并调整配置
cp config.json.example config.json

# 4. 运行爬虫
python weibo.py
```

</div>
