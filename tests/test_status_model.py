#!/usr/bin/env python3
"""Tests for pure InkDash status model helpers."""

import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).parent.parent))

import status_model  # noqa: E402


class StatusModelTests(unittest.TestCase):
    def test_normalize_status_bounds_events_and_lists(self):
        raw = {
            "state": " 编码中 ",
            "participants": [" @scnet_brain ", "", None, "@opencode"],
            "blockers": "等待输入",
            "events": [
                {"time": f"t{i}", "text": f"事件{i}"}
                for i in range(status_model.MAX_EVENT_ITEMS + 2)
            ],
        }

        status = status_model.normalize_status(raw)

        self.assertEqual(status["state"], "编码中")
        self.assertEqual(status["participants"], ["@scnet_brain", "@opencode"])
        self.assertEqual(status["blockers"], ["等待输入"])
        self.assertEqual(len(status["events"]), status_model.MAX_EVENT_ITEMS)
        self.assertEqual(status["events"][0]["text"], "事件2")

    def test_merge_status_patch_appends_event_and_refreshes_time(self):
        base = status_model.normalize_status({
            "current_task": "旧任务",
            "updated_at": "2026-05-30 12:00:00",
            "events": [{"time": "2026-05-30 12:00:00", "text": "旧事件"}],
        })

        merged = status_model.merge_status_patch(base, {
            "current_task": "新任务",
            "event": "开始处理",
        })

        self.assertEqual(merged["current_task"], "新任务")
        self.assertEqual(merged["events"][-1]["text"], "开始处理")
        self.assertNotEqual(merged["updated_at"], base["updated_at"])

    def test_is_status_stale_uses_supplied_threshold(self):
        old_time = datetime.now() - timedelta(seconds=120)
        status = {"updated_at": old_time.strftime("%Y-%m-%d %H:%M:%S")}

        self.assertTrue(status_model.is_status_stale(status, 60))
        self.assertFalse(status_model.is_status_stale(status, 300))


if __name__ == "__main__":
    unittest.main()
