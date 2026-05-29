import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
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

    def test_update_vibe_status_can_clear_events(self):
        app.update_vibe_status({
            "event": "先记录一条事件。"
        })

        status = app.update_vibe_status({
            "events": []
        })

        self.assertEqual(status["events"], [])

    def test_generate_status_text_contains_vibe_and_usage_summary(self):
        usage = app.CodexUsage()
        usage.five_hour_percent_left = 72
        usage.weekly_percent_left = 88
        usage.source = "session"
        usage.last_updated = "2026-05-29 01:30:00"
        usage.local_token_usage["windows"]["24h"]["total_tokens"] = 12345
        usage.local_token_usage["windows"]["24h"]["cache_hit_percent"] = 50.0
        usage.local_token_usage["windows"]["7d"]["total_tokens"] = 23456
        usage.local_token_usage["windows"]["7d"]["cache_hit_percent"] = 25.5
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
        self.assertIn("本机 Token 消耗近 24 小时：12,345 tokens，缓存命中：50.0%", text)
        self.assertIn("本机 Token 消耗近 7 天：23,456 tokens，缓存命中：25.5%", text)
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

    def test_main_html_displays_local_token_usage(self):
        usage = app.CodexUsage()
        usage.local_token_usage["windows"]["24h"]["total_tokens"] = 12345
        usage.local_token_usage["windows"]["24h"]["cache_hit_percent"] = 50.0
        usage.local_token_usage["windows"]["7d"]["total_tokens"] = 23456
        usage.local_token_usage["windows"]["7d"]["cache_hit_percent"] = 25.5

        html = app.generate_main_html(usage, app.default_vibe_status())

        self.assertIn("本机 Token 消耗", html)
        self.assertIn("12,345 tokens", html)
        self.assertIn("缓存命中 50.0%", html)
        self.assertIn("23,456 tokens", html)

    def test_main_html_exposes_layout_switch_and_landscape_class(self):
        original_config = app.config
        try:
            app.config = app.merge_configs(app.DEFAULT_CONFIG, {
                "display": {"layout_mode": "landscape"}
            })
            html = app.generate_main_html(app.CodexUsage(), app.default_vibe_status())
        finally:
            app.config = original_config

        self.assertIn('class="layout-landscape"', html)
        self.assertIn("横屏布局", html)
        self.assertIn('href="/layout?mode=auto"', html)
        self.assertIn('href="/layout?mode=portrait"', html)
        self.assertIn('href="/layout?mode=landscape"', html)
        self.assertIn("dashboard-layout", html)

    def test_normalize_layout_mode_falls_back_to_auto(self):
        self.assertEqual(app.normalize_layout_mode("landscape"), "landscape")
        self.assertEqual(app.normalize_layout_mode("portrait"), "portrait")
        self.assertEqual(app.normalize_layout_mode("bad-value"), "auto")

    def test_settings_html_exposes_stale_threshold(self):
        html = app.generate_settings_html()

        self.assertIn('name="stale_after_seconds"', html)
        self.assertIn("状态过期阈值", html)

    def test_settings_html_exposes_layout_mode(self):
        html = app.generate_settings_html()

        self.assertIn('name="layout_mode"', html)
        self.assertIn("强制横屏布局", html)
        self.assertIn("不能自动旋转", html)

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

    def test_load_vibe_presets_exposes_payloads(self):
        presets = app.load_vibe_presets()
        names = {preset["name"] for preset in presets}

        self.assertEqual(names, set(app.PRESET_NAMES))
        self.assertEqual(len(presets), 4)
        for preset in presets:
            self.assertIn("state", preset)
            self.assertIn("current_task", preset)
            self.assertIn("next_action", preset)
            self.assertIsInstance(preset["payload"], dict)

    def test_generate_presets_text_contains_preset_summary(self):
        text = app.generate_presets_text(app.load_vibe_presets())

        self.assertIn("KindleVibe Presets", text)
        self.assertIn("- coding", text)
        self.assertIn("状态：编码中", text)
        self.assertIn("下一步：", text)

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

    def test_compute_local_token_usage_sums_recent_last_usage(self):
        codex_home = Path(self.tmpdir.name) / ".codex"
        session_dir = codex_home / "sessions" / "2026" / "05"
        session_dir.mkdir(parents=True)
        archive_dir = codex_home / "archived_sessions"
        archive_dir.mkdir(parents=True)
        now = datetime(2026, 5, 29, 10, 0, 0, tzinfo=timezone.utc)

        def token_event(timestamp: datetime, last_total: int, input_tokens: int, cached_tokens: int) -> dict:
            return {
                "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": input_tokens,
                            "cached_input_tokens": cached_tokens,
                            "output_tokens": last_total - input_tokens,
                            "reasoning_output_tokens": 0,
                            "total_tokens": last_total,
                        },
                        "total_token_usage": {
                            "input_tokens": 999999,
                            "cached_input_tokens": 999999,
                            "output_tokens": 999999,
                            "reasoning_output_tokens": 999999,
                            "total_tokens": 999999,
                        },
                    },
                },
            }

        recent_file = session_dir / "recent.jsonl"
        with open(recent_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(token_event(now - timedelta(hours=2), 30, 20, 10)) + "\n")
            f.write("{invalid-json}\n")

        week_file = archive_dir / "week.jsonl"
        with open(week_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(token_event(now - timedelta(days=3), 100, 80, 20)) + "\n")

        old_file = session_dir / "old.jsonl"
        with open(old_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(token_event(now - timedelta(days=8), 500, 500, 500)) + "\n")

        usage = app.compute_local_token_usage(codex_home=codex_home, now=now)

        window_24h = usage["windows"]["24h"]
        self.assertEqual(window_24h["total_tokens"], 30)
        self.assertEqual(window_24h["input_tokens"], 20)
        self.assertEqual(window_24h["cached_input_tokens"], 10)
        self.assertEqual(window_24h["cache_hit_percent"], 50.0)
        self.assertEqual(window_24h["event_count"], 1)
        self.assertEqual(window_24h["session_count"], 1)

        window_7d = usage["windows"]["7d"]
        self.assertEqual(window_7d["total_tokens"], 130)
        self.assertEqual(window_7d["input_tokens"], 100)
        self.assertEqual(window_7d["cached_input_tokens"], 30)
        self.assertEqual(window_7d["cache_hit_percent"], 30.0)
        self.assertEqual(window_7d["event_count"], 2)
        self.assertEqual(window_7d["session_count"], 2)


if __name__ == "__main__":
    unittest.main()
