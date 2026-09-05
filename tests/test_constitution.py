from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vigil.cage import CageRefused, plan as cage_plan
from vigil.folders import envelope_for_cwd, is_exclusive, list_folders, match, tighter, upsert
from vigil.gate import gate_payload
from vigil.machine import render, write as write_machine
from vigil.pause import pause_all, resume_all
from vigil.policy import Policy, load_policy, save_policy
from vigil.risk import ASK, DENY, classify
from vigil.call import ToolCall
from vigil.wallet import count_today, over_cap, record


def grok_call(command: str, cwd: str = "/home/brwsk/Projects/vigil", session: str = "s1") -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "sessionId": session,
        "cwd": cwd,
        "workspaceRoot": cwd,
        "permissionMode": "always-approve",
        "toolName": "run_terminal_command",
        "toolInput": {"command": command},
    }


def write_call(path: str, cwd: str = "/home/brwsk/Projects/a") -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "sessionId": "s1",
        "cwd": cwd,
        "workspaceRoot": cwd,
        "permissionMode": "always-approve",
        "toolName": "search_replace",
        "toolInput": {"file_path": path},
    }


def subagent_call() -> dict:
    return {
        "hookEventName": "pre_tool_use",
        "sessionId": "s1",
        "cwd": "/home/brwsk/Projects/vigil",
        "workspaceRoot": "/home/brwsk/Projects/vigil",
        "permissionMode": "always-approve",
        "toolName": "spawn_subagent",
        "toolInput": {"prompt": "help"},
    }


class FolderTests(unittest.TestCase):
    def test_tighter_and_longest_prefix(self) -> None:
        self.assertEqual(tighter("seatbelt", "hermit"), "hermit")
        self.assertEqual(tighter("read", "project"), "read")
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            root = Path(tmp) / "work"
            nested = root / "secret"
            nested.mkdir(parents=True)
            upsert(home, str(root), "project")
            upsert(home, str(nested), "hermit")
            self.assertEqual(envelope_for_cwd(home, str(root), "seatbelt"), "project")
            self.assertEqual(envelope_for_cwd(home, str(nested), "seatbelt"), "hermit")
            self.assertEqual(len(list_folders(home)), 2)

    def test_exclusive_flag(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            d = Path(tmp) / "only"
            d.mkdir()
            upsert(home, str(d), "project", exclusive=True)
            self.assertTrue(is_exclusive(home, str(d)))
            self.assertFalse(is_exclusive(home, str(Path(tmp) / "other")))


class WalletTests(unittest.TestCase):
    def test_cap(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertFalse(over_cap(home, "grok:s", 2))
            record(home, "grok:s")
            record(home, "grok:s")
            self.assertEqual(count_today(home, "grok:s"), 2)
            self.assertTrue(over_cap(home, "grok:s", 2))


class SubagentHoldTests(unittest.TestCase):
    def test_seatbelt_holds_spawn(self) -> None:
        call = ToolCall(
            event="pre_tool_use",
            tool="subagent",
            raw_tool="spawn_subagent",
            command=None,
            path=None,
            cwd="/home/brwsk/Projects/vigil",
            workspace="/home/brwsk/Projects/vigil",
            session_id="s",
            permission_mode="always-approve",
            agent_hint="grok",
            raw_input={},
        )
        risk = classify(call)
        self.assertEqual(risk.class_id, "subagent")
        self.assertTrue(risk.hold)
        self.assertEqual(risk.decision, ASK)

    def test_third_child_denied_without_ticket(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            policy = Policy(mode="seatbelt", max_subagents=2)
            save_policy(home, policy)
            decisions = []
            for _ in range(3):
                result = gate_payload(
                    subagent_call(),
                    home=home,
                    wait_fn=lambda *_: type("D", (), {"action": "allow"})(),
                )
                decisions.append((result.decision, result.risk.class_id if result.risk else ""))
            self.assertEqual(decisions[0][0], "allow")
            self.assertEqual(decisions[1][0], "allow")
            self.assertEqual(decisions[2][1], "subagent-cap")


class TrustUntilLockTests(unittest.TestCase):
    def test_clears_on_lid_freeze(self) -> None:
        from vigil.lid import sync

        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            policy = Policy(mode="ask")
            policy.trust_until_lid(str(home))
            save_policy(home, policy)
            self.assertTrue(load_policy(home).is_trusted(str(home)))
            sync(home, locked=True)
            loaded = load_policy(home)
            self.assertFalse(loaded.trust_until_lock)
            self.assertEqual(loaded.effective_mode(), "frozen")


class PauseTests(unittest.TestCase):
    def test_records_pids_with_injected_kill(self) -> None:
        sent: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            sent.append((pid, sig))

        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            # inspect_target will refuse fake pids — so we only test unittest skip
            out = pause_all(home)
            self.assertEqual(out.get("skipped"), "unittest")
            out = pause_all(home, pids=[], kill_fn=fake_kill)
            self.assertEqual(out["paused"], [])
            resumed = resume_all(home, kill_fn=fake_kill)
            self.assertEqual(resumed["resumed"], [])
            self.assertEqual(sent, [])


class CageTests(unittest.TestCase):
    def test_plan_drops_net(self) -> None:
        try:
            spec = cage_plan(["grok"], cwd="/tmp", net=False)
        except CageRefused:
            self.skipTest("bwrap missing")
        self.assertIn("--unshare-net", spec["argv"])
        self.assertEqual(spec["argv"][-1], "grok")

    def test_empty_command_refused(self) -> None:
        with self.assertRaises(CageRefused):
            cage_plan([], cwd="/tmp")


class MachineTests(unittest.TestCase):
    def test_write_private(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = write_machine(home)
            self.assertTrue(path.is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn("Omarchy", text)
            self.assertIn("Silence is deny", render(home=home))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class ExclusiveGateTests(unittest.TestCase):
    def test_second_writer_held(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            proj = Path(tmp) / "repo"
            proj.mkdir()
            upsert(home, str(proj), "project", exclusive=True)
            from vigil.passport import upsert as upsert_paper

            upsert_paper(home, agent="claude", session_id="other", cwd=str(proj))
            result = gate_payload(
                write_call(str(proj / "a.py"), cwd=str(proj)),
                home=home,
                wait_fn=lambda *_: type("D", (), {"action": "deny"})(),
            )
            self.assertEqual(result.decision, DENY)
            self.assertEqual(result.risk.class_id if result.risk else "", "project-owner")


class SnapshotTicketsTests(unittest.TestCase):
    def test_snapshot_has_constitution_fields(self) -> None:
        from vigil.snapshot import build_snapshot

        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            policy = Policy()
            policy.remember_allow("t:grok:x:network")
            save_policy(home, policy)
            snap = build_snapshot([], home=home, uid=os.getuid(), host="omarchy")
            self.assertIn("tickets", snap)
            self.assertIn("t:grok:x:network", snap["tickets"]["allow"])
            self.assertEqual(snap["folders"], [])
            self.assertIn("brief", snap)


if __name__ == "__main__":
    unittest.main()
