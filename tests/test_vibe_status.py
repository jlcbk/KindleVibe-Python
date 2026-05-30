import json
import os
import sys
import tempfile
import threading
import time
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
            "project": "InkDash",
            "branch": "feature/vibe-board",
            "objective": "显示 vibe coding 状态",
            "participants": ["@scnet_brain", "@opencode"],
            "blockers": [],
            "event": "完成状态写入接口。"
        })

        self.assertEqual(status["state"], "编码中")
        self.assertEqual(status["project"], "InkDash")
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

    def test_update_vibe_status_serializes_read_modify_write(self):
        original_merge = app.merge_status_patch
        start = threading.Barrier(3)
        errors = []

        def slow_merge(status, patch):
            if patch.get("event") in {"并发 A", "并发 B"}:
                time.sleep(0.05)
            return original_merge(status, patch)

        def worker(event_text):
            try:
                start.wait(timeout=2)
                app.update_vibe_status({"event": event_text})
            except Exception as exc:
                errors.append(exc)

        app.merge_status_patch = slow_merge
        threads = [
            threading.Thread(target=worker, args=("并发 A",)),
            threading.Thread(target=worker, args=("并发 B",)),
        ]
        try:
            for thread in threads:
                thread.start()
            start.wait(timeout=2)
            for thread in threads:
                thread.join(timeout=2)
        finally:
            app.merge_status_patch = original_merge

        self.assertFalse(errors)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        events = [event["text"] for event in app.load_vibe_status()["events"]]
        self.assertIn("并发 A", events)
        self.assertIn("并发 B", events)

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
            "project": "InkDash",
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
            html = app.generate_main_html(
                app.CodexUsage(),
                app.default_vibe_status(),
                text_scale_percent=150,
            )
        finally:
            app.config = original_config

        self.assertIn('class="layout-landscape"', html)
        self.assertIn('--text-scale: 1.50', html)
        self.assertIn("150%字号", html)
        self.assertIn("横屏布局", html)
        self.assertIn('href="/layout?mode=auto"', html)
        self.assertIn('href="/layout?mode=portrait"', html)
        self.assertIn('href="/layout?mode=landscape"', html)
        self.assertIn('href="/text-scale?scale=100"', html)
        self.assertIn('href="/text-scale?scale=125"', html)
        self.assertIn('href="/text-scale?scale=150"', html)
        self.assertIn('href="/text-scale?scale=200"', html)
        self.assertIn("dashboard-layout", html)

    def test_normalize_layout_mode_falls_back_to_auto(self):
        self.assertEqual(app.normalize_layout_mode("landscape"), "landscape")
        self.assertEqual(app.normalize_layout_mode("portrait"), "portrait")
        self.assertEqual(app.normalize_layout_mode("bad-value"), "auto")

    def test_normalize_text_scale_clamps_to_supported_range(self):
        self.assertEqual(app.normalize_text_scale("150"), 150)
        self.assertEqual(app.normalize_text_scale("10"), app.TEXT_SCALE_MIN)
        self.assertEqual(app.normalize_text_scale("999"), app.TEXT_SCALE_MAX)
        self.assertEqual(app.normalize_text_scale("bad-value"), app.TEXT_SCALE_DEFAULT)

    def test_refresh_helpers_clamp_invalid_config_values(self):
        self.assertEqual(app.refresh_interval_seconds("bad-value"), 300)
        self.assertEqual(app.refresh_interval_seconds(5), 30)
        self.assertEqual(app.refresh_interval_seconds(99999), 3600)
        self.assertEqual(app.page_refresh_seconds("bad-value"), 300)
        self.assertEqual(app.page_refresh_seconds(5000), 30)
        self.assertEqual(app.page_refresh_seconds(99999999), 3600)

    def test_server_helpers_clamp_invalid_config_values(self):
        self.assertEqual(app.server_port_number("bad-value"), 8080)
        self.assertEqual(app.server_port_number(0), 1)
        self.assertEqual(app.server_port_number(999999), 65535)
        self.assertEqual(app.server_host_value(""), "0.0.0.0")
        self.assertEqual(app.server_host_value(" 127.0.0.1 "), "127.0.0.1")

    def test_pages_tolerate_invalid_refresh_config_values(self):
        original_config = app.config
        try:
            app.config = {
                "refresh": {
                    "interval_seconds": "bad-value",
                    "auto_refresh_page_ms": "bad-value",
                }
            }
            main_html = app.generate_main_html(app.CodexUsage(), app.default_vibe_status())
            settings_html = app.generate_settings_html()
        finally:
            app.config = original_config

        self.assertIn('http-equiv="refresh" content="300"', main_html)
        self.assertIn('name="refresh_interval" value="300"', settings_html)
        self.assertIn('name="refresh_page" value="300"', settings_html)

    def test_settings_html_tolerates_invalid_server_config_values(self):
        original_config = app.config
        try:
            app.config = {"server": {"port": "bad-value", "host": ""}}
            html = app.generate_settings_html()
        finally:
            app.config = original_config

        self.assertIn('name="port" value="8080"', html)
        self.assertIn('name="host" value="0.0.0.0"', html)

    def test_settings_html_exposes_stale_threshold(self):
        html = app.generate_settings_html()

        self.assertIn('name="stale_after_seconds"', html)
        self.assertIn("状态过期阈值", html)

    def test_settings_html_exposes_layout_mode(self):
        html = app.generate_settings_html()

        self.assertIn('name="layout_mode"', html)
        self.assertIn("强制横屏布局", html)
        self.assertIn("不能自动旋转", html)
        self.assertIn('name="text_scale_percent"', html)
        self.assertIn("默认字号比例", html)

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
        self.assertEqual(health["status_board"]["state"], "运行中")
        self.assertFalse(health["status_board"]["stale"])
        self.assertEqual(health["vibe"]["state"], "运行中")
        self.assertFalse(health["vibe"]["stale"])
        self.assertEqual(health["codex"]["source"], "session")

    def test_config_migration_copies_legacy_vibe_stale_setting(self):
        merged = app.migrate_config(
            app.merge_configs(app.DEFAULT_CONFIG, {
                "vibe": {"stale_after_seconds": 1234},
            }),
            {"vibe": {"stale_after_seconds": 1234}},
        )

        self.assertEqual(merged["status"]["stale_after_seconds"], 1234)

    def test_config_migration_prefers_explicit_status_setting(self):
        merged = app.migrate_config(
            app.merge_configs(app.DEFAULT_CONFIG, {
                "status": {"stale_after_seconds": 2222},
                "vibe": {"stale_after_seconds": 1234},
            }),
            {
                "status": {"stale_after_seconds": 2222},
                "vibe": {"stale_after_seconds": 1234},
            },
        )

        self.assertEqual(merged["status"]["stale_after_seconds"], 2222)

    def test_merge_configs_does_not_share_nested_defaults(self):
        merged = app.merge_configs(app.DEFAULT_CONFIG, {
            "display": {"show_credits": True},
        })

        merged["server"]["port"] = 9999
        merged["display"]["layout_mode"] = "landscape"

        self.assertEqual(app.DEFAULT_CONFIG["server"]["port"], 8080)
        self.assertEqual(app.DEFAULT_CONFIG["display"]["layout_mode"], "auto")

    def test_load_config_default_result_does_not_share_nested_defaults(self):
        original_config_file = app.CONFIG_FILE
        try:
            app.CONFIG_FILE = Path(self.tmpdir.name) / "missing-config.json"

            loaded = app.load_config()
            loaded["server"]["port"] = 9999
            loaded["display"]["layout_mode"] = "landscape"
        finally:
            app.CONFIG_FILE = original_config_file

        self.assertEqual(app.DEFAULT_CONFIG["server"]["port"], 8080)
        self.assertEqual(app.DEFAULT_CONFIG["display"]["layout_mode"], "auto")

    def test_setup_logging_does_not_duplicate_handlers(self):
        handler_count = len(app.logger.handlers)
        app.setup_logging()
        app.setup_logging()

        self.assertEqual(len(app.logger.handlers), handler_count)

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

        self.assertIn("InkDash Presets", text)
        self.assertIn("- coding", text)
        self.assertIn("状态：编码中", text)
        self.assertIn("下一步：", text)

    def test_token_comparison_requires_configured_token(self):
        self.assertTrue(app.tokens_match("secret", "secret"))
        self.assertFalse(app.tokens_match("secret", "wrong"))
        self.assertFalse(app.tokens_match("", "secret"))
        self.assertFalse(app.tokens_match("secret", None))

    def test_request_line_redacts_query_token_before_logging(self):
        request_line = "POST /api/status?token=secret&event=ok&token=second HTTP/1.1"

        redacted = app.redact_sensitive_request_line(request_line)

        self.assertNotIn("secret", redacted)
        self.assertNotIn("second", redacted)
        self.assertIn("token=REDACTED", redacted)
        self.assertIn("event=ok", redacted)

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

    def test_compute_local_token_usage_respects_session_file_limit(self):
        codex_home = Path(self.tmpdir.name) / ".codex"
        session_dir = codex_home / "sessions"
        session_dir.mkdir(parents=True)
        now = datetime(2026, 5, 29, 10, 0, 0, tzinfo=timezone.utc)

        def write_session(path: Path, event_time: datetime, total_tokens: int):
            payload = {
                "timestamp": event_time.isoformat().replace("+00:00", "Z"),
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "last_token_usage": {
                            "input_tokens": total_tokens,
                            "cached_input_tokens": 0,
                            "output_tokens": 0,
                            "reasoning_output_tokens": 0,
                            "total_tokens": total_tokens,
                        },
                    },
                },
            }
            path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            timestamp = event_time.timestamp()
            os.utime(path, (timestamp, timestamp))

        write_session(session_dir / "newest.jsonl", now - timedelta(hours=1), 10)
        write_session(session_dir / "second.jsonl", now - timedelta(hours=2), 20)
        write_session(session_dir / "third.jsonl", now - timedelta(hours=3), 100)

        usage = app.compute_local_token_usage(
            codex_home=codex_home,
            now=now,
            session_file_limit=2,
        )

        self.assertEqual(usage["windows"]["24h"]["total_tokens"], 30)
        self.assertEqual(usage["windows"]["24h"]["session_count"], 2)

    def test_codex_session_file_limit_clamps_invalid_values(self):
        self.assertEqual(app.codex_session_file_limit("bad-value"), 10)
        self.assertEqual(app.codex_session_file_limit(0), 1)
        self.assertEqual(app.codex_session_file_limit(999), 100)

    def test_main_html_has_grid_supports_fallback(self):
        html = app.generate_main_html(
            app.CodexUsage(),
            app.default_vibe_status(),
        )
        self.assertIn("@supports (display: grid)", html)
        self.assertIn(".dashboard-layout", html)

    def test_landscape_narrow_no_min_width_overflow(self):
        html = app.generate_main_html(
            app.CodexUsage(),
            app.default_vibe_status(),
            layout_mode="landscape",
        )
        self.assertNotIn("min-width: 920px", html)
        self.assertIn("layout-landscape", html)

    def test_settings_page_escapes_dynamic_html(self):
        html = app.generate_settings_html(message="<script>alert(1)</script>")
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_settings_page_escapes_host_value(self):
        host = '"><script>alert(1)</script>'
        original_config = app.config
        try:
            app.config = app.merge_configs(app.DEFAULT_CONFIG, {
                "server": {"host": host}
            })
            html = app.generate_settings_html()
        finally:
            app.config = original_config
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>alert", html)

    def test_load_vibe_status_falls_back_to_legacy_file(self):
        legacy = Path(self.tmpdir.name) / "vibe_status.json"
        new_file = Path(self.tmpdir.name) / "inkdash_status.json"
        self.assertFalse(legacy.exists())
        self.assertFalse(new_file.exists())

        legacy.write_text(json.dumps({"state": "from-legacy"}), encoding="utf-8")
        self.assertTrue(legacy.exists())
        self.assertFalse(new_file.exists())

        original_status = app.STATUS_FILE
        original_legacy = app.STATUS_FILE_LEGACY
        try:
            app.STATUS_FILE = new_file
            app.STATUS_FILE_LEGACY = legacy

            status = app.load_vibe_status()
        finally:
            app.STATUS_FILE = original_status
            app.STATUS_FILE_LEGACY = original_legacy

        self.assertEqual(status.get("state"), "from-legacy")

    def test_settings_page_max_width_matches_main_page(self):
        html = app.generate_settings_html()
        self.assertIn("max-width: 1040px", html)

    def test_default_vibe_status_mentions_api_status(self):
        status = app.default_vibe_status()
        self.assertIn("/api/status", status.get("next_action", ""))

    def test_display_status_board_prefers_new_key_with_legacy_fallback(self):
        self.assertTrue(app.display_status_board_enabled({"show_vibe_board": True}))
        self.assertFalse(app.display_status_board_enabled({"show_status_board": False, "show_vibe_board": True}))
        self.assertFalse(app.display_status_board_enabled({"show_status_board": "false"}))
        self.assertTrue(app.display_status_board_enabled({"show_status_board": "true"}))

    def test_display_flags_parse_string_booleans(self):
        display = {
            "show_plan_type": "true",
            "show_credits": "false",
            "show_data_source": "0",
            "show_last_updated": "no",
        }

        self.assertTrue(app.display_flag(display, "show_plan_type"))
        self.assertFalse(app.display_flag(display, "show_credits"))
        self.assertFalse(app.display_flag(display, "show_data_source"))
        self.assertFalse(app.display_flag(display, "show_last_updated"))

    def test_codex_enabled_flag_parses_string_booleans(self):
        self.assertFalse(app.codex_enabled_flag("false"))
        self.assertFalse(app.codex_enabled_flag("0"))
        self.assertTrue(app.codex_enabled_flag("true"))
        self.assertTrue(app.codex_enabled_flag(None))

    def test_safe_content_length_bounds_invalid_values(self):
        self.assertEqual(app.safe_content_length("bad-value"), 0)
        self.assertEqual(app.safe_content_length("-10"), 0)
        self.assertEqual(app.safe_content_length("42"), 42)
        self.assertEqual(app.safe_content_length(str(app.MAX_POST_BODY_BYTES + 1)), app.MAX_POST_BODY_BYTES)

    def test_fetch_codex_usage_honors_string_false_enabled_flag(self):
        original_config = app.config
        original_attach = app.attach_local_token_usage
        try:
            app.config = {"codex": {"enabled": "false"}}
            app.attach_local_token_usage = lambda usage: usage

            usage = app.fetch_codex_usage()
        finally:
            app.config = original_config
            app.attach_local_token_usage = original_attach

        self.assertEqual(usage.source, "disabled")
        self.assertEqual(usage.error, "Codex 监控已关闭")

    def test_settings_page_uses_status_board_field_name(self):
        html = app.generate_settings_html()
        self.assertIn('name="show_status_board"', html)
        self.assertIn("显示状态看板", html)
        self.assertNotIn('name="show_vibe_board"', html)


if __name__ == "__main__":
    unittest.main()
