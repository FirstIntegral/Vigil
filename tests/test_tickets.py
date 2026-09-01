from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.call import ToolCall
from vigil.gate import gate_payload
from vigil.pending import write_decision
from vigil.policy import Policy, save_policy
from vigil.risk import ASK, DENY, classify
from vigil.ticket import mcp_server, project_id, ticket_key


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


class TicketKeyTests(unittest.TestCase):
    def test_stable_across_argv(self) -> None:
        a = classify(bash("git push origin HEAD"))
        b = classify(bash("git push origin feature"))
        self.assertEqual(a.class_id, "git-push")
        self.assertEqual(a.rule_key, b.rule_key)
        self.assertTrue(a.rule_key.startswith("t:grok:"))

    def test_mcp_splits_server(self) -> None:
        call = ToolCall(
            event="pre_tool_use",
            tool="mcp",
            raw_tool="github__create_issue",
            command=None,
            path=None,
            cwd="/home/brwsk/projects/vigil",
            workspace="/home/brwsk/projects/vigil",
            session_id="s",
            permission_mode="",
            agent_hint="grok",
            raw_input={},
        )
        risk = classify(call)
        self.assertEqual(risk.class_id, "mcp")
        self.assertEqual(risk.extra, "github")
        self.assertIn(":mcp:github", risk.rule_key)
        self.assertEqual(mcp_server("github__create_issue"), "github")

    def test_project_id_stable(self) -> None:
        self.assertEqual(project_id("/a/vigil"), project_id("/a/vigil/"))
        self.assertNotEqual(project_id("/a/vigil"), project_id("/b/vigil"))


class AlwaysTicketTests(unittest.TestCase):
    def test_always_covers_other_argv_same_class(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)

            def always(h, req_id, timeout_sec, **_kwargs):
                write_decision(h, req_id, "always")
                from vigil.pending import read_decision

                return read_decision(h, req_id)

            save_policy(home, Policy(mode="ask"))
            first = gate_payload(grok_bash("git push origin HEAD"), home=home, wait_fn=always)
            self.assertEqual(first.decision, "allow")
            second = gate_payload(
                grok_bash("git push origin feature"),
                home=home,
                wait_fn=lambda *_: (_ for _ in ()).throw(AssertionError("ticket should match")),
            )
            self.assertEqual(second.decision, "allow")
            self.assertFalse(second.asked)


class DesktopTests(unittest.TestCase):
    def test_hypr_exit_is_deny(self) -> None:
        self.assertEqual(classify(bash("hyprctl dispatch exit")).decision, DENY)
        self.assertEqual(classify(bash("hyprctl dispatch exit")).class_id, "desktop-kill")

    def test_plugin_add_is_deny(self) -> None:
        self.assertEqual(classify(bash("omarchy plugin add git@x --yes")).decision, DENY)
        self.assertEqual(classify(bash("omarchy plugin add git@x --yes")).class_id, "plugin-inject")

    def test_self_approve_is_deny(self) -> None:
        self.assertEqual(classify(bash("vigil decide abc allow")).decision, DENY)
        self.assertEqual(classify(bash("vigil decide abc allow")).class_id, "self-approve")

    def test_power_is_deny(self) -> None:
        self.assertEqual(classify(bash("reboot")).decision, DENY)

    def test_hypr_monitors_is_ask(self) -> None:
        self.assertEqual(classify(bash("hyprctl monitors")).decision, ASK)
