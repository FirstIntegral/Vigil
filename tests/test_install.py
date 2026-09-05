from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil import ASK_WAIT_SEC, HOOK_TIMEOUT_SEC
from vigil.install import grok_hook_document, hooks_installed, install, merge_claude_hooks, uninstall
from vigil.policy import load_policy
from vigil.secure import write_private


class InstallTests(unittest.TestCase):
    def test_grok_hook_has_long_timeout(self) -> None:
        doc = grok_hook_document("/opt/vigil/bin/vigil")
        handler = doc["hooks"]["PreToolUse"][0]["hooks"][0]
        self.assertEqual(handler["timeout"], HOOK_TIMEOUT_SEC)
        self.assertGreater(HOOK_TIMEOUT_SEC, 300)
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
            self.assertFalse((home / ".config" / "opencode" / "plugins" / "vigil.js").exists())
            self.assertFalse((home / ".codex" / "hooks.json").exists())
            from vigil.policy import load_policy

            self.assertFalse(load_policy(home).auto_arm)
            install(home, helper)
            self.assertTrue(load_policy(home).auto_arm)

    def test_install_writes_opencode_and_codex(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            helper = "/x/bin/vigil"
            written = install(home, helper)
            opath = Path(written["opencode"])
            xpath = Path(written["codex"])
            self.assertTrue(opath.is_file())
            self.assertIn(helper, opath.read_text(encoding="utf-8"))
            plugin = opath.read_text(encoding="utf-8")
            self.assertIn("tool.execute.before", plugin)
            self.assertIn(str(HOOK_TIMEOUT_SEC * 1000), plugin)
            self.assertNotIn("__VIGIL_HOOK_TIMEOUT_MS__", plugin)
            body = json.loads(xpath.read_text(encoding="utf-8"))
            self.assertIn("PreToolUse", body["hooks"])
            self.assertIn("vigil gate", json.dumps(body))
            self.assertEqual(body["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"], HOOK_TIMEOUT_SEC)
            flags = hooks_installed(home, helper)
            self.assertTrue(flags["grok"])
            self.assertTrue(flags["opencode"])
            self.assertTrue(flags["codex"])

    def test_stale_hook_timeout_counts_as_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            helper = "/x/bin/vigil"
            install(home, helper)
            grok = home / ".grok" / "hooks" / "vigil.json"
            doc = json.loads(grok.read_text(encoding="utf-8"))
            doc["hooks"]["PreToolUse"][0]["hooks"][0]["timeout"] = 120
            grok.write_text(json.dumps(doc), encoding="utf-8")
            self.assertFalse(hooks_installed(home, helper)["grok"])

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


class AskWindowTests(unittest.TestCase):
    def test_hook_outlives_the_card(self) -> None:
        self.assertEqual(ASK_WAIT_SEC, 300)
        self.assertEqual(HOOK_TIMEOUT_SEC, 330)
        self.assertGreater(HOOK_TIMEOUT_SEC, ASK_WAIT_SEC)

    def test_legacy_90_becomes_five_minutes(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / ".config" / "vigil" / "policy.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            write_private(path, '{"timeoutSec": 90, "mode": "seatbelt"}\n')
            self.assertEqual(load_policy(home).timeout_sec, ASK_WAIT_SEC)

    def test_explicit_shorter_window_is_kept(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / ".config" / "vigil" / "policy.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            write_private(path, '{"timeoutSec": 180, "mode": "seatbelt"}\n')
            self.assertEqual(load_policy(home).timeout_sec, 180)

    def test_new_policy_default_is_five_minutes(self) -> None:
        with TemporaryDirectory() as tmp:
            self.assertEqual(load_policy(Path(tmp)).timeout_sec, ASK_WAIT_SEC)
