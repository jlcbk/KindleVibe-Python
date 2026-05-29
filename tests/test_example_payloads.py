import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import app  # noqa: E402
import vibe_update  # noqa: E402


class ExamplePayloadTests(unittest.TestCase):
    def test_payload_examples_are_valid_status_objects(self):
        payload_dir = ROOT / "examples" / "payloads"
        payload_files = sorted(payload_dir.glob("*.json"))

        self.assertGreaterEqual(len(payload_files), 4)
        for payload_file in payload_files:
            with self.subTest(payload=payload_file.name):
                payload = json.loads(payload_file.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
                self.assertIn("state", payload)
                self.assertIn("current_task", payload)
                self.assertIn("next_action", payload)
                normalized = app.normalize_vibe_status(payload)
                self.assertEqual(normalized["state"], payload["state"])

    def test_payload_examples_can_be_loaded_by_cli_helper(self):
        payload_dir = ROOT / "examples" / "payloads"

        for payload_file in sorted(payload_dir.glob("*.json")):
            with self.subTest(payload=payload_file.name):
                payload = vibe_update.load_payload_file(str(payload_file))
                self.assertEqual(payload["state"], json.loads(payload_file.read_text(encoding="utf-8"))["state"])

    def test_cli_preset_names_match_payload_files(self):
        payload_names = {
            payload_file.stem
            for payload_file in (ROOT / "examples" / "payloads").glob("*.json")
        }

        self.assertEqual(payload_names, set(vibe_update.PRESET_NAMES))
