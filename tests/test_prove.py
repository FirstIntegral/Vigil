from __future__ import annotations

import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vigil.cli import main
from vigil.pending import write_decision
from vigil.prove import SENTINEL, deadly_would_hold, prove
from vigil.risk import DENY, classify
from vigil.call import ToolCall


def bash(cmd: str) -> ToolCall:
    return ToolCall(
        event="pre_tool_use",
        tool="bash",
        raw_tool="run_terminal_command",
        command=cmd,
        path=None,
        cwd="/tmp",
        workspace="/tmp",
        session_id="s",
        permission_mode="always-approve",
        agent_hint="grok",
        raw_input={"command": cmd},
    )


class GlassProofTests(unittest.TestCase):
    def test_sentinel_is_deny(self) -> None:
        risk = classify(bash(SENTINEL))
        self.assertEqual(risk.decision, DENY)
        self.assertEqual(risk.class_id, "glass-proof")

    def test_deadly_samples_hold_without_exec(self) -> None:
        rows = deadly_would_hold()
        ids = {row["classId"] for row in rows}
        self.assertIn("rm-root", ids)
        self.assertIn("pipe-shell", ids)
        self.assertTrue(all(row["wouldExec"] is False for row in rows))
        self.assertTrue(all(row["decision"] == DENY for row in rows))

    def test_check_does_not_mint(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            report = prove(home, helper=str(home / "bin" / "vigil"), mint=False)
            self.assertTrue(report["ok"])
            self.assertFalse(report["minted"])
            self.assertFalse(report["asked"])

    def test_mint_holds_and_timeout_denies(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            report = prove(
                home,
                helper=str(home / "bin" / "vigil"),
                mint=True,
                wait_fn=lambda *_: None,
            )
            self.assertTrue(report["asked"])
            self.assertTrue(report["minted"])
            self.assertEqual(report["gateDecision"], DENY)

    def test_cli_check(self) -> None:
        with TemporaryDirectory() as tmp:
            buf = StringIO()
            with patch("vigil.cli.caller_is_agent", return_value=False), patch("sys.stdout", buf):
                rc = main(["--home", tmp, "prove", "--check"])
            self.assertEqual(rc, 0)
            data = json.loads(buf.getvalue())
            self.assertEqual(data["sentinel"], SENTINEL)
            self.assertFalse(data["minted"])

    def test_mint_human_deny(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)

            def deny(h, req_id, timeout_sec, **_kwargs):
                write_decision(h, req_id, "deny")
                from vigil.pending import read_decision

                return read_decision(h, req_id)

            report = prove(home, helper=str(home / "x"), mint=True, wait_fn=deny)
            self.assertEqual(report["gateDecision"], DENY)
            self.assertTrue(report["ok"])
