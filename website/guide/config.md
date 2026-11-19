# 完整配置参数指南

所有核心爬虫行为默认通过 `config/config.json` 定义（可从模板 `config/config.json.example` 复制生成，同时向后兼容项目根目录旧版 `config.json`）。系统支持在 **Web 控制台** 中进行表单化可视化配置，也可在源码视图中直接编辑 JSON。

::: tip Cookie 优先级与文件路径约定
- Cookie 支持直接写在配置项 `"cookie"` 中，或填为文件路径（如 `"config/cookie.txt"`）；
- 若设置了环境变量 `WEIBO_COOKIE`，将作为最高优先级覆盖配置文件中的 Cookie。
:::

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-settings.png" alt="参数配置控制台" style="width: 100%; display: block;" />
</div>

---

## 典型配置示例

```json
{
  "user_id_list": ["1669879400"],
  "only_crawl_original": 1,
  "remove_html_tag": 1,
  "since_date": "2024-01-01",
  "start_page": 1,
  "page_weibo_count": 10,
  "write_mode": ["csv", "json"],
  "download_folder_name": {
    "original_image_folder": "img",
    "retweet_image_folder": "img",
    "original_video_folder": "video",
    "retweet_video_folder": "video",
    "original_live_photo_folder": "live_photo",
    "retweet_live_photo_folder": "live_photo"
  },
  "markdown_file_dir": {
    "original_image_dir": "img",
    "retweet_image_dir": "img",
    "original_video_dir": "video",
    "retweet_video_dir": "video",
    "original_live_photo_dir": "live_photo",
    "retweet_live_photo_dir": "live_photo"
  },
  "original_pic_download": 1,
  "retweet_pic_download": 0,
  "original_video_download": 1,
  "retweet_video_download": 0,
  "original_live_photo_download": 1,
  "retweet_live_photo_download": 0,
  "anti_ban_config": {
    "enabled": true,
    "max_weibo_per_session": 500,
    "max_session_time": 600,
    "batch_size": 50,
    "batch_delay": 30,
    "request_delay_min": 8,
    "request_delay_max": 15,
    "max_api_errors": 5,
    "rest_time_min": 180,
    "random_rest_probability": 0.01
  },
  "user_id_as_folder_name": 0,
  "cookie": "your cookie",
  "cookie_auto_config": {
    "enabled": true,
    "browser": "auto",
    "refresh_on_expire": true,
    "check_before_start": true,
    "interval_minutes": 360
  },
  "schedule_config": {
    "enabled": false,
    "interval_minutes": 30
  }
}
```

---

## 参数字典

### 基础抓取控制

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `user_id_list` | `list` / `str` | 必填 | 目标用户列表。可以是一组用户ID `["123456", "789012"]`，也可以是指向本地文本文件的路径如 `"user_id_list.txt"`。 |
| `only_crawl_original` | `int` | `1` | 抓取范围控制。`1` 表示仅抓取原创微博；`0` 表示抓取全部微博（原创 + 转发）。 |
| `since_date` | `str` / `int` | `"1900-01-01"` | 抓取起始时间。可为固定日期字符串（如 `"2024-01-01"`），也可以是整数 $N$（如 `7`），表示抓取最近 $N$ 天发布的微博。 |
| `end_date` | `str` / `int` | `""` | 抓取截止时间（可选）。留空不限制；支持 `"2024-12-31"` 或精确定点时间。 |
| `start_page` | `int` | `1` | 爬取的初始页码。若大批量爬取中途被限制中断，可设置此项从中断页继续爬取。 |
| `page_weibo_count` | `int` | `10` | 每页拉取的微博条数，建议取值 `10` 到 `100`。 |
| `query_list` | `list` / `str` | `[]` | 关键词过滤。留空爬取全部；若设置（如 `["梦想", "旅行"]`），则仅抓取含指定关键词的微博（需有效 Cookie）。 |
| `remove_html_tag` | `int` | `1` | 是否过滤清洗正文中的 HTML 标签。`1` 清洗为纯文本，`0` 保留原始 HTML 节点。 |

---

### 输出与存储控制

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `write_mode` | `list` | `["csv"]` | 数据落盘格式列表，可任意组合：`"csv"`、`"json"`、`"sqlite"`、`"mysql"`、`"mongo"`、`"markdown"`、`"post"`。 |
| `output_directory` | `str` | `"weibo_data"` | 数据与媒体输出根目录，支持相对项目根路径或绝对路径。 |
| `user_id_as_folder_name` | `int` | `0` | 存储目录命名方式。`0` 为使用用户昵称（如 `Dear-迪丽热巴/`）；`1` 为使用纯数字 ID。 |
| `markdown_split_by` | `str` | `"day_by_month"` | Markdown 归档分割粒度：`"day"`（按天）、`"day_by_month"`（按天+按月归档）、`"month"`（按月）、`"year"`（按年）、`"all"`（全部单文件）。 |
| `markdown_sort_order` | `str` | `"new_to_old"` | Markdown 内微博排序方向：`"new_to_old"`（新→旧）或 `"old_to_new"`（旧→新）。 |
| `timestamp_prefix_format` | `str` | `"%Y-%m-%d_%H-%M-%S"` | 媒体文件时间前缀格式（例如改为 `"%Y%m%d_%H%M%S"` 可去掉时间中的横线）。 |
| `timestamp_prefix_include_id` | `int` | `0` | 是否在时间前缀后追加 `_微博ID`：`0` 不追加，`1` 追加。 |
| `not_downloaded_record` | `int` | `0` | 是否记录下载失败清单（下载成功后自动清理）：`0` 不记录，`1` 记录。 |
| `download_folder_name` | `dict` | 见详情 | 本地各类媒体文件（图片/视频/实况/评论图片）存放的子目录配置。 |
| `markdown_file_dir` | `dict` | 见详情 | 生成 Markdown 时内部相对链接引用的媒体子目录配置。 |
| `sqlite_db_path` | `str` | `"weibodata.db"` | 当 `write_mode` 含 `"sqlite"` 时的数据库文件路径。 |
| `mysql_config` | `dict` | 见详情 | MySQL 数据库连接配置（含 `host`, `port`, `user`, `password`, `charset`）。 |
| `mongodb_URI` | `str` | `""` | MongoDB 标准连接 URI，例如 `mongodb://root:pass@localhost:27017/weibo?authSource=admin`。 |
| `store_binary_in_sqlite`| `int` | `0` | 是否在 SQLite 数据库内直接存储图片与视频的二进制 BLOB 原始数据（`0` 关，`1` 开）。 |
| `post_config` | `dict` | 见详情 | 当 `write_mode` 包含 `"post"` 时，配置接收数据的 Webhook `api_url` 和认证 `api_token`。 |

---

### 🛡️ 智能反封禁保护策略 (`anti_ban_config`)

为了应对微博针对持续爬取的动态风控与频率限制，系统内置自适应反封禁保护机制：

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `enabled` | `bool` | `true` | 是否开启智能反封禁保护策略。 |
| `max_weibo_per_session` | `int` | `500` | 单次运行允许爬取的最大微博数。达到该数量后自动暂停，防止单次请求过载。 |
| `max_session_time` | `int` | `600` | 单次连续运行最长耗时（秒）。达到时间后强制冷却休眠。 |
| `batch_size` | `int` | `50` | 批次大小。每连续爬取指定微博数后执行批次延迟。 |
| `batch_delay` | `int` | `30` | 批次之间的冷却等待时长（秒）。 |
| `request_delay_min` | `int` | `8` | 动态随机延迟下限（秒），模拟真实人类翻页行为。 |
| `request_delay_max` | `int` | `15` | 动态随机延迟上限（秒）。 |
| `max_api_errors` | `int` | `5` | 连续 API 错误容忍阈值。达到后自动判定被限频，触发长时保护休眠。 |
| `rest_time_min` | `int` | `180` | 触发风控保护时的长时休眠冷却时长（秒）。 |
| `random_rest_probability` | `float`| `0.01` | 偶发性随机额外延长休眠的概率（0~1）。 |

---

### 多媒体下载控制

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `original_pic_download` | `int` | `1` | 是否下载原创微博高清原图。`1` 下载，`0` 不下载。 |
| `retweet_pic_download` | `int` | `0` | 是否下载转发微博图片（需 `only_crawl_original=0`）。 |
| `original_video_download`| `int` | `1` | 是否下载原创微博高清 MP4 视频。 |
| `retweet_video_download` | `int` | `0` | 是否下载转发微博视频。 |
| `original_live_photo_download` | `int` | `1` | 是否将原创微博 Live Photo 实况照片中的视频单独提取下载。 |
| `retweet_live_photo_download` | `int` | `0` | 是否提取下载转发微博的 Live Photo 视频。 |
| `write_time_in_exif` | `int` | `1` | 是否将微博发布时间写入已下载 JPG 图片的 EXIF 拍摄时间元数据中。 |
| `change_file_time` | `int` | `1` | 是否将下载到本地的文件的修改时间修改为微博发布时间。 |

---

### 🔄 浏览器 Cookie 自动更新与失效热恢复 (`cookie_auto_config`)

控制爬虫与 Web 控制台如何自动从本机浏览器提取、校验并热更新微博 Cookie：

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `enabled` | `bool` | `false` | 是否开启本地浏览器 Cookie 自动提取与更新总开关。 |
| `browser` | `str` | `"auto"` | 目标源浏览器。可选 `"auto"`（自动探测已登录浏览器）、`"chrome"`、`"edge"`、`"firefox"`、`"safari"`、`"brave"`、`"arc"`、`"opera"`。 |
| `refresh_on_expire` | `bool` | `true` | 爬虫运行中遇到 `403` / `432` 或认证失效时，是否自动从浏览器提取新 Cookie 热替换当前 `Session` 并无缝重试（带 15 秒冷却保护）。 |
| `check_before_start` | `bool` | `true` | 每次启动爬虫任务前是否自动探针检测 Cookie，若已失效则先自动从浏览器刷新后再启动。 |
| `interval_minutes` | `int` | `360` | 后台周期性自动同步间隔（分钟）。设为 `0` 表示仅在失效或启动前触发；支持 `30`、`60`、`180`、`360`、`720`、`1440` 等。 |

---

### ⏰ 持续监听与定时增量巡检 (`schedule_config`)

控制 Web 控制台是否开启 7×24 小时定时循环增量爬取：

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `enabled` | `bool` | `false` | 是否开启持续监听模式。开启后每轮爬完自动等待指定间隔并拉起下一轮增量巡检。 |
| `interval_minutes` | `int` | `30` | 两轮增量巡检之间的休眠等待间隔（分钟，从上一轮任务完全结束后开始倒计时，防止并发重叠）。 |

---

### 💬 评论与转发下载

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `download_comment` | `int` | `0` | 是否下载微博评论（含一级评论与二级回复）：`1` 下载，`0` 不下载。 |
| `comment_max_download_count` | `int` | `0` | 单条微博一级评论抓取上限（条），`0` 表示不限制。 |
| `comment_reply_max_download_count` | `int` | `0` | 每条一级评论下的二级回复上限（条），`0` 表示不限制。 |
| `comment_pic_download` | `int` | `0` | 是否下载评论配图：`1` 下载，`0` 不下载。 |
| `comment_user_filter_file` | `str` | `"config/comment_user_filter.txt"` | 评论者白名单文件路径；也可使用 `comment_user_filter` 内联字典配置（未列出的博主不过滤）。 |
| `comment_refresh_scope` | `str` | `"all"` | 评论刷新范围：`all`（刷新本轮抓到的已存档微博）、`recent`（仅最近 N 天）、`off`（仅刷新增微博）。 |
| `download_repost` | `int` | `0` | 是否下载转发详情：`1` 下载，`0` 不下载。 |
| `repost_max_download_count` | `int` | `100` | 单条微博转发记录上限（条）。 |

---

### 📋 报告、存档核对与不可见隔离区

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `weibo_archive_check` | `int` | `0` | 是否生成本轮存档核对报告（需 `write_mode` 含 `"markdown"`）：`1` 生成，`0` 不生成。 |
| `weibo_crawl_summary` | `int` | `0` | 是否生成本轮抓取情况汇总报告（需 `write_mode` 含 `"markdown"`）。 |
| `weibo_media_check` | `int` | `0` | 是否生成媒体完整性核对报告（需 `write_mode` 含 `"markdown"`）。 |
| `weibo_change_report` | `int` | `1` | 是否生成微博变化审计报告（记录正文编辑、可见性改变、疑似不可见、恢复可见等变更）。 |
| `weibo_deleted_report` | `int` | `1` | 抓取结束后是否在用户目录生成 `已删除微博.txt`。 |
| `invisible_archive_enabled` | `int` | `1` | 不可见微博隔离区总开关：`1` 启用，`0` 关闭。 |
| `invisible_confirm_rounds` | `int` | `2` | 连续多少轮全量巡检未抓到时判定为「疑似不可见」。 |
| `invisible_archive_dir` | `str` | `"已不可见"` | 隔离区目录名（相对用户目录）或绝对路径。 |

::: tip 常用配置体检与维护脚本
```bash
# 预览配置差异与迁移检查（不修改文件）；如需自动补全并备份可执行 --update-config
python weibo.py --check-config

# 部署后一键环境与模块自检（含导入检查与配置键提示）
python scripts/weibo_selfcheck.py

# 按需运行全量存档核对或历史评论回填（需配置项对应开启）
python scripts/weibo_archive_check_full.py
python scripts/weibo_comment_backfill.py
```
:::


