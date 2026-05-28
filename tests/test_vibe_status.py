import json
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
