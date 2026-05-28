# KindleVibe 使用指南

这份指南面向把 Kindle 当作常亮 vibe coding 状态屏的日常使用场景。

## 启动服务

在运行 Codex 或其他开发工具的电脑上启动 KindleVibe：

```bash
python3 app.py --host 0.0.0.0 --port 8080
```

启动后，终端会打印本机访问地址和局域网访问地址。Kindle 应该打开局域网地址，例如：

```text
http://192.168.1.20:8080
```

如果系统里的 Python 命令不是 `python3`，也可以用 Makefile 指定解释器：

```bash
make run PYTHON=/path/to/python3
```

## 后台运行

### Linux systemd

Linux 用户可以参考 `examples/systemd/kindlevibe.service` 创建 user service。

复制示例文件：

```bash
mkdir -p ~/.config/systemd/user
cp examples/systemd/kindlevibe.service ~/.config/systemd/user/kindlevibe.service
```

根据实际路径修改：

- `WorkingDirectory`
- `ExecStart` 中的 Python 路径、端口和监听地址

启用并启动：

```bash
systemctl --user daemon-reload
systemctl --user enable --now kindlevibe.service
systemctl --user status kindlevibe.service
```

查看日志：

```bash
journalctl --user -u kindlevibe.service -f
```

### macOS launchd

macOS 用户可以参考 `examples/launchd/com.kindlevibe.plist` 创建 launchd agent。

复制示例文件：

```bash
mkdir -p ~/Library/LaunchAgents
cp examples/launchd/com.kindlevibe.plist ~/Library/LaunchAgents/com.kindlevibe.plist
```

根据实际路径修改：

- `WorkingDirectory`
- `ProgramArguments` 里的 Python 路径、端口和监听地址
- 日志路径 `StandardOutPath` / `StandardErrorPath`

加载并启动：

```bash
launchctl unload ~/Library/LaunchAgents/com.kindlevibe.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.kindlevibe.plist
launchctl start com.kindlevibe
```

查看日志：

```bash
tail -f /tmp/kindlevibe.out.log /tmp/kindlevibe.err.log
```

## Kindle 端使用

1. 让 Kindle 和运行 KindleVibe 的电脑处在同一个局域网。
2. 打开 Kindle 浏览器。
3. 访问服务启动时显示的局域网地址。
4. 把 Kindle 放在桌面常亮显示。

主看板使用 HTML `meta refresh` 自动刷新，不依赖 JavaScript。响应也会发送 no-cache 头，减少 Kindle 显示旧页面的概率。

如果主页面渲染异常，可以访问纯文本兜底页：

```text
http://<电脑局域网 IP>:8080/status.txt
```

## 更新状态

用 CLI 写入当前状态：

```bash
python3 vibe_update.py \
  --state 编码中 \
  --from-git \
  --current-task "实现下一个功能" \
  --next-action "运行测试并提交 PR" \
  --participant @scnet_brain \
  --event "开始新一轮迭代。"
```

如果服务不在本机 8080 端口，可以设置环境变量：

```bash
export KINDLEVIBE_URL=http://192.168.1.20:8080/api/vibe
python3 vibe_update.py --heartbeat
```

如果配置了写入 token：

```bash
export KINDLEVIBE_TOKEN=your-token
python3 vibe_update.py --heartbeat
```

常用 Makefile 命令：

```bash
make status
make heartbeat
make health
make presets
make clear-blockers EVENT="阻塞项已解除。"
make clear-events EVENT="开始新一轮状态记录。"
make preset-coding EVENT="开始编码。"
make preset-review EVENT="本轮改动已交付。"
make preset-blocked BLOCKER="等待人工确认" EVENT="当前被阻塞。"
make preset-done EVENT="本轮任务已完成。"
```

## 自动化集成

自动化脚本可以先生成 JSON 状态包，再提交：

```bash
python3 vibe_update.py --payload-file status.json --event "自动化任务完成。"
```

`status.json` 可以参考仓库里的 `vibe_status.example.json`。

仓库也提供了常见状态包模板，可以直接复用：

```bash
python3 vibe_update.py --payload-file examples/payloads/coding.json --from-git
python3 vibe_update.py --payload-file examples/payloads/review.json --event "本轮改动已交付。"
python3 vibe_update.py --payload-file examples/payloads/blocked.json --blocker "等待人工确认"
python3 vibe_update.py --payload-file examples/payloads/done.json
```

同一组模板也可以用内置 preset 名称调用：

```bash
python3 vibe_update.py --list-presets
python3 vibe_update.py --preset coding --from-git
python3 vibe_update.py --preset review --event "本轮改动已交付。"
python3 vibe_update.py --preset blocked --blocker "等待人工确认"
python3 vibe_update.py --preset done
```

常用 preset 也有 Makefile 快捷命令：

```bash
make preset-coding EVENT="开始编码。"
make preset-review EVENT="本轮改动已交付。"
make preset-blocked BLOCKER="等待人工确认" EVENT="当前被阻塞。"
make preset-done EVENT="本轮任务已完成。"
```

阻塞项解决后，可以显式清空阻塞列表：

```bash
python3 vibe_update.py --clear-blockers --event "阻塞项已解除。"
```

如果最近事件已经太长，开始新一轮工作时可以清空历史并保留一条新事件：

```bash
python3 vibe_update.py --clear-events --event "开始新一轮状态记录。"
```

也可以用 Makefile 快捷命令完成同样操作：

```bash
make clear-blockers EVENT="阻塞项已解除。"
make clear-events EVENT="开始新一轮状态记录。"
```

健康检查：

```bash
python3 vibe_update.py --health
python3 vibe_update.py --health --json
```

或者直接访问：

```text
http://<电脑局域网 IP>:8080/api/health
```

远程脚本如果需要发现内置状态模板，可以读取：

```text
http://<电脑局域网 IP>:8080/api/presets
```

旧浏览器或终端可以用纯文本版本：

```text
http://<电脑局域网 IP>:8080/presets.txt
```

## 过期提示

看板会根据 `vibe.stale_after_seconds` 判断状态是否可能过期。默认值是 900 秒。

可以在浏览器的 `/settings` 页面修改这个值。建议：

- 高频协作：300 到 900 秒。
- 普通编码：900 到 1800 秒。
- 长任务观察：1800 秒以上。

只刷新心跳、不改变当前任务：

```bash
python3 vibe_update.py --heartbeat
```

## 常见问题

### Kindle 打不开页面

先确认电脑和 Kindle 在同一个局域网。然后在电脑上访问：

```text
http://localhost:8080/api/health
```

如果电脑本机可以访问，但 Kindle 不行，通常是防火墙、端口或网络隔离问题。

### 页面一直显示旧状态

先访问 `/status.txt` 看纯文本状态是否更新。如果纯文本也没有更新，说明状态没有写入成功。

如果纯文本已更新但主页面没有更新，尝试在 Kindle 浏览器里手动刷新页面，或者缩短 `refresh.auto_refresh_page_ms`。

### Codex 用量显示未知

Codex 用量依赖本机 Codex CLI 或本地会话文件。如果只想使用 vibe coding 看板，可以在 `/settings` 中关闭 Codex 监控。

### CLI 连接不上服务

确认 `KINDLEVIBE_URL` 或 `--url` 指向 `/api/vibe`：

```bash
python3 vibe_update.py --url http://127.0.0.1:8080/api/vibe --health
```

### 写入状态返回 401

如果 `config.json` 设置了 `security.api_token`，CLI 必须提供相同 token：

```bash
python3 vibe_update.py --token your-token --heartbeat
```

也可以通过环境变量提供：

```bash
export KINDLEVIBE_TOKEN=your-token
python3 vibe_update.py --heartbeat
```
