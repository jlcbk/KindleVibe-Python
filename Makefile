.PHONY: run stop test ci status heartbeat health presets clear-blockers clear-participants clear-events preset-coding preset-review preset-blocked preset-done help

# Default port
PORT ?= 8080
URL ?= http://localhost:$(PORT)/api/vibe
PYTHON ?= python3
EVENT ?=
BLOCKER ?=
EVENT_ARG = $(if $(strip $(EVENT)),--event "$(EVENT)",)
BLOCKER_ARG = $(if $(strip $(BLOCKER)),--blocker "$(BLOCKER)",)

help:
	@echo "KindleVibe-Python - Kindle 友好的 vibe coding 状态面板"
	@echo ""
	@echo "用法："
	@echo "  make run             在 $(PORT) 端口启动服务"
	@echo "  make run PORT=9090   在 9090 端口启动服务"
	@echo "  make stop            停止服务"
	@echo "  make test            测试 Codex CLI 连接"
	@echo "  make ci              运行本地 CI 检查"
	@echo "  make status          读取当前 Vibe 状态"
	@echo "  make heartbeat       刷新当前 Vibe 状态心跳"
	@echo "  make health          查看服务健康状态"
	@echo "  make presets         查看内置状态 preset"
	@echo "  make clear-blockers  清空阻塞项，可加 EVENT=\"说明\""
	@echo "  make clear-events    清空最近事件，可加 EVENT=\"说明\""
	@echo "  make preset-coding   切换到编码中 preset，并自动读取 Git 上下文"
	@echo "  make preset-review   切换到等待评审 preset，可加 EVENT=\"说明\""
	@echo "  make preset-blocked  切换到被阻塞 preset，可加 BLOCKER=\"原因\""
	@echo "  make preset-done     切换到已完成 preset，可加 EVENT=\"说明\""
	@echo "  make run PYTHON=/path/to/python3  指定 Python 解释器"
	@echo ""

run:
	@echo "正在 $(PORT) 端口启动 KindleVibe-Python..."
	$(PYTHON) app.py --port $(PORT)

stop:
	@echo "正在停止 KindleVibe-Python..."
	@if lsof -ti tcp:$(PORT) >/dev/null 2>&1; then \
		kill $$(lsof -ti tcp:$(PORT)); \
		echo "已停止。"; \
	else \
		echo "当前没有运行。"; \
	fi

test:
	@echo "正在测试 Codex CLI 连接..."
	@codex /status 2>&1 || echo "错误：codex /status 执行失败"

ci:
	$(PYTHON) -m py_compile app.py vibe_update.py
	$(PYTHON) -m unittest discover -s tests

status:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py

heartbeat:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --heartbeat

health:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --health

presets:
	@$(PYTHON) vibe_update.py --list-presets

clear-blockers:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --clear-blockers $(EVENT_ARG)

clear-participants:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --clear-participants $(EVENT_ARG)

clear-events:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --clear-events $(EVENT_ARG)

preset-coding:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --preset coding --from-git $(EVENT_ARG)

preset-review:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --preset review $(EVENT_ARG)

preset-blocked:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --preset blocked $(BLOCKER_ARG) $(EVENT_ARG)

preset-done:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --preset done $(EVENT_ARG)
