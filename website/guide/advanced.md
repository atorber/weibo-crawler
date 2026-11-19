# 二次开发与 Python 调用

除了通过命令行启动外，你还可以将 Weibo Crawler 直接作为 Python 模块引入你自己的工程项目中。

## 在代码中调用 Weibo 核心类

所有核心业务逻辑封装于 `weibo.py` 中的 `Weibo` 类：

```python
import json
from weibo import Weibo

# 1. 构造配置字典
my_config = {
    "user_id_list": ["1669879400"],
    "only_crawl_original": 1,
    "since_date": "2024-01-01",
    "write_mode": ["csv", "json"],
    "original_pic_download": 0,
    "original_video_download": 0,
    "cookie": "your_cookie_here"
}

# 2. 实例化爬虫对象
wb = Weibo(my_config)

# 3. 启动抓取
wb.start()

# 4. 从内存中直接获取数据对象
print("目标博主昵称:", wb.user['screen_name'])
print("粉丝数量:", wb.user['followers_count'])

# wb.weibo 包含抓取到的微博列表（列表元素为字典）
print(f"共采集到 {len(wb.weibo)} 条微博")
if wb.weibo:
    latest_post = wb.weibo[0]
    print("最新一条微博内容:", latest_post['text'])
    print("发布时间:", latest_post['created_at'])
```

---

## 核心属性概览

在调用 `wb.start()` 执行结束后，爬虫实例具备以下对象：

- **`wb.user`**：包含当前正在处理博主的完整画像数据字典，如 `id`, `screen_name`, `gender`, `birthday`, `location`, `verified` 等。
- **`wb.weibo`**：列表类型，按时间倒序存放当前博主抓取到的微博列表。当 `only_crawl_original=1` 时，`wb.weibo[0]` 即为博主最新发布的原创微博。

---

## 在代码中调用 WeiboPublisher（微博发布与管理 SDK）

除爬虫核心类 `Weibo` 外，你也可以直接引入 `util/publish` 中的 `WeiboPublisher` 在 Python 程序中实现发博、定时发布、修改可见范围、`checkCanEdit` 预检编辑与删除管理：

```python
from util.publish import WeiboPublisher

# 默认自动读取 config/config.json（兼容根目录 config.json）、cookie 文件或 WEIBO_COOKIE
publisher = WeiboPublisher()

# 1. 验证 weibo.com 个人登录态并刷新 XSRF-TOKEN
auth_res = publisher.ensure_session()
print("登录态:", auth_res.get("logged_in"), auth_res.get("screen_name"))

# 2. 发布仅自己可见（visible=1）的图文微博；可先设 dry_run=True 进行预检
pub_res = publisher.publish(
    content="Python 模块调用测试 #自动化#",
    visible=1,
    images=["demo.jpg"],
    schedule_time=None,  # 如需定时，可传入 "2026-12-01 09:00"（须晚于当前时间 >= 10 分钟）
    dry_run=False,
)
mid = pub_res["mid"]
print("发布成功:", mid, pub_res.get("url"))

# 3. 调整可见范围（0=公开, 1=仅自己可见, 6=好友圈, 10=粉丝可见, 5=群可见）
publisher.modify_visibility(mid, visible=0)

# 4. 编辑前先做 checkCanEdit 预检，再提交正文修改
can_edit_res = publisher.check_can_edit(mid)
if can_edit_res.get("can_edit"):
    publisher.edit(mid, content="修改后的微博正文")

# 5. 获取个人主页最新微博列表 / 删除微博
timeline = publisher.list_my_posts(page=1)
# publisher.delete(mid)
```

关于可见性枚举、Cookie 要求与安全限制详情，请参阅 [微博发布与博文管理](/guide/publish)。
