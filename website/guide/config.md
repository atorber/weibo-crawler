# 完整配置参数指南

所有核心爬虫行为均通过 `config.json` 进行定义。

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
  "original_pic_download": 1,
  "retweet_pic_download": 0,
  "original_video_download": 1,
  "retweet_video_download": 0,
  "original_live_photo_download": 1,
  "retweet_live_photo_download": 0,
  "download_comment": 0,
  "comment_max_download_count": 1000,
  "download_repost": 0,
  "repost_max_download_count": 1000,
  "user_id_as_folder_name": 0,
  "cookie": "your cookie",
  "write_time_in_exif": 1,
  "change_file_time": 1
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
| `start_page` | `int` | `1` | 爬取的初始页码。若大批量爬取中途被限制中断，可设置此项从中断页继续爬取。 |
| `page_weibo_count` | `int` | `10` | 每页拉取的微博条数，建议取值 `10` 到 `100`，数值越大通常网络吞吐效率越高。 |
| `query_list` | `list` / `str` | `[]` | 关键词过滤。留空爬取全部；若设置（如 `["梦想", "旅行"]` 或 `"梦想,旅行"`），则仅抓取含指定关键词的微博（需配置 Cookie）。 |
| `remove_html_tag` | `int` | `1` | 是否过滤清洗正文与评论中的 HTML 标签。`1` 为清洗纯文本，`0` 为保留原始 HTML 节点。 |

### 输出与存储控制

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `write_mode` | `list` | `["csv"]` | 数据落盘格式列表，可任意组合：`"csv"`、`"json"`、`"sqlite"`、`"mysql"`、`"mongo"`、`"markdown"`、`"post"`。 |
| `user_id_as_folder_name` | `int` | `0` | 存储目录命名方式。`0` 为使用用户昵称（如 `Dear-迪丽热巴/`）；`1` 为使用固定数字ID（如 `1669879400/`），适合自动化长期归档。 |
| `mysql_config` | `dict` | 见详情 | MySQL 数据库连接配置（含 `host`, `port`, `user`, `password`, `charset`）。 |
| `mongodb_URI` | `str` | `""` | MongoDB 标准连接 URI，例如 `mongodb://root:pass@localhost:27017/`。 |
| `store_binary_in_sqlite`| `int` | `0` | 是否在 SQLite 数据库内直接存储图片与视频的二进制 BLOB 数据（`0` 关，`1` 开）。 |
| `post_config` | `dict` | 见详情 | 当 `write_mode` 包含 `"post"` 时，配置接收数据的 Webhook `api_url` 和认证 `api_token`。 |

### 多媒体下载控制

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `original_pic_download` | `int` | `1` | 是否下载原创微博高清原图。`1` 下载，`0` 不下载。 |
| `retweet_pic_download` | `int` | `0` | 是否下载转发微博图片（需 `only_crawl_original=0`）。 |
| `original_video_download`| `int` | `1` | 是否下载原创微博视频。`1` 下载，`0` 不下载。 |
| `retweet_video_download` | `int` | `0` | 是否下载转发微博视频（需 `only_crawl_original=0`）。 |
| `original_live_photo_download` | `int` | `1` | 是否将原创微博 Live Photo 中的动效视频单独提取下载。 |
| `retweet_live_photo_download` | `int` | `0` | 是否下载转发微博中的 Live Photo 视频。 |
| `write_time_in_exif` | `int` | `1` | 是否将微博发布时间写入已下载 JPG/JPEG 图片的 EXIF 元数据中。 |
| `change_file_time` | `int` | `1` | 是否将下载到本地的文件的修改时间修改为微博发布时间。 |

### 评论与转发抓取

::: warning 注意
评论与转发深度采集目前主要用于 SQLite 写入模式。
:::

| 参数名 | 类型 | 默认值 | 详细说明 |
| --- | --- | --- | --- |
| `download_comment` | `int` | `0` | 是否爬取每条微博下的一级评论。`1` 开启，`0` 关闭。 |
| `comment_max_download_count` | `int` | `1000`| 每条微博允许下载的最大评论上限条数。 |
| `download_repost` | `int` | `0` | 是否爬取每条微博下的转发链条。`1` 开启，`0` 关闭。 |
| `repost_max_download_count` | `int` | `1000` | 每条微博允许下载的最大转发上限条数。 |
