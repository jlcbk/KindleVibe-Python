# 架构说明

KindleVibe-Python 当前保持单进程、标准库优先的结构，目标是让旧 Kindle 浏览器、终端脚本和协作 agent 都能稳定读取同一份 vibe coding 状态。

## 主要模块

| 文件 | 职责 |
| --- | --- |
| `app.py` | HTTP 服务、页面渲染、设置页、Vibe 状态读写、Codex 用量读取、preset API。 |
| `vibe_update.py` | 命令行状态读写工具，封装 `/api/vibe`、`/api/health`、preset 和心跳操作。 |
| `config.json` | 服务端口、刷新间隔、Codex 来源、过期阈值、可选写入 token。 |
| `vibe_status.json` | 本地运行时状态文件，不提交到 Git。 |
| `examples/payloads/*.json` | 内置状态包模板，被 CLI preset 和服务端 preset API 复用。 |
| `Makefile` | 常用启动、检查、状态更新和 preset 快捷命令。 |
| `tests/` | 标准库 `unittest` 测试，覆盖状态归一化、CLI、preset 和安全行为。 |

## 数据流

```text
脚本 / agent / Makefile
        |
        v
vibe_update.py  ----POST /api/vibe---->  app.py
        |                                |
        |                                v
        |                          vibe_status.json
        |                                |
        v                                v
终端摘要 / JSON 输出              Kindle 主看板 / status.txt / health
```

核心状态只存一份：`vibe_status.json`。页面、纯文本端点、健康检查和 CLI 读取到的都是同一份状态。

## 服务端职责

`app.py` 负责以下几类输出：

| 类型 | 端点 |
| --- | --- |
| Kindle 页面 | `/`、`/settings` |
| 纯文本兜底 | `/status.txt`、`/presets.txt` |
| JSON API | `/api/vibe`、`/api/health`、`/api/presets`、`/api/usage`、`/api/config` |

所有面向 Kindle 或脚本的响应默认发送 no-cache 头，减少旧状态被缓存的概率。

## 状态更新规则

`POST /api/vibe` 使用局部更新：

- 字符串字段只在请求体提供该字段时更新。
- `blockers`、`participants` 会覆盖原列表。
- `events` 会覆盖事件列表，传入空列表可以清空事件历史。
- `event` 会追加一条事件。
- `heartbeat` 用于刷新 `updated_at`，表示当前状态仍然有效。

如果配置了 `security.api_token`，写入状态需要提供 `X-KindleVibe-Token` 请求头或 `token` 查询参数。

## CLI 职责

`vibe_update.py` 让脚本不需要手写 curl。它负责：

- 读取或写入当前状态。
- 从 Git 自动填充项目和分支。
- 从 JSON 状态包或内置 preset 构建 payload。
- 查询健康状态。
- 列出内置 preset。
- 读取 `KINDLEVIBE_URL` 和 `KINDLEVIBE_TOKEN`。

CLI 参数优先级高于状态包和 preset，因此可以先加载模板，再用命令行覆盖某个字段。

## preset 复用关系

```text
examples/payloads/*.json
        |
        +--> vibe_update.py --preset
        |
        +--> vibe_update.py --list-presets
        |
        +--> GET /api/presets
        |
        +--> GET /presets.txt
```

新增 preset 时，需要同时更新：

- `examples/payloads/<name>.json`
- `vibe_update.py` 的 `PRESET_NAMES`
- `app.py` 的 `PRESET_NAMES`
- README、使用指南或 API 文档中的示例
- `tests/test_example_payloads.py`

## 测试策略

本项目不引入额外测试依赖，使用 Python 标准库：

```bash
make ci
```

CI 检查包括：

- `python -m py_compile app.py vibe_update.py`
- `python -m unittest discover -s tests`

涉及 HTTP 端点的改动应至少补充函数级测试；影响真实路由时建议再做本地 smoke test。

## 设计边界

- 默认面向可信局域网，不直接承诺公网安全部署。
- 优先兼容旧 Kindle 浏览器，核心视图不依赖 JavaScript。
- 人类可见内容使用中文；稳定机器接口保留英文命名。
- 运行时状态、日志和个人 token 不进入 Git。
