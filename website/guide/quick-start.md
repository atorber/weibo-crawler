# 快速开始

Weibo Crawler 提供了两种便捷的运行模式：**现代化 Web 可视化控制台**（推荐，零代码、免改 JSON）与 **经典纯命令行模式**（适合自动化脚本与服务器定时任务）。

---

## 1. 下载源码与环境准备

在开始之前，确保本地已安装 Python 3.8 或更高版本。

```bash
# 1. 克隆代码仓库
git clone https://github.com/atorber/weibo-crawler.git
cd weibo-crawler

# 2. 创建并激活虚拟环境 (推荐)
python3 -m venv venv
source venv/bin/activate  # Windows 用户: venv\Scripts\activate

# 3. 安装依赖包 (已包含 Web 服务、Cookie 免密读取与数据库驱动)
pip install -r requirements.txt
```

---

## 方式一：Web 可视化控制台操作（推荐）

通过内置的 Web 控制台，你可以享受现代化界面带来的极大便利：**无需手动找 F12 抓包 Cookie、无需手动编辑复杂的 JSON 配置文件，一切皆在可视化界面完成**。

### 1. 启动控制台服务

在项目根目录下直接运行一键启动脚本（或手动执行 `python service.py`）：

```bash
# macOS / Linux 一键启动（自动检查环境、安装缺失依赖并打开浏览器）
./start.sh

# Windows 一键启动（支持直接双击 start.bat 运行）
start.bat

# 或手动通过 Python 启动
python service.py
```

终端将打印本地访问地址，在浏览器中打开：
👉 [http://127.0.0.1:15001](http://127.0.0.1:15001)

### 2. 控制台功能与界面概览

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-dashboard.png" alt="控制台总览" style="width: 100%; display: block;" />
</div>

- **一键浏览器提取 Cookie**：进入「总览控制」，点击 **🌐 浏览器提取**，系统会自动探测你本地已登录微博的浏览器（Chrome / Edge / Firefox / Safari / Brave），一键完成鉴权与连通性检测，免去繁琐的控制台抓包过程。
- **维护目标博主队列**：进入「目标管理」，可随时添加目标博主 UID，为不同博主独立配置采集起始日期与关键词过滤。

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-targets.png" alt="目标管理" style="width: 100%; display: block;" />
</div>

- **独立数据输出与连通性测试**：进入「数据存储」，独立开启 CSV、JSON、SQLite、MySQL、MongoDB、Webhook 与 Markdown，开启前支持点击 `⚡ 测试连通性` 验证数据库或接口状态。

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-storage.png" alt="数据存储配置" style="width: 100%; display: block;" />
</div>

### 3. 一键启动采集

点击页面右上角的 **▶ 启动爬虫** 按钮，任务即刻在后台执行。你可以切换到 **📜 实时日志** 页面，观察带高亮配色的彩色实时输出。

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-logs.png" alt="实时日志监控" style="width: 100%; display: block;" />
</div>

---

## 方式二：纯命令行脚本运行（CLI）

如果你在没有桌面图形环境的 Linux 云服务器上运行，或者需要结合 `crontab` 实现定时任务，可使用纯命令行方式。

### 1. 复制并调整配置文件

从示例模板复制出 `config.json`：

```bash
cp config.json.example config.json
```

编辑 `config.json`，填入目标用户的 `user_id_list` 及 Cookie：

```json
{
  "user_id_list": ["1669879400"],
  "only_crawl_original": 1,
  "since_date": "2024-01-01",
  "write_mode": ["csv", "json"],
  "original_pic_download": 1,
  "original_video_download": 0,
  "download_folder_name": {
    "original_image_folder": "img",
    "retweet_image_folder": "img",
    "original_video_folder": "video",
    "retweet_video_folder": "video",
    "original_live_photo_folder": "live_photo",
    "retweet_live_photo_folder": "live_photo"
  },
  "cookie": "SCF=...; SUB=...;"
}
```

::: tip 提示
- 不知道目标博主的数字 ID？请参阅 [如何获取 User ID](/guide/user-id)。
- 详细 Cookie 说明请参阅 [Cookie 获取与验证](/guide/cookie)。
:::

### 2. 运行爬虫脚本

在终端中执行：

```bash
python weibo.py
```

### 3. 查看输出成果

抓取完毕后，爬虫默认将在 `weibo_data/` 目录下生成规范结构：

```text
weibo_data/
└── Dear-迪丽热巴/                 # 默认博主昵称（或纯数字 UID 文件夹）
    ├── 1669879400.csv            # 结构化表格文件
    ├── 1669879400.json           # 完整 JSON 字典
    ├── img/                      # 高清无损原创/转发图片
    ├── video/                    # 高清 MP4 原创/转发视频
    └── live_photo/               # 提取的 Live Photo 动态视频
```

