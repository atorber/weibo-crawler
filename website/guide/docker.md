# Docker 容器化部署

本项目提供了官方 `Dockerfile` 与 `docker-compose.yml`，方便在云服务器、家庭 NAS（群晖、威联通、极空间、Unraid）等环境中以容器方式一键部署并稳定运行。

系统支持**两种运行形态**：
1. **Web 控制台服务模式**（推荐）：暴露 `5001` 端口，随时通过浏览器访问管理后台、查看大屏与实时日志。
2. **静默定时爬取模式**：作为后台守护进程，按设定的时间间隔自动周期循环爬取。

---

## 方式一：Web 控制台容器化运行（推荐）

通过容器启动 Web 控制台，可以在任意设备上通过网页直接管理爬虫。

### 1. 构建镜像

```bash
docker build -t weibo-crawler .
```

### 2. 运行 Web 控制台

```bash
docker run -d \
  --name weibo-crawler-web \
  -p 5001:5001 \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/weibo:/app/weibo \
  --restart unless-stopped \
  weibo-crawler python service.py
```

容器启动后，在局域网或公网浏览器中访问 `http://<服务器IP>:5001` 即可进入现代化 Web 控制台。

---

## 方式二：静默定时爬取模式 (CLI)

适合无人值守的周期性增量数据拉取。

```bash
docker run -it -d \
  --name weibo-crawler \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/user_id_list.txt:/app/user_id_list.txt \
  -v $(pwd)/weibo:/app/weibo \
  -e schedule_interval=60 \
  --restart unless-stopped \
  weibo-crawler
```

::: tip 环境变量解释
`schedule_interval`：指定定时循环抓取的间隔时长（单位：分钟）。设置后容器会在后台常驻，每隔指定分钟数触发一次全量/增量采集。
:::

---

## Docker Compose 部署

项目已内置多功能 `docker-compose.yml`：

```yaml
version: '3.8'
services:
  # Web 控制台服务（按需映射 5001 端口）
  weibo-web:
    build:
      context: .
      dockerfile: Dockerfile
    command: python service.py
    ports:
      - "5001:5001"
    volumes:
      - ./config.json:/app/config.json
      - ./weibo:/app/weibo
    restart: unless-stopped

  # 可选：后台定时静默任务
  weibo-cron:
    build:
      context: .
      dockerfile: Dockerfile
    volumes:
      - ./config.json:/app/config.json
      - ./user_id_list.txt:/app/user_id_list.txt
      - ./weibo:/app/weibo
    environment:
      - schedule_interval=60
    restart: unless-stopped
```

一键启动与查看日志：

```bash
# 启动所有服务（或指定单个服务 weibo-web）
docker compose up -d weibo-web

# 查看运行日志
docker compose logs -f weibo-web
```

