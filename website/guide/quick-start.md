# 快速开始

只需几个简单的步骤，即可在本地运行 Weibo Crawler。

## 1. 下载项目源码

使用 Git 克隆当前项目仓库：

```bash
git clone https://github.com/atorber/weibo-crawler.git
cd weibo-crawler
```

## 2. 安装项目依赖

推荐在虚拟环境（如 `venv` 或 `conda`）中安装依赖：

```bash
# 创建并激活虚拟环境 (可选)
python3 -m venv venv
source venv/bin/activate  # Windows 用户运行: venv\Scripts\activate

# 安装基础依赖
pip install -r requirements.txt
```

如果需要将数据保存至 MySQL 或 MongoDB，需额外安装对应驱动：

```bash
# 若使用 MySQL
pip install pymysql

# 若使用 MongoDB
pip install pymongo
```

## 3. 创建配置文件

项目根目录下提供了配置模板 `config.json.example`，复制一份并重命名为 `config.json`：

```bash
cp config.json.example config.json
```

编辑 `config.json`，填入目标用户的 `user_id`：

```json
{
  "user_id_list": ["1669879400"],
  "only_crawl_original": 1,
  "since_date": "2024-01-01",
  "write_mode": ["csv", "json"],
  "original_pic_download": 1,
  "original_video_download": 0,
  "cookie": "your cookie"
}
```

::: tip 提示
不知道目标博主的 `user_id`？请参阅 [如何获取 User ID](/guide/user-id)。
如果仅仅做简单尝试且博主近期微博数量不多，`cookie` 可以保持默认或留空。
:::

## 4. 运行爬虫

在终端执行：

```bash
python weibo.py
```

执行完毕后，程序将在当前目录下生成 `weibo/` 文件夹：
- 按照用户昵称（或用户 ID）创建专属文件夹，如 `weibo/Dear-迪丽热巴/`
- 里面包含 `1669879400.csv`、`1669879400.json` 结果文件
- 若开启了图片或视频下载，将包含 `img/` 与 `video/` 文件夹
- 若存在下载超时的媒体，会记录在 `not_downloaded.txt` 中供后续重试
