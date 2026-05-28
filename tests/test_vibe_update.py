import sys
import unittest
from pathlib import Path


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
            "--event", "CLI 写入状态。"
        ])

        payload = vibe_update.build_payload(args)

        self.assertEqual(payload["current_task"], "补充 CLI")
        self.assertEqual(payload["next_action"], "运行测试")
        self.assertEqual(payload["participants"], ["@scnet_brain", "@opencode"])
        self.assertEqual(payload["blockers"], [])
        self.assertEqual(payload["event"], "CLI 写入状态。")

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


if __name__ == "__main__":
    unittest.main()
