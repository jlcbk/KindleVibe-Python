# 维护检查清单

这份清单用于发布前、部署前和排障时快速确认 InkDash 的关键路径没有遗漏。

## 每次改动前

- 确认改动目标只覆盖一个能力点，避免把功能、重构和文档大范围混在一起。
- 如果改动面向用户，确认所有人类可见内容使用中文。
- 如果改动机器接口，确认 API 路径、JSON 字段、命令行参数和配置键保持兼容。
- 如果涉及 Kindle 页面，确认旧浏览器仍有纯文本或无 JavaScript 兜底。

## 提交 PR 前

必须运行：

```bash
make ci
```

按改动类型补充检查：

| 改动类型 | 额外检查 |
| --- | --- |
| 页面或端点 | 本地启动服务并请求对应路径。 |
| CLI 参数 | `python3 vibe_update.py --help` 和目标参数 smoke test。 |
| Makefile target | `make help` 和 `make -n <target>`。 |
| 文档 | 检查 README、文档导航、CHANGELOG 是否同步。 |
| preset | 检查 `examples/payloads/`、`PRESET_NAMES`、测试和文档是否一致。 |
| token 或安全边界 | 检查 `SECURITY.md` 和 `/api/config` 脱敏行为。 |

## 部署前

- 确认 `config.json` 中的 `server.host` 和 `server.port` 符合局域网访问需求。
- 如果暴露给多设备写入，设置 `security.api_token`。
- 确认 `inkdash_status.json`、`vibe_status.json`、`logs/` 和真实 token 没有提交到 Git。
- 确认 Kindle 可以访问主页面 `/`。
- 用终端确认纯文本兜底：

```bash
curl http://<电脑局域网 IP>:8080/status.txt
curl http://<电脑局域网 IP>:8080/presets.txt
```

## 日常运行

查看状态：

```bash
make status
```

查看健康状态：

```bash
make health
```

刷新心跳：

```bash
make heartbeat
```

查看日志：

```bash
tail -n 80 logs/inkdash.log
```

## 排障

| 现象 | 检查 |
| --- | --- |
| Kindle 页面不更新 | 请求 `/status.txt`，确认 no-cache 响应和 `updated_at`。 |
| 状态显示可能过期 | 用 `make heartbeat` 刷新，或调整 `vibe.stale_after_seconds`。 |
| 写入返回 401 | 检查 `INKDASH_TOKEN`（兼容旧名 `KINDLEVIBE_TOKEN`）或 `X-InkDash-Token`（兼容旧名 `X-KindleVibe-Token`）。 |
| Codex 用量为空 | 检查 Codex CLI 登录状态和 `logs/inkdash.log`。 |
| preset 不一致 | 运行 `make presets`，再检查 `examples/payloads/` 和测试。 |

## 新增端点时

- 在 `app.py` 中设置合适的 `Content-Type`。
- 对 Kindle 或脚本可能访问的端点发送 no-cache 头。
- 如果是 JSON API，更新 [API 参考](api.md)。
- 如果有旧浏览器需求，考虑补一个 `.txt` 纯文本端点。
- 增加测试或本地 HTTP smoke。

## 新增 preset 时

- 新增 `examples/payloads/<name>.json`。
- 更新 `vibe_update.py` 和 `app.py` 中的 `PRESET_NAMES`。
- 更新 README、使用指南、自动化接入示例或 API 文档中的示例。
- 运行：

```bash
make ci
python3 vibe_update.py --list-presets
make presets
```
