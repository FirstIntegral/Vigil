from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.gate import gate_payload
from vigil.pending import decorate
from vigil.policy import Policy, save_policy
from vigil.risk import ALLOW


def grok_bash(command: str, cwd: str = "/home/brwsk/Projects/vigil") -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "sessionId": "sess-1",
        "cwd": cwd,
        "workspaceRoot": cwd,
        "permissionMode": "always-approve",
        "toolName": "run_terminal_command",
        "toolInput": {"command": command},
    }


class TrustTests(unittest.TestCase):
    def test_is_trusted_window(self) -> None:
        p = Policy()
        p.trust_for(60, "/home/brwsk/Projects/vigil")
        now = datetime.now(timezone.utc)
        self.assertTrue(p.is_trusted("/home/brwsk/Projects/vigil", now))
        self.assertTrue(p.is_trusted("/home/brwsk/Projects/vigil/src", now))
        self.assertFalse(p.is_trusted("/etc", now))
        expired = now + timedelta(hours=2)
        self.assertFalse(p.is_trusted("/home/brwsk/Projects/vigil", expired))

    def test_trust_downgrades_ask_to_seatbelt(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            policy = Policy(mode="ask")
            policy.trust_for(60, "/home/brwsk/Projects/vigil")
            save_policy(home, policy)
            result = gate_payload(
                grok_bash("git push origin HEAD"),
                home=home,
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("trusted ask must not wait")),
            )
            self.assertEqual(result.decision, ALLOW)
            self.assertFalse(result.asked)


class BarLineTests(unittest.TestCase):
    def test_decorate(self) -> None:
        row = decorate(
            {
                "id": "abc",
                "agent": "grok",
                "summary": "rm -rf /",
                "classId": "rm-root",
                "title": "Delete the filesystem",
            }
        )
        self.assertEqual(row["severity"], "critical")
        self.assertEqual(row["barLine"], "Grok is trying to rm -rf /")
