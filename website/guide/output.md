# 输出内容与格式

Weibo Crawler 采集到的数据涵盖 **用户信息** 与 **微博详情** 两大核心模块，并支持 7 种丰富的数据输出介质。

---

## 数据输出介质矩阵 (write_mode)

系统支持按需启用多种输出介质，在 Web 控制台的「数据存储」页面中，每个介质均配备专属开关与参数校验：

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-storage.png" alt="数据输出配置" style="width: 100%; display: block;" />
</div>

| 介质类型 | 配置值 (`write_mode`) | 适用场景 | 说明 |
| :--- | :--- | :--- | :--- |
| **CSV 表格** | `"csv"` | Excel 数据透视、快速统计分析 | 导出逗号分隔的结构化 `.csv` 文件，支持中文字符集 |
| **JSON 文件** | `"json"` | 程序化二次处理、文本挖掘 | 导出标准 `.json` 字典，含完整媒体字段与转发嵌套字典 |
| **SQLite 数据库** | `"sqlite"` | 单机轻量持久化、无需搭建数据库 | 默认存储至 `weibodata.db`，支持媒体二进制直接入库 |
| **MySQL 关系库** | `"mysql"` | 企业级大数据分析、多用户协作 | 自动建表（`weibo`、`user`、`comment`），utf8mb4 表情支持 |
| **MongoDB 文档库** | `"mongo"` | 灵活文档检索、海量非结构化存储 | 自动创建 `weibo` 集合，支持复杂查询与副本集 URI |
| **HTTP Webhook** | `"post"` | 实时消息推送、下游系统接入 | 微博写入时实时发送带有 Token 签名的 HTTP POST Webhook |
| **Markdown 归档** | `"markdown"` | 本地知识库（Obsidian/Notion/博客） | 图文排版归档，支持按月/天分割与 8 类多媒体嵌入预览 |

---

## 规范的媒体相对路径结构

为了确保在不同操作系统（macOS / Linux / Windows）、Docker 容器以及 Markdown 知识库查看器中均能无损读取图片与视频，系统默认采用规范的英文相对路径：

```text
weibo_data/
└── Dear-迪丽热巴/                 # 博主专属目录（可按配置使用纯数字 UID）
    ├── 1669879400.csv            # 表格文件
    ├── 1669879400.json           # JSON 结构化数据
    ├── img/                      # 图片相对目录
    │   ├── 20240101123000_xxx.jpg
    │   └── ...
    ├── video/                    # 高清 MP4 视频相对目录
    │   ├── 20240101123000_xxx.mp4
    │   └── ...
    ├── live_photo/               # Live Photo 动态视频相对目录
    │   ├── 20240101123000_xxx.mov
    │   └── ...
    └── not_downloaded.txt        # 网络抖动超时媒体重试清单
```

::: tip 避免中文乱码最佳实践
- 默认配置中 `download_folder_name` 与 `markdown_file_dir` 均已采用 `img`、`video`、`live_photo`。
- 如果你的博客或 Markdown 编辑器对中文路径有兼容限制，保持使用相对英文路径可以杜绝 URL 编码乱码与 404 找不到文件的情况。
:::

---

## 用户信息字段

当爬虫访问目标博主主页时，会抓取以下博主档案数据：

| 字段名称 | 示例 / 说明 |
| --- | --- |
| `id` | 微博数字 ID，如 `"1669879400"` |
| `screen_name` | 微博昵称，如 `"Dear-迪丽热巴"` |
| `gender` | 性别：`"f"` (女) 或 `"m"` (男) |
| `birthday` | 出生日期或星座信息 |
| `location` | 所在地，如 `"上海"` |
| `education` | 教育背景及毕业院校 |
| `company` | 所在所属公司名称 |
| `sunshine` | 阳光信用评级，如 `"信用极好"` |
| `registration_time` | 微博账号注册时间 |
| `statuses_count` | 历史发布的总微博数（原创 + 转发） |
| `followers_count` | 粉丝数量 |
| `follow_count` | 关注博主数量 |
| `description` | 个人主页自我介绍/简介 |
| `profile_url` | 移动版微博主页完整链接 |
| `profile_image_url` | 用户头像 URL |
| `avatar_hd` | 高清原始头像 URL |
| `urank` | 微博成长等级数值 |
| `mbrank` | 微博会员等级（非会员为 0） |
| `verified` | 是否通过官方认证（`true` / `false`） |
| `verified_type` | 认证类别标识（个人认证、企业认证、官方机构等） |
| `verified_reason` | 官方认证身份备注描述信息 |

---

## 微博信息字段

每条微博记录包含完整的正文、互动指标与多媒体资源：

| 字段名称 | 类型 | 说明 |
| --- | --- | --- |
| `id` | int / str | 微博数字全局唯一标识符 |
| `bid` | str | 微博 Base62 编码 ID（与微博网页端 URL 后缀一致） |
| `text` | str | 微博正文（可根据配置去除 HTML 格式标签） |
| `article_url` | str | 若含有头条文章，记录头条长文 URL 地址 |
| `pics` | str | 原创微博的高清图片 URL（多张图片以英文逗号 `,` 分隔） |
| `video_url` | str | 原创微博的视频 MP4 播放地址（多视频以分号 `;` 分割） |
| `live_photo_url` | str | 原创微博的 Live Photo 视频源地址 |
| `location` | str | 发送微博时附带的地理位置名称（如无则为空） |
| `created_at` | str | 发布时间，格式为 `yyyy-mm-dd` 或标准时间 |
| `source` | str | 发布客户端来源，如 `"iPhone 15 Pro"`、`"微博网页版"` |
| `attitudes_count` | int | 获得的赞/点赞总数 |
| `comments_count` | int | 评论总数 |
| `reposts_count` | int | 转发总数 |
| `topics` | str | 微博参与的话题标签（多个以英文逗号 `,` 分隔） |
| `at_users` | str | 微博正文中 `@` 提及的用户昵称列表 |
| `retweet` | dict / obj | **转发微博特有**：内嵌原始微博的完整对象（原作者 ID、原正文、原媒体等） |

---

## 异常网络下载恢复机制 (`not_downloaded.txt`)

若在抓取海量高清图片或大体积视频时，由于网络瞬时波动导致某个媒体文件下载超时，爬虫**不会异常退出中断**。

它会自动将出错记录记录在 `not_downloaded.txt` 中（格式为 `weibo_id:media_url`），不仅保障长任务平稳完成，更方便后续针对失败清单进行断点补抓。

