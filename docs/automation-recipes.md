# 自动化接入示例

这份文档给协作开发过程中的脚本和 agent 提供可直接套用的状态更新配方。所有示例都只依赖仓库内置的 `vibe_update.py` 和 Makefile。

## 基础环境变量

如果 InkDash 运行在另一台电脑上，先设置 API 地址：

```bash
export INKDASH_URL=http://192.168.1.20:8080/api/status
```

如果服务端配置了写入 token：

```bash
export INKDASH_TOKEN=your-token
```

## 开始一轮编码

在当前 Git 仓库里运行：

```bash
python3 vibe_update.py --preset coding --from-git --event "开始新一轮编码。"
```

Makefile 快捷命令：

```bash
make preset-coding EVENT="开始新一轮编码。"
```

效果：

- 状态切换为 `编码中`。
- 自动读取当前项目名和 Git 分支。
- 在最近事件里记录这轮编码开始。

## 进入评审

本地检查通过并交给协作者评审时：

```bash
python3 vibe_update.py \
  --preset review \
  --event "本地检查通过，等待 PR 评审。"
```

Makefile 快捷命令：

```bash
make preset-review EVENT="本地检查通过，等待 PR 评审。"
```

## 记录阻塞

遇到需要人类决策、外部资源或 CI 问题时：

```bash
python3 vibe_update.py \
  --preset blocked \
  --blocker "等待人类确认部署目标" \
  --event "当前任务被外部决策阻塞。"
```

Makefile 快捷命令：

```bash
make preset-blocked BLOCKER="等待人类确认部署目标" EVENT="当前任务被外部决策阻塞。"
```

阻塞解除后：

```bash
make clear-blockers EVENT="阻塞项已解除，恢复推进。"
```

## 标记完成

当前任务交付、合并或无需继续操作时：

```bash
python3 vibe_update.py --preset done --event "本轮任务已完成。"
```

Makefile 快捷命令：

```bash
make preset-done EVENT="本轮任务已完成。"
```

## 保持心跳

长时间运行的脚本可以定期刷新心跳，避免 Kindle 看板误判状态过期：

```bash
while true; do
  python3 vibe_update.py --heartbeat
  sleep 300
done
```

如果使用 Makefile：

```bash
make heartbeat
```

## 清理事件历史

开始一个新的大目标时，可以清空旧事件并保留一条新记录：

```bash
python3 vibe_update.py --clear-events --event "开始新的目标。"
```

Makefile 快捷命令：

```bash
make clear-events EVENT="开始新的目标。"
```

## 读取当前状态和健康状态

```bash
python3 vibe_update.py
python3 vibe_update.py --health
python3 vibe_update.py --wait-health --wait-timeout 30
python3 vibe_update.py --list-presets
```

Makefile 快捷命令：

```bash
make status
make health
make presets
```

## 直接调用 HTTP API

当脚本不方便调用 Python CLI 时，可以直接写入 API：

```bash
curl -X POST "$INKDASH_URL" \
  -H 'Content-Type: application/json' \
  -H "X-InkDash-Token: $INKDASH_TOKEN" \
  -d '{
    "state": "编码中",
    "current_task": "执行自动化任务",
    "next_action": "等待任务完成后更新状态",
    "event": "自动化任务启动。"
  }'
```

如果没有启用 token，可以省略 `X-InkDash-Token` 请求头（兼容旧名 `X-KindleVibe-Token`）。

## 最小状态机建议

自动化脚本可以按下面的状态顺序更新 InkDash：

| 阶段 | 推荐命令 |
| --- | --- |
| 开始实现 | `make preset-coding EVENT="开始实现。"` |
| 本地检查通过 | `make preset-review EVENT="等待评审。"` |
| 等待外部输入 | `make preset-blocked BLOCKER="等待输入" EVENT="被阻塞。"` |
| 阻塞解除 | `make clear-blockers EVENT="阻塞解除。"` |
| 工作完成 | `make preset-done EVENT="完成。"` |

这个状态机不要求脚本完全接管流程。只要在关键节点更新一次，Kindle 屏幕就能持续显示当前协作状态。
