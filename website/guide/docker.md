# Docker 与 PM2 后台部署

本项目在 `deploy/` 目录下提供了官方 `deploy/Dockerfile` 与 `deploy/docker-compose.yml`，并在根目录提供了 `ecosystem.config.js`（PM2 配置），方便在云服务器、家庭 NAS（群晖、威联通、极空间、Unraid）或本地主机长期稳定运行。

系统支持**三种后台运行形态**：
1. **Web 控制台容器化运行**（推荐）：暴露 `15001` 端口，随时通过浏览器访问管理后台、查看实时日志与发布管理 `/publish`。
2. **静默定时爬取容器模式**：作为后台守护容器，按设定的时间间隔自动周期循环爬取。
3. **本地 PM2 进程守护部署**：直接在宿主机使用 PM2 管理 `service.py`，兼顾本地浏览器 Cookie 自动提取与断线自动重启。

---

## 方式一：Web 控制台容器化运行（推荐）

通过容器启动 Web 控制台，可以在任意设备上通过网页直接管理爬虫。注意宿主机配置文件默认位于 `config/config.json`，数据输出默认位于 `weibo_data/`。

### 1. 构建镜像

在项目根目录下指定 `deploy/Dockerfile` 构建：

```bash
docker build -f deploy/Dockerfile -t weibo-crawler .
```

### 2. 运行 Web 控制台

```bash
docker run -d \
  --name weibo-crawler-web \
  -p 15001:15001 \
  -v $(pwd)/config/config.json:/app/config/config.json \
  -v $(pwd)/weibo_data:/app/weibo_data \
  --restart unless-stopped \
  weibo-crawler python service.py
```

容器启动后，在局域网或公网浏览器中访问 ``http://<服务器IP>:15001`` 即可进入现代化 Web 控制台。

---

## 方式二：静默定时爬取模式 (CLI)

适合无人值守的周期性增量数据拉取。

```bash
docker run -it -d \
  --name weibo-crawler \
  -v $(pwd)/config/config.json:/app/config/config.json \
  -v $(pwd)/config/user_id_list.txt:/app/config/user_id_list.txt \
  -v $(pwd)/weibo_data:/app/weibo_data \
  -e schedule_interval=60 \
  --restart unless-stopped \
  weibo-crawler
```

::: tip 环境变量解释
`schedule_interval`：指定定时循环抓取的间隔时长（单位：分钟）。设置后容器会在后台常驻，每隔指定分钟数触发一次全量/增量采集。
:::

---

## Docker Compose 部署

仓库内 `deploy/docker-compose.yml` 已配置仓库根作为构建上下文，并挂载 `../config/config.json` 与 `../weibo_data`（启动前请先参考 `config/config.json.example` 准备好 `config/config.json`）：

```bash
cd deploy
docker compose up -d --build
```

若需要同时在 Compose 中启动 Web 控制台服务，可参考如下服务定义（以项目根目录为 `context`）：

```yaml
services:
  # Web 控制台服务（按需映射 15001 端口）
  weibo-web:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    command: python service.py
    ports:
      - "15001:15001"
    volumes:
      - ../config/config.json:/app/config/config.json
      - ../weibo_data:/app/weibo_data
    restart: unless-stopped

  # 后台定时静默任务（与 deploy/docker-compose.yml 一致）
  weibo-crawler:
    build:
      context: ..
      dockerfile: deploy/Dockerfile
    image: weibo-crawler:local
    restart: always
    volumes:
      - ../config/config.json:/app/config/config.json:ro
      - ../weibo_data:/app/weibo_data
    environment:
      - schedule_interval=1
```

查看运行日志：

```bash
docker compose logs -f
```

---

## 方式三：本地 PM2 进程守护部署

如果你需要在本机直接读取 Chrome / Edge / Safari 浏览器 Cookie（实现热更新与 `weibo.com` 发博鉴权），推荐使用 PM2 守护运行 `service.py`。项目根目录已内置 `ecosystem.config.js`，会自动检测 `.venv/` 或 `venv/` 中的 Python 解释器并监听 `0.0.0.0:15001`（内存超过 `500M` 自动平滑重启）：

```bash
# 1. 启动控制台守护进程（应用名 weibo-console）
pm2 start ecosystem.config.js

# 2. 查看运行状态与实时日志
pm2 status
pm2 logs weibo-console

# 3. 重启或保存开机自启列表
pm2 restart weibo-console
pm2 save
```

