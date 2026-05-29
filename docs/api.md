# API 参考

本文档面向脚本、agent 和轻量监控工具，说明 KindleVibe-Python 当前提供的页面、JSON API 和纯文本端点。

默认服务地址示例：

```text
http://localhost:8080
```

局域网访问时，把 `localhost` 换成运行服务的电脑 IP。

## 页面和纯文本端点

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/` | Kindle 主看板，展示 Vibe Coding 状态和 Codex 用量。 |
| `GET` | `/settings` | 浏览器设置页。 |
| `GET` | `/status.txt` | 纯文本状态摘要，适合旧 Kindle 浏览器、终端和监控脚本。 |
| `GET` | `/presets.txt` | 纯文本内置状态包列表。 |

示例：

```bash
curl http://localhost:8080/status.txt
curl http://localhost:8080/presets.txt
```

## JSON API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/vibe` | 读取当前 Vibe Coding 状态。 |
| `POST` | `/api/vibe` | 更新当前 Vibe Coding 状态。 |
| `GET` | `/api/health` | 读取服务健康状态、Vibe 心跳状态和 Codex 数据状态。 |
| `GET` | `/api/presets` | 读取内置状态包模板摘要和原始 payload。 |
| `GET` | `/api/usage` | 读取 Codex 用量数据。 |
| `GET` | `/api/config` | 读取当前配置；如果配置了写入 token，会脱敏显示。 |

## 读取状态

```bash
curl http://localhost:8080/api/vibe
```

响应是当前状态对象，常用字段包括：

| 字段 | 说明 |
| --- | --- |
| `state` | 当前状态，例如 `编码中`、`等待评审`、`被阻塞`。 |
| `project` | 当前项目。 |
| `branch` | 当前分支或工作区。 |
| `objective` | 当前大目标。 |
| `current_task` | 正在处理的任务。 |
| `next_action` | 下一步行动。 |
| `participants` | 参与者列表。 |
| `blockers` | 阻塞项列表。 |
| `events` | 最近事件列表。 |
| `updated_at` | 状态更新时间。 |

## 更新状态

```bash
curl -X POST http://localhost:8080/api/vibe \
  -H 'Content-Type: application/json' \
  -d '{
    "state": "编码中",
    "project": "KindleVibe-Python",
    "branch": "main",
    "current_task": "补充 API 文档",
    "next_action": "运行测试并交付 PR",
    "event": "API 文档更新完成。"
  }'
```

`POST /api/vibe` 是局部更新：只修改请求体中出现的字段。几个特殊字段：

| 字段 | 行为 |
| --- | --- |
| `event` | 追加一条最近事件。 |
| `events` | 覆盖最近事件列表；传入 `[]` 可以清空事件历史。 |
| `blockers` | 覆盖阻塞项列表；传入 `[]` 可以清空阻塞项。 |
| `participants` | 覆盖参与者列表；传入 `[]` 可以清空参与者。 |
| `heartbeat` | 设为 `true` 时只刷新更新时间，用来表示当前状态仍然有效。 |

## 写入鉴权

默认情况下，`POST /api/vibe` 只适合可信局域网使用。如果在 `config.json` 中设置了：

```json
{
  "security": {
    "api_token": "your-token"
  }
}
```

写入时需要提供 token：

```bash
curl -X POST http://localhost:8080/api/vibe \
  -H 'Content-Type: application/json' \
  -H 'X-KindleVibe-Token: your-token' \
  -d '{"heartbeat": true}'
```

也可以使用查询参数：

```bash
curl -X POST 'http://localhost:8080/api/vibe?token=your-token' \
  -H 'Content-Type: application/json' \
  -d '{"heartbeat": true}'
```

## 健康检查

```bash
curl http://localhost:8080/api/health
```

响应包含：

| 字段 | 说明 |
| --- | --- |
| `status` | 服务状态，目前正常时为 `ok`。 |
| `checked_at` | 检查时间。 |
| `vibe.stale` | 当前 Vibe 状态是否可能过期。 |
| `vibe.stale_after_seconds` | 状态过期阈值。 |
| `codex.source` | Codex 用量数据来源。 |
| `codex.error` | Codex 数据错误信息。 |

## Codex 用量

```bash
curl http://localhost:8080/api/usage
```

常用字段：

| 字段 | 说明 |
| --- | --- |
| `five_hour_percent_left` | 5 小时额度剩余百分比。 |
| `five_hour_reset` | 5 小时额度重置时间。 |
| `weekly_percent_left` | 周额度剩余百分比。 |
| `weekly_reset` | 周额度重置时间。 |
| `source` | 额度数据来源，通常是 `cli-rpc` 或 `session`。 |
| `local_token_usage.windows.24h.total_tokens` | 本机近 24 小时消耗 Token 数。 |
| `local_token_usage.windows.24h.cache_hit_percent` | 本机近 24 小时缓存命中率。 |
| `local_token_usage.windows.7d.total_tokens` | 本机近 7 天消耗 Token 数。 |
| `local_token_usage.windows.7d.cache_hit_percent` | 本机近 7 天缓存命中率。 |

`local_token_usage` 来自当前电脑的 Codex 会话文件，只代表本机消耗；额度百分比优先来自 Codex 服务器侧 RPC，适合观察同一账号的整体余量。

## 状态包模板

读取 JSON 版本：

```bash
curl http://localhost:8080/api/presets
```

读取纯文本版本：

```bash
curl http://localhost:8080/presets.txt
```

本地 CLI 也可以查看和使用同一组模板：

```bash
python3 vibe_update.py --list-presets
python3 vibe_update.py --preset coding --from-git
python3 vibe_update.py --preset blocked --blocker "等待人工确认"
```

## 缓存行为

主看板、设置页、纯文本端点和 JSON API 默认发送 no-cache 响应头，减少 Kindle 或代理缓存旧状态的概率。
