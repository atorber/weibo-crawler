# RESTful API 概述

除了本地命令行或脚本调用，项目根目录下的 `service.py` 提供了基于 Flask 框架构建的标准化 RESTful API 接口。

通过 HTTP 接口，你可以轻松实现：
- 远程触发指定用户的微博数据抓取任务
- 异步查询爬虫任务执行进度与状态
- 通过 API 检索获取已存储在本地 SQLite 中的微博数据

---

## 启动 API 服务

在根目录下执行：

```bash
python service.py
```

默认将在 `http://0.0.0.0:5000` 监听请求。

::: tip 生产环境部署
如需在生产环境部署，建议结合 Gunicorn 或 uWSGI：
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 service:app
```
:::

---

## 预配置与环境变量

在 `service.py` 文件内部，定义了默认的全局调度配置 `config`（包含用户列表、存储模式、SQLite 数据库路径等）。若需调整默认参数，可直接在 `service.py` 开头的配置项中修改。
