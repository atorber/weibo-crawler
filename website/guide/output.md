# 输出内容与格式

爬虫采集到的数据主要分为 **用户信息** 与 **微博详情** 两大模块。

## 用户信息字段

当爬虫访问目标主页时，会抓取以下博主档案数据：

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
| `video_url` | str | 原创微博的视频/Live Photo MP4 播放地址（多视频以分号 `;` 分割） |
| `location` | str | 发送微博时附带的地理位置名称（如无则为空） |
| `created_at` | str | 发布时间，格式通常为 `yyyy-mm-dd` 或精确时间 |
| `source` | str | 发布客户端来源，如 `"iPhone 15 Pro"`、`"微博网页版"` |
| `attitudes_count` | int | 获得的赞/点赞总数 |
| `comments_count` | int | 评论总数 |
| `reposts_count` | int | 转发总数 |
| `topics` | str | 微博参与的话题标签（多个以英文逗号 `,` 分隔） |
| `at_users` | str | 微博正文中 `@` 提及的用户昵称列表 |
| `retweet` | dict / obj | **转发微博特有**：内嵌原始微博的完整对象（原作者 ID、原正文、原视频图片等） |

---

## 多媒体与异常处理文件

在结果目录下，文件结构如下：

```
weibo/
└── Dear-迪丽热巴/
    ├── 1669879400.csv           # 表格形式的微博数据
    ├── 1669879400.json          # 结构化 JSON 数据
    ├── img/                     # 微博原图文件夹
    │   ├── 20240101_4981...jpg
    │   └── ...
    ├── video/                   # 微博视频与 Live Photo 视频
    │   ├── 20240101_4981...mp4
    │   └── ...
    └── not_downloaded.txt       # 下载超时的媒体记录清单
```

::: tip not_downloaded.txt 说明
若因为网络抖动个别图片或视频下载失败，程序不会抛出异常中断，而是将出错记录写入 `not_downloaded.txt`（格式为 `weibo_id:media_url`），确保整个爬取流程顺利完成。
:::
