# KindleVibe-Python

KindleVibe-Python 是一个面向 Kindle 浏览器的常亮状态面板，用来显示 vibe coding 过程中的关键信息：当前目标、项目/分支、正在处理的任务、下一步、阻塞项、最近事件，以及 Codex 用量。

这个版本只依赖 Python 标准库，适合在本机或局域网内运行，然后用 Kindle 打开页面作为低功耗状态屏。

## 功能

- **Kindle 友好**：黑白高对比、大字号、低动态效果，适合电子墨水屏。
- **Vibe Coding 看板**：展示当前目标、任务、下一步、协作者、阻塞项和最近事件。
- **状态写入 API**：任意 agent、脚本或自动化流程都可以通过 `POST /api/vibe` 更新看板。
- **纯文本兜底页**：`/status.txt` 提供不依赖 CSS/JS 的状态摘要，适合旧 Kindle 浏览器、终端和监控脚本。
- **心跳/过期提示**：当状态长时间没有更新时，页面和纯文本端点会提示“可能过期”。
- **Codex 用量监控**：优先通过 Codex CLI RPC 读取用量，失败后回退到本地会话文件。
- **自动刷新**：主看板使用 HTML `meta refresh` 按配置周期自动刷新，不依赖 JavaScript。
- **禁用缓存**：主页面、纯文本页和 API 默认发送 no-cache 响应头，减少 Kindle 显示旧状态的概率。
- **浏览器设置页**：可以在 `/settings` 中调整端口、刷新间隔、Codex 来源和显示内容。

## 环境要求

- Python 3.7 或更高版本。
- 如需 Codex 用量：本机已安装并登录 Codex CLI。

## 快速开始

```bash
python3 app.py
```

指定端口和监听地址：

```bash
python3 app.py --host 0.0.0.0 --port 9090
```

启动后，在 Kindle 浏览器打开：

```text
http://<你的局域网 IP>:8080
```

更完整的 Kindle 使用、CLI 自动化和排障说明见 [docs/kindle-usage.md](docs/kindle-usage.md)。

## 更新 Vibe Coding 状态

看板状态保存在本地 `vibe_status.json`，该文件属于运行时状态，不提交到 Git。可以参考 `vibe_status.example.json` 的结构。

最小更新示例：

```bash
curl -X POST http://localhost:8080/api/vibe \
  -H 'Content-Type: application/json' \
  -d '{
    "state": "编码中",
    "project": "KindleVibe-Python",
    "branch": "feature/vibe-board",
    "objective": "把 Kindle 变成 vibe coding 常亮状态屏",
    "current_task": "实现通用状态写入接口",
    "next_action": "运行测试并交给 GitHub 协作 agent 发 PR",
    "participants": ["@scnet_brain", "@opencode"],
    "blockers": [],
    "event": "完成第一版状态面板。"
  }'
```

读取当前状态：

```bash
curl http://localhost:8080/api/vibe
```

也可以使用随项目提供的标准库 CLI 工具，避免每次手写 curl：

```bash
python3 vibe_update.py \
  --state 编码中 \
  --project KindleVibe-Python \
  --branch feature/vibe-board \
  --objective "把 Kindle 变成 vibe coding 常亮状态屏" \
  --current-task "补充 CLI 状态写入工具" \
  --next-action "运行测试并交给 GitHub 协作 agent 发 PR" \
  --participant @scnet_brain \
  --participant @opencode \
  --event "CLI 已经能写入状态。"
```

如果 KindleVibe 不在本机 8080 端口，可以用环境变量设置默认 API 地址：

```bash
export KINDLEVIBE_URL=http://192.168.1.20:8080/api/vibe
python3 vibe_update.py --heartbeat
```

如果在 `config.json` 中配置了 `security.api_token`，写入状态时需要提供同一个 token：

```bash
export KINDLEVIBE_TOKEN=your-token
python3 vibe_update.py --heartbeat
```

只读取并输出中文摘要：

```bash
python3 vibe_update.py
```

输出完整 JSON：

```bash
python3 vibe_update.py --json
```

查看服务健康状态：

```bash
python3 vibe_update.py --health
```

常用操作也可以通过 Makefile 调用：

```bash
make status
make heartbeat
make health
```

如果系统里的 Python 命令不是 `python3`，可以覆盖 Makefile 变量：

```bash
make health PYTHON=/path/to/python3
```

只刷新心跳，不改变当前任务内容：

```bash
python3 vibe_update.py --heartbeat
```

从当前 Git 仓库自动填充项目名和分支：

```bash
python3 vibe_update.py --from-git --state 编码中 --event "继续推进当前仓库。"
```

在脚本中指定要读取的 Git 工作目录：

```bash
python3 vibe_update.py --from-git --cwd /path/to/repo --heartbeat
```

从 JSON 状态包读取，再用命令行参数覆盖其中部分字段：

```bash
python3 vibe_update.py --payload-file vibe_status.example.json --state 等待评审
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `title` | 看板标题 |
| `state` | 当前状态，例如 `编码中`、`等待评审`、`被阻塞` |
| `project` | 当前项目 |
| `branch` | 当前分支或工作区 |
| `objective` | 当前大目标 |
| `current_task` | 正在处理的具体任务 |
| `next_action` | 下一步行动 |
| `blockers` | 阻塞项列表 |
| `participants` | 参与者列表 |
| `event` | 追加一条最近事件 |
| `events` | 覆盖最近事件列表 |

## 配置

`config.json` 中可以配置服务端口、刷新间隔、Codex 数据来源和显示选项。

```json
{
  "server": {
    "port": 8080,
    "host": "0.0.0.0"
  },
  "refresh": {
    "interval_seconds": 300,
    "auto_refresh_page_ms": 300000
  },
  "codex": {
    "enabled": true,
    "source": "auto",
    "session_file_limit": 10
  },
  "vibe": {
    "stale_after_seconds": 900
  },
  "security": {
    "api_token": ""
  },
  "display": {
    "show_vibe_board": true,
    "show_credits": false,
    "show_plan_type": true,
    "show_data_source": true,
    "show_last_updated": true
  }
}
```

## API

- `GET /`：Kindle 主看板。
- `GET /status.txt`：纯文本状态摘要。
- `GET /settings`：设置页。
- `GET /api/vibe`：读取 vibe coding 状态。
- `POST /api/vibe`：更新 vibe coding 状态。
- `GET /api/health`：健康检查，返回服务状态、vibe 状态是否过期、Codex 数据是否报错。
- `GET /api/usage`：读取 Codex 用量。
- `GET /api/config`：读取当前配置。

## 运行日志

日志写入 `logs/kindlevibe.log`。如果 Codex 用量没有更新，先查看日志，再确认 Codex CLI 是否可用。

## 许可证

WTFPL（与原 KindleVibe 保持一致）。
