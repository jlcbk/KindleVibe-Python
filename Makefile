.PHONY: run stop test status heartbeat health help

# Default port
PORT ?= 8080
URL ?= http://localhost:$(PORT)/api/vibe
PYTHON ?= python3

help:
	@echo "KindleVibe-Python - Kindle 友好的 vibe coding 状态面板"
	@echo ""
	@echo "用法："
	@echo "  make run             在 $(PORT) 端口启动服务"
	@echo "  make run PORT=9090   在 9090 端口启动服务"
	@echo "  make stop            停止服务"
	@echo "  make test            测试 Codex CLI 连接"
	@echo "  make status          读取当前 Vibe 状态"
	@echo "  make heartbeat       刷新当前 Vibe 状态心跳"
	@echo "  make health          查看服务健康状态"
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

status:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py

heartbeat:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --heartbeat

health:
	@KINDLEVIBE_URL=$(URL) $(PYTHON) vibe_update.py --health
