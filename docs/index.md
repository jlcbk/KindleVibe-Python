# 文档导航

这里汇总 KindleVibe-Python 的主要中文文档。第一次使用时建议按顺序阅读；只接入脚本或维护项目时，可以直接跳到对应章节。

## 使用和部署

| 文档 | 适合场景 |
| --- | --- |
| [Kindle 使用指南](kindle-usage.md) | 启动服务、在 Kindle 上访问、设置刷新、排障。 |
| [API 参考](api.md) | 查询页面端点、纯文本端点、JSON API、写入鉴权和状态字段。 |
| [自动化接入示例](automation-recipes.md) | 用脚本或 agent 更新状态、切换 preset、刷新心跳、记录阻塞。 |
| [安全说明](../SECURITY.md) | 理解可信局域网边界、写入 token、配置脱敏和安全报告方式。 |

## 后台运行示例

| 文件 | 适合场景 |
| --- | --- |
| [systemd user service](../examples/systemd/kindlevibe.service) | Linux 用户级后台服务。 |
| [macOS launchd plist](../examples/launchd/com.kindlevibe.plist) | macOS 用户级后台服务。 |

## 开发和维护

| 文档 | 适合场景 |
| --- | --- |
| [架构说明](architecture.md) | 理解服务端、CLI、状态文件、preset、测试之间的关系。 |
| [贡献指南](../CONTRIBUTING.md) | 本地开发、兼容性原则、PR 检查清单。 |
| [变更记录](../CHANGELOG.md) | 查看当前功能集合和验证入口。 |
| [README](../README.md) | 项目入口、快速开始、主要命令。 |

## 常用入口

本地开发检查：

```bash
make ci
```

查看当前状态：

```bash
make status
```

查看服务健康状态：

```bash
make health
```

查看内置状态模板：

```bash
make presets
```

切换到常见 vibe coding 状态：

```bash
make preset-coding EVENT="开始编码。"
make preset-review EVENT="等待评审。"
make preset-blocked BLOCKER="等待输入" EVENT="被阻塞。"
make preset-done EVENT="完成。"
```
