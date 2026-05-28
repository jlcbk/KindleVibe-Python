import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402


class VibeStatusTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.original_status_file = app.STATUS_FILE
        app.STATUS_FILE = Path(self.tmpdir.name) / "vibe_status.json"

    def tearDown(self):
        app.STATUS_FILE = self.original_status_file
        self.tmpdir.cleanup()

    def test_update_vibe_status_persists_patch_and_event(self):
        status = app.update_vibe_status({
            "state": "编码中",
            "project": "KindleVibe-Python",
            "branch": "feature/vibe-board",
            "objective": "显示 vibe coding 状态",
            "participants": ["@scnet_brain", "@opencode"],
            "blockers": [],
            "event": "完成状态写入接口。"
        })

        self.assertEqual(status["state"], "编码中")
        self.assertEqual(status["project"], "KindleVibe-Python")
        self.assertEqual(status["participants"], ["@scnet_brain", "@opencode"])
        self.assertEqual(status["events"][-1]["text"], "完成状态写入接口。")

        with open(app.STATUS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["branch"], "feature/vibe-board")

    def test_normalize_limits_recent_events(self):
        raw = {
            "events": [
                {"time": f"t{i}", "text": f"事件 {i}"}
                for i in range(app.MAX_EVENT_ITEMS + 3)
            ]
        }

        status = app.normalize_vibe_status(raw)

        self.assertEqual(len(status["events"]), app.MAX_EVENT_ITEMS)
        self.assertEqual(status["events"][0]["text"], "事件 3")

    def test_generate_status_text_contains_vibe_and_usage_summary(self):
        usage = app.CodexUsage()
        usage.five_hour_percent_left = 72
        usage.weekly_percent_left = 88
        usage.source = "session"
        usage.last_updated = "2026-05-29 01:30:00"
        status = app.normalize_vibe_status({
            "state": "测试中",
            "project": "KindleVibe-Python",
            "branch": "status-text",
            "objective": "提供纯文本兜底视图",
            "events": [{"time": "01:30", "text": "生成 status.txt"}],
        })

        text = app.generate_status_text(usage, status)

        self.assertIn("状态：测试中", text)
        self.assertIn("目标：提供纯文本兜底视图", text)
        self.assertIn("分支：status-text", text)
        self.assertIn("5 小时额度剩余：72%", text)
        self.assertIn("- 01:30 生成 status.txt", text)

    def test_stale_status_detection(self):
        status = app.normalize_vibe_status({
            "updated_at": "2026-05-29 01:00:00",
        })

        self.assertFalse(app.is_vibe_status_stale(
            status,
            now=datetime(2026, 5, 29, 1, 10, 0)
        ))
        self.assertTrue(app.is_vibe_status_stale(
            status,
            now=datetime(2026, 5, 29, 1, 20, 1)
        ))

    def test_main_html_uses_meta_refresh_without_javascript_timer(self):
        usage = app.CodexUsage()
        status = app.default_vibe_status()

        html = app.generate_main_html(usage, status)

        self.assertIn('http-equiv="refresh"', html)
        self.assertNotIn("setTimeout", html)

    def test_settings_html_exposes_stale_threshold(self):
        html = app.generate_settings_html()

        self.assertIn('name="stale_after_seconds"', html)
        self.assertIn("状态过期阈值", html)

    def test_build_health_status_reports_vibe_and_codex_state(self):
        usage = app.CodexUsage()
        usage.source = "session"
        usage.error = ""
        status = app.normalize_vibe_status({
            "state": "运行中",
            "updated_at": app.now_display(),
        })

        health = app.build_health_status(usage, status)

        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["vibe"]["state"], "运行中")
        self.assertFalse(health["vibe"]["stale"])
        self.assertEqual(health["codex"]["source"], "session")

    def test_token_comparison_requires_configured_token(self):
        self.assertTrue(app.tokens_match("secret", "secret"))
        self.assertFalse(app.tokens_match("secret", "wrong"))
        self.assertFalse(app.tokens_match("", "secret"))

    def test_public_config_redacts_configured_api_token(self):
        original_config = app.config
        try:
            app.config = {
                "security": {"api_token": "secret"},
                "server": {"port": 8080},
            }
            safe = app.public_config()
        finally:
            app.config = original_config

        self.assertEqual(safe["security"]["api_token"], "<configured>")
        self.assertEqual(app.config, original_config)


if __name__ == "__main__":
    unittest.main()
