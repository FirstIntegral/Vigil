from __future__ import annotations

import unittest

from vigil.call import parse_envelope


class CallParseTests(unittest.TestCase):
    def test_grok_envelope(self) -> None:
        call = parse_envelope(
            {
                "hookEventName": "pre_tool_use",
                "sessionId": "abc",
                "cwd": "/home/brwsk/projects/vigil",
                "workspaceRoot": "/home/brwsk/projects/vigil",
                "permissionMode": "always-approve",
                "toolName": "run_terminal_command",
                "toolInput": {"command": "rm -rf /"},
            }
        )
        self.assertEqual(call.event, "pre_tool_use")
        self.assertEqual(call.tool, "bash")
        self.assertEqual(call.command, "rm -rf /")
        self.assertEqual(call.agent_hint, "grok")
        self.assertTrue(call.is_pre_tool)

    def test_claude_envelope(self) -> None:
        call = parse_envelope(
            {
                "hook_event_name": "PreToolUse",
                "session_id": "sid",
                "cwd": "/tmp",
                "tool_name": "Bash",
                "tool_input": {"command": "pytest"},
            }
        )
        self.assertEqual(call.tool, "bash")
        self.assertEqual(call.agent_hint, "claude")
        self.assertEqual(call.command, "pytest")

    def test_write_path(self) -> None:
        call = parse_envelope(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Edit",
                "tool_input": {"file_path": "/tmp/x.py", "new_string": "a"},
                "cwd": "/tmp",
            }
        )
        self.assertEqual(call.tool, "write")
        self.assertEqual(call.path, "/tmp/x.py")
