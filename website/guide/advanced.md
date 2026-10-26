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
