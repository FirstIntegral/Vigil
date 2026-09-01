from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.call import ToolCall
from vigil.envelope import apply_envelope
from vigil.gate import gate_payload
from vigil.passport import upsert
from vigil.risk import ASK, ALLOW, classify


def bash(cmd: str, cwd: str = "/home/brwsk/projects/vigil") -> ToolCall:
    return ToolCall(
        event="pre_tool_use",
        tool="bash",
        raw_tool="run_terminal_command",
        command=cmd,
        path=None,
        cwd=cwd,
        workspace=cwd,
        session_id="s",
        permission_mode="always-approve",
        agent_hint="grok",
        raw_input={"command": cmd},
    )


class EnvelopeTests(unittest.TestCase):
    def test_project_holds_outside_write_in_seatbelt(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            upsert(
                home,
                agent="grok",
                session_id="sess-1",
                cwd="/home/brwsk/projects/vigil",
                envelope="project",
            )
            payload = {
                "hookEventName": "pre_tool_use",
                "sessionId": "sess-1",
                "cwd": "/home/brwsk/projects/vigil",
                "workspaceRoot": "/home/brwsk/projects/vigil",
                "permissionMode": "always-approve",
                "toolName": "search_replace",
                "toolInput": {"file_path": "/etc/hosts"},
            }
            result = gate_payload(payload, home=home, wait_fn=lambda *_: None)
            self.assertTrue(result.asked)
            self.assertEqual(result.decision, "deny")

    def test_seatbelt_envelope_lets_pytest_through(self) -> None:
        with TemporaryDirectory() as tmp:
            result = gate_payload(
                {
                    "hookEventName": "pre_tool_use",
                    "sessionId": "s",
                    "cwd": "/home/brwsk/projects/vigil",
                    "workspaceRoot": "/home/brwsk/projects/vigil",
                    "toolName": "run_terminal_command",
                    "toolInput": {"command": "pytest"},
                },
                home=Path(tmp),
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("pytest")),
            )
            self.assertEqual(result.decision, ALLOW)
            self.assertFalse(result.asked)

    def test_hermit_marks_network_hold(self) -> None:
        risk = classify(bash("curl https://example.com"))
        held = apply_envelope("hermit", risk, bash("curl https://example.com"))
        self.assertTrue(held.hold)
        self.assertEqual(held.decision, ASK)
