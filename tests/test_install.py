from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.install import grok_hook_document, install, merge_claude_hooks, uninstall


class InstallTests(unittest.TestCase):
    def test_grok_hook_has_long_timeout(self) -> None:
        doc = grok_hook_document("/opt/vigil/bin/vigil")
        handler = doc["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertEqual(handler["timeout"], 120)
        self.assertIn("vigil gate", handler["command"])

    def test_install_and_uninstall_grok_file(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            helper = "/x/bin/vigil"
            written = install(home, helper)
            path = Path(written["grok"])
            self.assertTrue(path.is_file())
            body = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("PreToolUse", body["hooks"])
            uninstall(home, helper)
            self.assertFalse(path.exists())

    def test_claude_merge_keeps_other_hooks(self) -> None:
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo other"}],
                    }
                ]
            }
        }
        merged = merge_claude_hooks(settings, "/x/bin/vigil")
        groups = merged["hooks"]["PreToolUse"]
        commands = []
        for g in groups:
            for h in g.get("hooks", []):
                commands.append(h["command"])
        self.assertIn("echo other", commands)
        self.assertTrue(any("vigil gate" in c for c in commands))
        self.assertEqual(sum(1 for c in commands if "vigil gate" in c), 1)
        again = merge_claude_hooks(merged, "/x/bin/vigil")
        commands2 = [
            h["command"] for g in again["hooks"]["PreToolUse"] for h in g.get("hooks", [])
        ]
        self.assertEqual(sum(1 for c in commands2 if "vigil gate" in c), 1)
