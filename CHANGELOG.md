# 变更记录

本项目使用人工维护的变更记录，后续发布版本时可以从这里整理 release notes。

## 未发布

### 新增

- Kindle 友好的 Vibe Coding 主看板，展示目标、项目、分支、当前任务、下一步、参与者、阻塞项和最近事件。
- `GET /api/vibe` / `POST /api/vibe` 状态读取与写入接口。
- `vibe_update.py` CLI，支持状态写入、心跳、健康检查、JSON 输出、从 Git 自动填充上下文、从 JSON 状态包读取、环境变量配置 URL/token。
- `GET /status.txt` 纯文本兜底页。
- `GET /presets.txt` 纯文本内置状态包列表。
- `GET /api/health` 健康检查接口。
- `GET /api/presets` 返回内置状态包模板摘要和 payload。
- 心跳/过期提示，并支持在设置页调整过期阈值。
- 可选 `security.api_token` 写入鉴权。
- `GET /api/config` 对已配置 token 脱敏。
- `vibe_update.py` 支持显式清空阻塞项、参与者和最近事件。
- `examples/payloads/` 提供编码中、等待评审、被阻塞和已完成状态包模板。
- `vibe_update.py --preset` 可以直接读取内置状态包模板。
- `vibe_update.py --list-presets` 可以列出内置状态包模板摘要。
- 主页面使用 `meta refresh` 自动刷新，不依赖 JavaScript。
- 主页面、设置页、纯文本页和 API 统一 no-cache 响应头。
- Makefile 快捷命令：`make status`、`make heartbeat`、`make health`、`make presets`、`make clear-blockers`、`make clear-events`、`make preset-coding`、`make preset-review`、`make preset-blocked`、`make preset-done`、`make ci`。
- GitHub Actions CI，自动运行 py_compile 和 unittest。
- 中文使用指南、API 参考、安全说明、systemd user service 示例、macOS launchd 示例。
- 中文贡献指南，固定本地开发、验证、兼容性和 PR 交接要求。

### 变更

- README、主页面、设置页和 Makefile 的人类可见内容改为中文。
- `python3 app.py --port ...` 和 `--host ...` 现在会覆盖配置文件中的监听设置。

### 验证

- 当前本地检查入口：`make ci`。
- 当前自动化检查：GitHub Actions 在 PR 和 main push 上运行 Python 3.11 / 3.12 测试矩阵。
