# 🤖 AI Agent 技能集成 (weibo-viewer)

为了让大语言模型（LLM）与智能体系统（如 Antigravity、Claude Code、Cursor、LangChain、AutoGen 等）能够自主操作爬虫并分析微博数据，本项目内置了开箱即用的 **Agent Skill 扩展包**：`skills/weibo-viewer`。

通过该 Skill，AI Agent 可以理解微博爬虫的生命周期，通过标准化 CLI 工具或 REST API 自主执行：
- 🔍 **多维数据检索**：按博主、日期起止、正文关键词模糊搜索或互动排序抓取的微博；
- 🎮 **爬取任务编排**：动态添加/移除博主、触发增量抓取、终止或重启服务；
- 📊 **状态与日志监控**：监控爬虫进程健康状态、统计指标、排查反爬日志；
- 🔑 **凭据自动维护**：诊断 Cookie 状态并从本地浏览器自动提取更新。

---

## 📁 Skill 目录结构

技能包位于仓库根目录的 `skills/weibo-viewer`：

```text
skills/weibo-viewer/
├── SKILL.md                  # 核心技能指引（包含 frontmatter 描述、触发时机与标准 runbook）
├── scripts/
│   └── weibo_ctl.py          # 供 Agent 执行的高可用 CLI 辅助工具（双通道通信）
└── references/
    └── api_reference.md      # 控制台 REST API 与 SQLite 数据库表结构完整参考
```

---

## ⚡ 一键安装：使用提示词从 GitHub 安装

无论您使用的是 **Google Antigravity**、**Claude Code**、**Cursor**、**Windsurf** 还是其他支持 Agent Skill / Customizations 的 AI 助手，都**无需手动下载或配置**。

只需**复制以下提示词**，直接发送给您的 AI 助手：

::: tip 💡 复制下方提示词直接发给您的 AI 助手
```text
请帮我从 GitHub 安装微博爬虫技能 (weibo-viewer)：

1. 目标仓库：https://github.com/atorber/weibo-crawler.git（分支 master）
2. 将其中的 skills/weibo-viewer/ 目录下载并安装到我的环境：
   - 如果是当前项目生效：安装到 .agents/skills/weibo-viewer/
   - 如果想全局跨项目生效：安装到 ~/.gemini/config/skills/weibo-viewer/
3. 确保完整包含 SKILL.md、scripts/weibo_ctl.py 及 references/api_reference.md，并为 scripts/weibo_ctl.py 赋予可执行权限 (chmod +x)；
4. 运行 `python .agents/skills/weibo-viewer/scripts/weibo_ctl.py status` 验证安装成功。
```
:::

AI 助手收到后会自动调用工具拉取 GitHub 资源、创建对应目录并测试连通性，秒级完成安装与就绪验证！

---

### 💻 备选：终端一键 Curl 安装

如果您更习惯在终端直接通过命令行下载安装，也可以直接在项目根目录下粘贴执行以下命令：

```bash
# 1. 创建技能目录
mkdir -p .agents/skills/weibo-viewer/scripts .agents/skills/weibo-viewer/references

# 2. 从 GitHub 下载核心文件
curl -sSL https://raw.githubusercontent.com/atorber/weibo-crawler/master/skills/weibo-viewer/SKILL.md -o .agents/skills/weibo-viewer/SKILL.md
curl -sSL https://raw.githubusercontent.com/atorber/weibo-crawler/master/skills/weibo-viewer/scripts/weibo_ctl.py -o .agents/skills/weibo-viewer/scripts/weibo_ctl.py
curl -sSL https://raw.githubusercontent.com/atorber/weibo-crawler/master/skills/weibo-viewer/references/api_reference.md -o .agents/skills/weibo-viewer/references/api_reference.md

# 3. 赋予执行权限并测试
chmod +x .agents/skills/weibo-viewer/scripts/weibo_ctl.py
python .agents/skills/weibo-viewer/scripts/weibo_ctl.py status
```

> [!NOTE] 本仓库用户免安装
> 如果您已经通过 `git clone` 下载了本项目的完整源码，仓库已内置 `skills/weibo-viewer` 并默认建立了 `.agents/skills/weibo-viewer` 软链接，直接即可使用，无需再次安装！

---

## 🛠️ CLI 辅助工具：`weibo_ctl.py`

Agent 通常通过调用命令行工具 [weibo_ctl.py](file:///Users/luyuchao/Documents/GitHub/weibo-crawler/skills/weibo-viewer/scripts/weibo_ctl.py) 来完成各类复杂操作。

> [!TIP] 双通道高可用架构
> `weibo_ctl.py` 优先通过 HTTP API（`http://127.0.0.1:15001/api/...`）与运行中的控制台服务通信；若 Web 控制台处于休眠或离线状态，脚本会**自动回退直接连接本地 SQLite 数据库（`weibodata.db`）**与本地文件，确保查询 100% 始终可用。

所有子命令均支持 `--json` 参数，以便 Agent 直接获取结构化 JSON 并无缝进行下文解析与推断。

---

## 🚀 常见操作指南

### 1. 监控服务与爬虫状态

Agent 可随时探测爬虫进程健康状况及已采集的数据量：

```bash
# 格式化终端输出
python skills/weibo-viewer/scripts/weibo_ctl.py status

# Agent 结构化 JSON 输出
python skills/weibo-viewer/scripts/weibo_ctl.py status --json
```

**返回示例**：
```text
Service Status : ⚪ IDLE (IDLE)
Process PID    : N/A
Current Target : None
Running Time   : 0s
Total Weibos   : 37
Total Users    : 1
DB Connected   : Yes
```

---

### 2. 多维搜索与查看微博

Agent 可以像搜索引擎一样在本地抓取的微博知识库中执行高精度检索：

```bash
# 1. 关键词查询（模糊匹配微博正文与话题标签）
python skills/weibo-viewer/scripts/weibo_ctl.py query --keyword "英伟达" --limit 5

# 2. 按博主 UID 筛选
python skills/weibo-viewer/scripts/weibo_ctl.py query --user-id 1445403190 --limit 10

# 3. 按发布日期区间筛选 (YYYY-MM-DD)
python skills/weibo-viewer/scripts/weibo_ctl.py query --start-date 2026-10-01 --end-date 2026-10-26

# 4. 按互动热度排序（点赞数、评论数、转发数）
python skills/weibo-viewer/scripts/weibo_ctl.py query --sort attitudes_count --limit 5

# 5. 输出纯 JSON 供大模型进一步分析或撰写简报
python skills/weibo-viewer/scripts/weibo_ctl.py query --keyword "财报" --json
```

**检索结果展示**：
```text
🔍 Query Results: Found 12 total records (Showing 2 on page 1)
================================================================================
[1] 财富密钥 | 🕒 2026-10-22 09:05:33 | 🔗 https://weibo.com/1445403190/RnOd83FRi
    👍 5  💬 0  🔄 0  
    📝 【盘前导读核心提要0922：美股AI走出颓势，短期AI科技会走强】
1、【美股三大指数集体收涨 ，英伟达持续扩建AI生态】...
--------------------------------------------------------------------------------
[2] 财富密钥 | 🕒 2026-10-21 21:18:45 | 🔗 https://weibo.com/1445403190/RnJAf4Z9F
    👍 13  💬 2  🔄 0  
    📝 【英伟达炸圈】
今日，英伟达GTC大会在柏林如期举行。会上，黄仁勋直言，“经过计算机行业数十年的发展，我们现在正处于新一轮工业革命的开端。”...
--------------------------------------------------------------------------------
```

---

### 3. 管理监控博主列表

Agent 可根据用户对话动态调整待采集的博主名单：

```bash
# 查看当前配置的所有博主
python skills/weibo-viewer/scripts/weibo_ctl.py users list

# 新增目标博主 UID
python skills/weibo-viewer/scripts/weibo_ctl.py users add --uid 1669879400

# 移除指定博主 UID
python skills/weibo-viewer/scripts/weibo_ctl.py users remove --uid 1669879400
```

---

### 4. 爬取任务调度

当用户需要采集最新数据时，Agent 可通过命令直接拉起爬虫：

```bash
# 按照系统默认配置启动
python skills/weibo-viewer/scripts/weibo_ctl.py start

# 动态指定特定博主与起始日期
python skills/weibo-viewer/scripts/weibo_ctl.py start --users "1445403190,1669879400" --since-date 2026-10-20 --original-only

# 终止当前运行的爬虫进程
python skills/weibo-viewer/scripts/weibo_ctl.py stop

# 重载配置并重启服务
python skills/weibo-viewer/scripts/weibo_ctl.py restart
```

---

### 5. 查看实时日志与排错

排查防爬策略（如 403 / 414 / 登录过期）：

```bash
# 查看最新 30 行日志
python skills/weibo-viewer/scripts/weibo_ctl.py logs --lines 30
```

---

### 6. Cookie 状态诊断与免密导入

```bash
# 验证当前 Cookie 是否有效
python skills/weibo-viewer/scripts/weibo_ctl.py cookie

# 一键从本地 Chrome 浏览器提取新鲜 Cookie 并自动配置生效
python skills/weibo-viewer/scripts/weibo_ctl.py cookie --extract --browser chrome
```

---

## 🤖 在 Agent 框架中接入使用

### 1. Antigravity IDE / CLI
项目在初始化时已在 `.agents/skills/weibo-viewer` 建立了软链接。在 Antigravity 中，只要用户提问与“爬取微博”、“查看某博主发文”、“搜索微博热点”相关，Agent 会**自动激活**本 Skill 并利用 `weibo_ctl.py` 协助完成任务。

### 2. LangChain / AutoGen / 自定义大模型
可将 `skills/weibo-viewer/scripts/weibo_ctl.py` 包装为一个标准 Tool / Function Call：

```python
import subprocess
import json

def weibo_tool(action: str, **kwargs) -> str:
    """Weibo Crawler & Data Controller Tool for AI Agents"""
    cmd = ["python", "skills/weibo-viewer/scripts/weibo_ctl.py", action]
    for k, v in kwargs.items():
        if v is not None:
            cmd.extend([f"--{k.replace('_', '-')}", str(v)])
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout or result.stderr
```

---

## 📑 进阶参考

如需直接通过 RESTful API 进行网络交互，或进行深度 SQL 联表查询，请参阅：
- [RESTful API 规范文档](/api/endpoints)
- [Database Schema 与 SQL 参考文档](file:///Users/luyuchao/Documents/GitHub/weibo-crawler/skills/weibo-viewer/references/api_reference.md)
