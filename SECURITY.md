# 安全说明

InkDash（墨板）设计为本机或可信局域网内使用的状态面板，不建议直接暴露到公网。

## 支持范围

当前安全说明适用于 `main` 分支的最新代码。

## 部署边界

建议部署方式：

- 只监听本机或可信局域网。
- 不要把服务端口直接映射到公网。
- 如果同一局域网内有不可信设备，建议启用写入 token。

默认配置下，读取看板和写入状态都面向可信局域网使用。启用 `security.api_token` 后，`POST /api/status` 需要 token；旧 `POST /api/vibe` 兼容别名同样需要 token。读取端点仍保持开放，便于 Kindle 显示和监控脚本读取。

读取端点（`GET /api/vibe`、`GET /api/status`、`GET /api/usage`、`GET /api/config`、`GET /status.txt`）默认不加验证。如果部署环境中存在不可信设备，这些端点会暴露用量、配置和状态信息。建议通过局域网防火墙限制访问，或在下一版本中使用可选的 read token。

## 写入 Token

在 `config.json` 中设置：

```json
{
  "security": {
    "api_token": "your-token"
  }
}
```

CLI 写入时提供 token：

```bash
export INKDASH_TOKEN=your-token
python3 vibe_update.py --heartbeat
```

也可以显式传入：

```bash
python3 vibe_update.py --token your-token --event "更新状态。"
```

`GET /api/config` 会对已配置的 token 脱敏显示为 `<configured>`。

## 不要提交的内容

不要提交：

- 本地 `config.json` 中的真实 token。
- `inkdash_status.json` 或 `vibe_status.json` 运行时状态文件。
- `logs/` 下的运行日志。

仓库已经默认忽略 `inkdash_status.json`、`vibe_status.json` 和日志目录。

## 报告问题

如果发现安全问题，请不要在公开 issue 中贴 token、日志、内网地址或其他敏感信息。

推荐报告内容：

- 影响范围。
- 复现步骤。
- 期望行为和实际行为。
- 是否需要 token 或特定配置才能复现。
