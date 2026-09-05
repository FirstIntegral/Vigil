from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from vigil.call import parse_envelope
from vigil.gate import gate_call, gate_payload
from vigil.pending import write_decision
from vigil.policy import Policy, save_policy
from vigil.risk import ALLOW, DENY


def ask_policy() -> Policy:
    return Policy(mode="ask")


def grok_bash(command: str) -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "sessionId": "sess-1",
        "cwd": "/home/brwsk/Projects/Vigil",
        "workspaceRoot": "/home/brwsk/Projects/Vigil",
        "permissionMode": "always-approve",
        "toolName": "run_terminal_command",
        "toolInput": {"command": command},
    }


class GateTests(unittest.TestCase):
    def test_ask_mode_denies_rm_root_without_card(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            save_policy(home, ask_policy())
            result = gate_payload(grok_bash("rm -rf /"), home=home, wait_fn=lambda *_: None)
            self.assertEqual(result.decision, DENY)
            self.assertFalse(result.asked)
            self.assertEqual(result.response["decision"], "deny")

    def test_silent_allow_pytest(self) -> None:
        with TemporaryDirectory() as tmp:
            result = gate_payload(grok_bash("pytest"), home=Path(tmp), wait_fn=lambda *_: None)
            self.assertEqual(result.decision, ALLOW)
            self.assertFalse(result.asked)

    def test_frozen_denies_everything(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            policy = Policy(frozen=True)
            save_policy(home, policy)
            result = gate_payload(grok_bash("pytest"), home=home, wait_fn=lambda *_: None)
            self.assertEqual(result.decision, DENY)
            self.assertIn("frozen", result.reason.lower())

    def test_ask_timeout_is_deny(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)

            def no_one(*_args, **_kwargs):
                return None

            save_policy(home, ask_policy())
            result = gate_payload(
                grok_bash("curl https://example.com"),
                home=home,
                wait_fn=no_one,
            )
            self.assertEqual(result.decision, DENY)
            self.assertTrue(result.asked)
            self.assertIn("No one answered", result.reason)

    def test_ask_allow_once(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)

            def allow_once(h, req_id, timeout_sec, **_kwargs):
                write_decision(h, req_id, "allow")
                from vigil.pending import read_decision

                return read_decision(h, req_id)

            save_policy(home, ask_policy())
            result = gate_payload(
                grok_bash("git push origin HEAD"),
                home=home,
                wait_fn=allow_once,
            )
            self.assertEqual(result.decision, ALLOW)
            self.assertTrue(result.asked)

    def test_deny_always_remembers(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)

            def deny_always(h, req_id, timeout_sec, **_kwargs):
                write_decision(h, req_id, "deny-always")
                from vigil.pending import read_decision

                return read_decision(h, req_id)

            save_policy(home, ask_policy())
            first = gate_payload(grok_bash("git push origin HEAD"), home=home, wait_fn=deny_always)
            self.assertEqual(first.decision, DENY)
            second = gate_payload(
                grok_bash("git push origin feature"),
                home=home,
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("deny-always must not re-ask")),
            )
            self.assertEqual(second.decision, DENY)
            self.assertFalse(second.asked)

    def test_always_allow_remembers(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)

            def always(h, req_id, timeout_sec, **_kwargs):
                write_decision(h, req_id, "always")
                from vigil.pending import read_decision

                return read_decision(h, req_id)

            save_policy(home, ask_policy())
            first = gate_payload(grok_bash("git push origin HEAD"), home=home, wait_fn=always)
            self.assertEqual(first.decision, ALLOW)
            second = gate_payload(
                grok_bash("git push origin HEAD"),
                home=home,
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("should not ask again")),
            )
            self.assertEqual(second.decision, ALLOW)
            self.assertFalse(second.asked)

    def test_non_pretool_passes(self) -> None:
        with TemporaryDirectory() as tmp:
            result = gate_payload(
                {"hookEventName": "session_start", "cwd": "/tmp"},
                home=Path(tmp),
            )
            self.assertEqual(result.decision, ALLOW)

    def test_never_returns_harness_ask(self) -> None:
        """YOLO harnesses auto-approve a harness `ask`. We must not emit it."""
        with TemporaryDirectory() as tmp:
            save_policy(Path(tmp), ask_policy())
            result = gate_payload(
                grok_bash("sudo true"),
                home=Path(tmp),
                wait_fn=lambda *_: None,
            )
            self.assertNotEqual(result.response["decision"], "ask")
            self.assertEqual(result.response["decision"], "deny")
