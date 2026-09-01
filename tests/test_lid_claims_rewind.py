from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.claims import claim, conflict
from vigil.lid import sync
from vigil.pending import list_pending
from vigil.policy import load_policy
from vigil.rewind import rewind
from vigil.secure import redact, redact_path


class LidTests(unittest.TestCase):
    def test_lock_freezes(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            state = sync(home, locked=True)
            self.assertTrue(state["frozen"])
            self.assertTrue(state["lidHeld"])
            self.assertEqual(load_policy(home).effective_mode(), "frozen")

    def test_unlock_stamps_away(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            sync(home, locked=True)
            state = sync(home, locked=False)
            self.assertTrue(state["away"])
            pending = list_pending(home)
            self.assertTrue(any(row.get("kind") == "away" for row in pending))
            self.assertEqual(load_policy(home).effective_mode(), "frozen")


class ClaimTests(unittest.TestCase):
    def test_other_passport_conflicts(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            claim(home, "/tmp/foo.py", "grok:a", agent="grok")
            self.assertIsNone(conflict(home, "/tmp/foo.py", "grok:a"))
            hit = conflict(home, "/tmp/foo.py", "claude:b")
            self.assertIsNotNone(hit)
            self.assertEqual(hit["passportId"], "grok:a")


class RewindTests(unittest.TestCase):
    def test_git_checkout_restores_tracked(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True, capture_output=True)
            f = root / "a.txt"
            f.write_text("one\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "t"], cwd=root, check=True, capture_output=True)
            f.write_text("two\n", encoding="utf-8")
            home = Path(tmp) / "home"
            home.mkdir()
            from vigil.audit import append

            append(home, {"event": "allow", "path": str(f), "tool": "write"})
            result = rewind(home, project_root=str(root))
            self.assertIn(str(f), result["restored"])
            self.assertEqual(f.read_text(encoding="utf-8"), "one\n")

    def test_refuses_secret(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = rewind(home, paths=["/home/brwsk/.ssh/id_ed25519"])
            self.assertIn("/home/brwsk/.ssh/id_ed25519", result["skipped"])
            self.assertEqual(result["restored"], [])


class PrivacyTests(unittest.TestCase):
    def test_redact_token_and_pem(self) -> None:
        self.assertIn("<redacted>", redact("Authorization: Bearer supersecretvalue"))
        self.assertIn("<redacted-pem>", redact("-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----"))
        self.assertEqual(redact_path("/home/brwsk/.ssh/id_ed25519"), "<secret>/id_ed25519")

    def test_audit_is_chained(self) -> None:
        from vigil.audit import append, tail

        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            append(home, {"event": "allow", "summary": "pytest"})
            append(home, {"event": "deny", "summary": "rm"})
            rows = tail(home, limit=10)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["prev"], rows[0]["hash"])
            self.assertTrue(rows[0]["hash"])


class GhostsTests(unittest.TestCase):
    def test_empty_without_hyprctl(self) -> None:
        from vigil.call import ToolCall
        from vigil.ghosts import ghosts_for

        call = ToolCall(
            event="pre_tool_use",
            tool="bash",
            raw_tool="run_terminal_command",
            command="rm -rf /",
            path=None,
            cwd="/tmp",
            workspace="/tmp",
            session_id="s",
            permission_mode="",
            agent_hint="grok",
            raw_input={},
        )
        self.assertEqual(ghosts_for(call), [])
