import sys
import subprocess
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import vibe_update  # noqa: E402


class VibeUpdateTests(unittest.TestCase):
    def test_build_payload_maps_cli_fields(self):
        args = vibe_update.parse_args([
            "--state", "编码中",
            "--project", "KindleVibe-Python",
            "--branch", "feature/cli",
            "--current-task", "补充 CLI",
            "--next-action", "运行测试",
            "--participant", "@scnet_brain",
            "--participant", "@opencode",
            "--blocker", "",
            "--event", "CLI 写入状态。",
            "--heartbeat"
        ])

        payload = vibe_update.build_payload(args)

        self.assertEqual(payload["current_task"], "补充 CLI")
        self.assertEqual(payload["next_action"], "运行测试")
        self.assertEqual(payload["participants"], ["@scnet_brain", "@opencode"])
        self.assertEqual(payload["blockers"], [])
        self.assertEqual(payload["event"], "CLI 写入状态。")
        self.assertTrue(payload["heartbeat"])

    def test_format_summary_uses_chinese_labels(self):
        summary = vibe_update.format_summary({
            "state": "等待评审",
            "project": "KindleVibe-Python",
            "branch": "main",
            "objective": "显示状态",
            "current_task": "检查 PR",
            "next_action": "合并",
            "participants": ["@scnet_brain"],
            "blockers": [],
            "events": [{"text": "测试通过。"}],
            "updated_at": "2026-05-29 01:30:00",
        })

        self.assertIn("状态：等待评审", summary)
        self.assertIn("项目：KindleVibe-Python / 分支：main", summary)
        self.assertIn("阻塞项：无", summary)
        self.assertIn("最近事件：测试通过。", summary)

    def test_from_git_fills_project_and_branch_without_overriding_explicit_values(self):
        def fake_run(cmd, cwd, capture_output, text, timeout):
            self.assertEqual(cwd, "/tmp/work")
            if cmd[1:] == ["rev-parse", "--show-toplevel"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="/tmp/work/KindleVibe-Python\n")
            if cmd[1:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="feature/status\n")
            return subprocess.CompletedProcess(cmd, 1, stdout="")

        args = vibe_update.parse_args([
            "--from-git",
            "--cwd", "/tmp/work",
            "--project", "显式项目",
        ])

        with patch("vibe_update.subprocess.run", side_effect=fake_run):
            payload = vibe_update.build_payload(args)

        self.assertEqual(payload["project"], "显式项目")
        self.assertEqual(payload["branch"], "feature/status")

    def test_payload_file_is_loaded_and_cli_fields_override(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload_file = Path(tmpdir) / "payload.json"
            payload_file.write_text(json.dumps({
                "state": "文件状态",
                "project": "文件项目",
                "participants": ["@file"],
            }, ensure_ascii=False), encoding="utf-8")

            args = vibe_update.parse_args([
                "--payload-file", str(payload_file),
                "--state", "命令行状态",
                "--participant", "@cli",
            ])
            payload = vibe_update.build_payload(args)

        self.assertEqual(payload["state"], "命令行状态")
        self.assertEqual(payload["project"], "文件项目")
        self.assertEqual(payload["participants"], ["@cli"])

    def test_preset_payload_is_loaded_and_cli_fields_override(self):
        args = vibe_update.parse_args([
            "--preset", "coding",
            "--state", "自定义状态",
            "--from-git",
        ])

        with patch("vibe_update.detect_git_context", return_value={"project": "Demo", "branch": "main"}):
            payload = vibe_update.build_payload(args)

        self.assertEqual(payload["state"], "自定义状态")
        self.assertEqual(payload["current_task"], "实现并验证一个小功能点")
        self.assertEqual(payload["project"], "Demo")
        self.assertEqual(payload["branch"], "main")

    def test_preset_conflicts_with_payload_file(self):
        args = vibe_update.parse_args([
            "--preset", "coding",
            "--payload-file", "status.json",
        ])

        with self.assertRaisesRegex(ValueError, "--preset"):
            vibe_update.build_payload(args)

    def test_list_presets_returns_summaries(self):
        presets = vibe_update.list_presets()
        names = {preset["name"] for preset in presets}
        summary = vibe_update.format_preset_list(presets)

        self.assertEqual(names, set(vibe_update.PRESET_NAMES))
        self.assertIn("coding", summary)
        self.assertIn("下一步", summary)

    def test_clear_flags_build_empty_lists(self):
        args = vibe_update.parse_args([
            "--clear-blockers",
            "--clear-participants",
            "--clear-events",
            "--event", "清理历史后继续。"
        ])

        payload = vibe_update.build_payload(args)

        self.assertEqual(payload["blockers"], [])
        self.assertEqual(payload["participants"], [])
        self.assertEqual(payload["events"], [])
        self.assertEqual(payload["event"], "清理历史后继续。")

    def test_clear_flags_conflict_with_explicit_lists(self):
        args = vibe_update.parse_args([
            "--blocker", "等待 CI",
            "--clear-blockers",
        ])

        with self.assertRaisesRegex(ValueError, "--blocker"):
            vibe_update.build_payload(args)

    def test_default_url_can_come_from_environment(self):
        with patch.dict(vibe_update.os.environ, {"KINDLEVIBE_URL": "http://kindle.local/api/vibe"}):
            args = vibe_update.parse_args([])

        self.assertEqual(args.url, "http://kindle.local/api/vibe")

    def test_default_token_can_come_from_environment(self):
        with patch.dict(vibe_update.os.environ, {"KINDLEVIBE_TOKEN": "secret"}):
            args = vibe_update.parse_args([])

        self.assertEqual(args.token, "secret")

    def test_derive_health_url_from_vibe_url(self):
        self.assertEqual(
            vibe_update.derive_health_url("http://localhost:8080/api/vibe"),
            "http://localhost:8080/api/health",
        )
        self.assertEqual(
            vibe_update.derive_health_url("http://localhost:8080"),
            "http://localhost:8080/api/health",
        )

    def test_format_health_summary(self):
        summary = vibe_update.format_health_summary({
            "status": "ok",
            "checked_at": "2026-05-29 02:20:00",
            "vibe": {
                "state": "运行中",
                "stale": False,
                "updated_at": "2026-05-29 02:19:00",
            },
            "codex": {
                "source": "session",
                "error": "",
            },
        })

        self.assertIn("服务：ok", summary)
        self.assertIn("Vibe 心跳：正常", summary)
        self.assertIn("Codex 数据来源：session", summary)

    def test_wait_for_health_returns_after_retry(self):
        calls = [
            RuntimeError("无法连接 KindleVibe"),
            {"status": "ok", "vibe": {}, "codex": {}},
        ]

        def fake_request(url, payload, timeout, token):
            result = calls.pop(0)
            if isinstance(result, RuntimeError):
                raise result
            return result

        with patch("vibe_update.request_vibe", side_effect=fake_request):
            health = vibe_update.wait_for_health(
                "http://localhost:8080/api/vibe",
                request_timeout=0.1,
                wait_timeout=2.0,
                wait_interval=0.1,
                sleep_fn=lambda _: None,
                monotonic_fn=iter([0.0, 0.1]).__next__,
            )

        self.assertEqual(health["status"], "ok")

    def test_wait_for_health_times_out_with_last_error(self):
        with patch("vibe_update.request_vibe", side_effect=RuntimeError("连接失败")):
            with self.assertRaisesRegex(RuntimeError, "连接失败"):
                vibe_update.wait_for_health(
                    "http://localhost:8080/api/vibe",
                    request_timeout=0.1,
                    wait_timeout=0.0,
                    wait_interval=0.1,
                    sleep_fn=lambda _: None,
                    monotonic_fn=iter([0.0, 0.0]).__next__,
                )


if __name__ == "__main__":
    unittest.main()
