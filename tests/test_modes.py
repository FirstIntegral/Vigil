from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.gate import apply_mode, gate_payload
from vigil.policy import Policy, save_policy
from vigil.risk import ALLOW, ASK, DENY


def grok_bash(command: str) -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "sessionId": "sess-1",
        "cwd": "/home/brwsk/projects/vigil",
        "workspaceRoot": "/home/brwsk/projects/vigil",
        "permissionMode": "always-approve",
        "toolName": "run_terminal_command",
        "toolInput": {"command": command},
    }


class ApplyModeTests(unittest.TestCase):
    def test_table(self) -> None:
        self.assertEqual(apply_mode("off", DENY), ALLOW)
        self.assertEqual(apply_mode("frozen", ALLOW), DENY)
        self.assertEqual(apply_mode("seatbelt", DENY), ASK)
        self.assertEqual(apply_mode("seatbelt", ASK), ALLOW)
        self.assertEqual(apply_mode("seatbelt", ALLOW), ALLOW)
        self.assertEqual(apply_mode("ask", ASK), ASK)
        self.assertEqual(apply_mode("ask", DENY), DENY)


class SeatbeltTests(unittest.TestCase):
    def test_default_lets_git_push_through(self) -> None:
        with TemporaryDirectory() as tmp:
            result = gate_payload(
                grok_bash("git push origin HEAD"),
                home=Path(tmp),
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("seatbelt must not ask")),
            )
            self.assertEqual(result.decision, ALLOW)
            self.assertFalse(result.asked)

    def test_default_holds_rm_root(self) -> None:
        with TemporaryDirectory() as tmp:
            result = gate_payload(
                grok_bash("rm -rf /"),
                home=Path(tmp),
                wait_fn=lambda *_: None,
            )
            self.assertEqual(result.decision, DENY)
            self.assertTrue(result.asked)

    def test_default_lets_sudo_through(self) -> None:
        with TemporaryDirectory() as tmp:
            result = gate_payload(
                grok_bash("sudo true"),
                home=Path(tmp),
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("seatbelt must not ask sudo")),
            )
            self.assertEqual(result.decision, ALLOW)
            self.assertFalse(result.asked)

    def test_off_allows_rm_root(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            save_policy(home, Policy(mode="off"))
            result = gate_payload(
                grok_bash("rm -rf /"),
                home=home,
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("off must not ask")),
            )
            self.assertEqual(result.decision, ALLOW)
            self.assertFalse(result.asked)
