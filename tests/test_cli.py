from __future__ import annotations

import json
import unittest
from io import StringIO
from unittest.mock import patch

from vigil.cli import main


class CliTests(unittest.TestCase):
    def test_version(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            rc = main(["version"])
        self.assertEqual(rc, 0)
        self.assertIn("brwsk.vigil", buf.getvalue())

    def test_kill_all_requires_yes(self) -> None:
        err = StringIO()
        with patch("sys.stderr", err):
            rc = main(["kill-all"])
        self.assertEqual(rc, 2)
        self.assertIn("--yes", err.getvalue())

    def test_snapshot_schema(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            buf = StringIO()
            with patch("sys.stdout", buf):
                rc = main(["--home", tmp, "snapshot"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["schemaVersion"], 1)
            self.assertEqual(data["pluginId"], "brwsk.vigil")
            self.assertIsInstance(data["sessions"], list)
            self.assertIn("agents", data["totals"])
            self.assertIn("lid", data)


if __name__ == "__main__":
    unittest.main()


class GateCrashTests(unittest.TestCase):
    def _crash(self, payload: dict) -> dict:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp, patch(
            "vigil.cli.gate_payload", side_effect=RuntimeError("boom")
        ), patch("sys.stdin", StringIO(json.dumps(payload))):
            buf = StringIO()
            with patch("sys.stdout", buf):
                rc = main(["--home", tmp, "gate"])
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue())

    def test_crash_denies_in_claude_shape(self) -> None:
        out = self._crash({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {}})
        self.assertNotIn("decision", out)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_crash_denies_in_grok_shape(self) -> None:
        out = self._crash({"hookEventName": "pre_tool_use", "toolName": "run_terminal_command"})
        self.assertEqual(out["decision"], "deny")
