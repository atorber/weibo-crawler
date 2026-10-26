# Docker 容器化部署

本项目提供了官方 `Dockerfile` 与 `docker-compose.yml`，方便在云服务器、NAS 或群晖等环境中以容器方式一键部署并稳定运行。

## Docker CLI 启动

1. 在当前项目根目录构建镜像：

```bash
docker build -t weibo-crawler .
```

2. 启动容器（挂载本地配置文件与输出目录）：

```bash
docker run -it -d \
  --name weibo-crawler \
  -v $(pwd)/config.json:/app/config.json \
  -v $(pwd)/user_id_list.txt:/app/user_id_list.txt \
  -v $(pwd)/weibo:/app/weibo \
  -e schedule_interval=60 \
  weibo-crawler
```

::: tip 环境变量解释
`schedule_interval`：指定定时循环抓取的间隔时长（单位：分钟）。设置后容器会在后台常驻，每隔指定分钟数触发一次采集。
:::

---

## Docker Compose 部署

项目已内置 `docker-compose.yml`：

```yaml
version: '3'
services:
  weibo-crawler:
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
# 后台启动
docker compose up -d

# 查看运行日志
docker compose logs -f
```
