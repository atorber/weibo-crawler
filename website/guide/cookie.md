# Cookie 指南与运维监控

Cookie 是爬虫访问微博深层数据、突破反爬限频与维持长效爬取的关键。

## 免登录 vs 添加 Cookie 区别

| 特性 / 维度 | 未添加 Cookie (匿名模式) | 已配置有效 Cookie (登录模式) |
| --- | --- | --- |
| 博主微博数 $\le 2000$ 条 | ✅ 可获取完整用户信息和绝大部分微博 | ✅ 100% 完整抓取 |
| 博主微博数 $> 2000$ 条 | ⚠️ 仅能抓取最近约 2000 条左右的公开微博 | ✅ 可回溯抓取历史全部微博 |
| 转发微博与转发链条 | ❌ 无法抓取转发详情 | ✅ 完整支持抓取 |
| 关键词搜索 (`query_list`) | ❌ 无法使用搜索接口 | ✅ 完整支持关键词过滤 |
| 抓取频次与限流防护 | 易触发反爬人机验证 | 稳定性明显增强 |

---

## 如何获取 Cookie

1. 打开 Chrome、Edge 或 Safari 浏览器，访问移动版网页：[https://m.weibo.cn](https://m.weibo.cn) 或 [https://weibo.cn](https://weibo.cn) 并完成扫码登录。
2. 按 `F12` 或右键点击“检查”，打开浏览器的 **开发者工具 (DevTools)**。
3. 切换到 **Network (网络)** 标签页。
4. 刷新页面（按 `F5`），点击任意以 `m.weibo.cn` 或 `weibo.cn` 开头的请求条目。
5. 在右侧 **Headers (标头)** -> **Request Headers (请求标头)** 中，找到 `Cookie:` 字段。
6. 复制该字段的完整值，粘贴到 `config.json` 的 `"cookie"` 配置项中：

```json
{
  "cookie": "SUB=_2A25xxxx...; SUBP=0033...; _T_WM=123456;"
}
```

---

## Cookie 有效性自动检测与通知

微博 Cookie 可能因登录过期或账号风控而失效。爬虫内置了自动化检测机制与告警推送。

### 1. 开启 Cookie 检测

在项目根目录的 `const.py` 中：

```python
# 开启检测
'CHECK': True,

# 填入你用小号发布的仅自己可见的微博正文测试词
'HIDDEN_WEIBO': '爬虫探针测试微博',
```

并在 `config.json` 的 `user_id_list` 第一个位置配置发出该探针微博的小号 ID。爬虫启动时会尝试检索这条隐私微博，若能成功读取，则证明 Cookie 认证有效，否则程序提前预警停止，避免无效请求。

### 2. 结合 PushDeer 实现手机即时告警

本项目已集成轻量开源通知组件 [PushDeer](https://github.com/easychen/pushdeer)：

1. 手机端安装 PushDeer App 或关注其微信公众号，生成你专有的 `PushKey`。
2. 编辑 `const.py`：
   ```python
   'NOTIFY': True,
   'PUSH_KEY': 'PDU1234Txxxx...',
   ```
3. 当爬虫检测到 Cookie 失效时，将第一时间向你的手机推送报警提醒，确保不遗漏关键数据。
