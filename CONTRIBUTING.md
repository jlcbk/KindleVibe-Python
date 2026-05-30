# 贡献指南

这份指南用于保持 InkDash 的迭代节奏稳定：先做小而可验证的改动，再用清晰的 PR 交接给协作者评审和合并。

## 项目方向

- 面向 Kindle 浏览器和电子墨水屏，优先保证高对比、低动态、可自动刷新。
- 主要场景是 vibe coding 状态展示：当前目标、任务、下一步、协作者、阻塞项、最近事件和健康状态。
- 默认只依赖 Python 标准库。新增运行时依赖前，需要说明它解决了什么不可替代的问题。
- 人类可见内容使用中文，包括 README、文档、页面文字、Makefile 提示和错误说明。
- 稳定的机器接口可以保留英文，例如命令行参数、JSON 字段、API 路径、Python 标识符和配置键。

## 本地开发

建议使用 Python 3.11 或 3.12。启动服务：

```bash
python3 app.py --host 0.0.0.0 --port 8080
```

常用状态操作：

```bash
python3 vibe_update.py --heartbeat
python3 vibe_update.py --health
make status
make heartbeat
make health
```

如果本机默认 `python3` 版本不合适，可以覆盖 Makefile 变量：

```bash
make ci PYTHON=/path/to/python3
```

## 提交前检查

每次交接 PR 前至少运行：

```bash
make ci
```

等价检查包括：

```bash
python3 -m py_compile app.py status_model.py vibe_update.py
python3 -m unittest discover -s tests
```

涉及页面、API 或 CLI 的改动，应补充对应的单元测试或 smoke test。涉及文档的改动，应确认 README、使用指南、安全说明和变更记录之间没有互相矛盾。

## 兼容性原则

- 主看板刷新应继续兼容旧 Kindle 浏览器，优先使用 HTML/CSS 能完成的方案。
- 不依赖 JavaScript 才能完成的核心状态展示，应同时提供 `/status.txt` 或其他低能力浏览器可用的兜底路径。
- 页面布局应避免复杂动画、过小字号和低对比颜色。
- API 默认用于可信局域网。如果暴露到不可信网络，需要先补齐反向代理、HTTPS 和访问控制说明。

## 运行时文件

以下内容属于本地运行状态，不应提交到仓库：

- `inkdash_status.json`
- `vibe_status.json`
- `logs/`
- `__pycache__/`
- 本地 token、个人 IP、私有部署地址和真实凭据

示例配置和示例状态可以提交，但不能包含真实 token。

## PR 说明

PR 描述建议包含：

- 这次改动解决的问题。
- 主要改动点。
- 已运行的验证命令和结果。
- 是否影响 Kindle 老浏览器、`/status.txt`、CLI、Makefile 或 token 鉴权。
- 是否需要用户修改配置或部署方式。

推荐保持 PR 小而完整。一次改动最好只围绕一个能力点，避免把功能、重构和文档大范围混在一起。
