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
