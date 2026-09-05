from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.call import ToolCall
from vigil.envelope import apply_envelope
from vigil.gate import gate_payload
from vigil.passport import upsert
from vigil.risk import ASK, ALLOW, classify


def bash(cmd: str, cwd: str = "/home/brwsk/Projects/Vigil") -> ToolCall:
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
                cwd="/home/brwsk/Projects/Vigil",
                envelope="project",
            )
            payload = {
                "hookEventName": "pre_tool_use",
                "sessionId": "sess-1",
                "cwd": "/home/brwsk/Projects/Vigil",
                "workspaceRoot": "/home/brwsk/Projects/Vigil",
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
                    "cwd": "/home/brwsk/Projects/Vigil",
                    "workspaceRoot": "/home/brwsk/Projects/Vigil",
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

    def test_read_holds_project_write(self) -> None:
        call = ToolCall(
            event="pre_tool_use",
            tool="write",
            raw_tool="search_replace",
            command=None,
            path="/home/brwsk/Projects/Vigil/README.md",
            cwd="/home/brwsk/Projects/Vigil",
            workspace="/home/brwsk/Projects/Vigil",
            session_id="s",
            permission_mode="",
            agent_hint="grok",
            raw_input={},
        )
        held = apply_envelope("read", classify(call), call)
        self.assertTrue(held.hold)

    def test_desktop_holds_plugin_inject(self) -> None:
        risk = classify(bash("omarchy plugin add https://example.com/x.git"))
        held = apply_envelope("desktop", risk, bash("omarchy plugin add https://example.com/x.git"))
        self.assertTrue(held.hold)
        self.assertEqual(held.decision, "deny")
