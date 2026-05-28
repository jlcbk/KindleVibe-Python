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


if __name__ == "__main__":
    unittest.main()
