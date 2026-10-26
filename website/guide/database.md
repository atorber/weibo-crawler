# 数据库存储指南

Weibo Crawler 原生支持 **MySQL**、**MongoDB** 和 **SQLite** 三种主流数据库，适合企业生产分析或本地科研实验。

## SQLite 存储（开箱即用）

无需安装额外服务，在 `config.json` 中配置即可：

```json
{
  "write_mode": ["sqlite"]
}
```

程序启动后会自动在项目根目录下生成并维护 `weibodata.db` 文件，同时支持将图片/视频二进制直接写入（通过设置 `"store_binary_in_sqlite": 1`）。

---

## MySQL 存储配置

### 1. 安装依赖

```bash
pip install pymysql
```

### 2. 修改配置

在 `config.json` 中设置 `write_mode` 包含 `"mysql"`，并配置连接认证参数：

```json
{
  "write_mode": ["mysql"],
  "mysql_config": {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "your_password",
    "charset": "utf8mb4"
  }
}
```

程序启动时将自动创建名为 `weibo` 的数据库，并建立两张核心数据表：`user`（用户信息表）与 `weibo`（微博详情表）。

### 3. 数据表结构设计

::: details 查看 user 表字段
- `id` (VARCHAR): 微博用户唯一数字 ID
- `screen_name` (VARCHAR): 微博昵称
- `gender` (VARCHAR): 性别 ('f' / 'm')
- `birthday` (VARCHAR): 生日或星座
- `location` (VARCHAR): 所在地
- `education` (VARCHAR): 教育经历
- `company` (VARCHAR): 所属公司
- `sunshine` (VARCHAR): 阳光信用
- `registration_time` (VARCHAR): 注册时间
- `statuses_count` (INT): 微博发布总数
- `followers_count` (INT): 粉丝数
- `follow_count` (INT): 关注数
- `description` (TEXT): 个人主页简介
- `profile_url` (VARCHAR): 移动端主页 URL
- `profile_image_url` (VARCHAR): 头像 URL
- `avatar_hd` (VARCHAR): 高清头像 URL
- `urank` (INT): 微博等级
- `mbrank` (INT): 会员等级
- `verified` (TINYINT): 认证状态
- `verified_type` (INT): 认证类型
- `verified_reason` (VARCHAR): 认证描述
:::

::: details 查看 weibo 表字段
- `id` (VARCHAR): 微博 ID（主键）
- `user_id` (VARCHAR): 关联作者 ID（外键关联 user 表）
- `screen_name` (VARCHAR): 作者昵称
- `text` (LONGTEXT): 微博正文文本
- `article_url` (VARCHAR): 头条文章链接
- `pics` (TEXT): 原始配图 URL 列表（逗号分隔）
- `video_url` (TEXT): 原始视频 URL 列表（分号分隔）
- `location` (VARCHAR): 发博地点
- `created_at` (VARCHAR): 发布时间
- `source` (VARCHAR): 发布设备/客户端来源
- `attitudes_count` (INT): 点赞数
- `comments_count` (INT): 评论数
- `reposts_count` (INT): 转发数
- `topics` (VARCHAR): 涉及话题列表
- `at_users` (VARCHAR): 被 @ 提及的用户
- `retweet_id` (VARCHAR): 转发的原微博 ID（原创微博为空）
:::

---

## MongoDB 存储配置

### 1. 安装依赖

```bash
pip install pymongo
```

### 2. 修改配置

在 `config.json` 中配置：

```json
{
  "write_mode": ["mongo"],
  "mongodb_URI": "mongodb://root:password@localhost:27017/weibo?authSource=admin"
}
```

爬虫在 MongoDB 中对应创建 `user` 与 `weibo` 两个集合（Collections），数据会自动根据用户 ID 与微博 ID 执行 Upsert（存在则更新，不存在则插入）。

---

## HTTP POST Webhook 实时推送

若你希望将抓取到的新微博实时流式推送到自己的企业微信机器人、钉钉机器人或业务系统接口，可开启 Webhook 推送：

```json
{
  "write_mode": ["post"],
  "post_config": {
    "api_url": "https://api.yourdomain.com/v1/weibo/webhook",
    "api_token": "Bearer YOUR_SECRET_TOKEN"
  }
}
```

- **请求头**：系统在发起 POST 请求时会自动携带 `Authorization` 鉴权头与 `Content-Type: application/json`。
- **Payload**：每次采集到微博时，推送包含用户信息与微博全量字段的 JSON 数据。

---

## ⚡ 存储介质一键连通性测试

无论使用 MySQL、MongoDB 还是 Webhook，配置错误（如密码错误、端口未放行、URI 鉴权库不正确）往往要等到爬虫运行数分钟后才会报错。

在 Web 控制台的 **「数据存储」** 页面中，每个卡片底部均内置了 **即时连通性测试引擎**：

<div style="border-radius: 8px; overflow: hidden; margin: 18px 0; border: 1px solid var(--vp-c-divider);">
  <img src="/images/console-storage.png" alt="连通性测试" style="width: 100%; display: block;" />
</div>

- **无需提前保存**：直接读取你当前在输入框中填写的参数，点击即可触发底层握手测试。
- **即时反馈诊断**：
  - **MySQL**：连接成功时反馈 MySQL 服务端版本号与延迟毫秒；失败时打印拒绝代码。
  - **MongoDB**：执行内部 `ping` 与 `server_info`，测试 4 秒超时保护。
  - **Webhook**：向接收端发送带有 Token 的 ping 包，精准反馈 HTTP 状态码（如 200 OK、401 Unauthorized、404 Not Found）及响应延迟。

