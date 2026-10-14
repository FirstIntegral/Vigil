"""GitHub fast-forward check. Uses a local origin so the test stays offline."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vigil.call import ToolCall
from vigil.cli import main
from vigil.repo_update import UPDATE_ARGV, apply_update, inspect
from vigil.risk import classify


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Vigil Test",
            "GIT_AUTHOR_EMAIL": "vigil-test@example.com",
            "GIT_COMMITTER_NAME": "Vigil Test",
            "GIT_COMMITTER_EMAIL": "vigil-test@example.com",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "commit.gpgsign",
            "GIT_CONFIG_VALUE_0": "false",
        }
    )
    return env


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, env=_env(), capture_output=True)


def _commit(cwd: Path, name: str, body: str) -> None:
    path = cwd / name
    path.write_text(body, encoding="utf-8")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-m", body)


def _pair() -> tuple[TemporaryDirectory[str], Path, Path]:
    tmp = TemporaryDirectory()
    root = Path(tmp.name)
    origin = root / "origin.git"
    clone = root / "clone"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    seed = root / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _commit(seed, "manifest.json", "one\n")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-u", "origin", "main")
    subprocess.run(
        ["git", "clone", str(origin), str(clone)],
        check=True,
        capture_output=True,
        env=_env(),
    )
    return tmp, origin, clone


def bash(command: str) -> ToolCall:
    cwd = "/tmp"
    return ToolCall(
        event="pre_tool_use",
        tool="bash",
        raw_tool="run_terminal_command",
        command=command,
        path=None,
        cwd=cwd,
        workspace=cwd,
        session_id="s",
        permission_mode="always-approve",
        agent_hint="grok",
        raw_input={"command": command},
    )


class RepoUpdateTests(unittest.TestCase):
    def test_current_behind_ahead_diverged_and_dirty(self) -> None:
        tmp, origin, clone = _pair()
        self.addCleanup(tmp.cleanup)
        current = inspect(clone)
        self.assertEqual(current["state"], "current")
        self.assertFalse(current["dirty"])

        seed = Path(tmp.name) / "seed"
        _commit(seed, "manifest.json", "two\n")
        _git(seed, "push", "origin", "main")
        behind = inspect(clone)
        self.assertEqual(behind["state"], "behind")
        self.assertEqual(behind["behind"], 1)
        self.assertFalse(behind["dirty"])

        (clone / "manifest.json").write_text("local\n", encoding="utf-8")
        dirty = inspect(clone)
        self.assertEqual(dirty["state"], "behind")
        self.assertTrue(dirty["dirty"])

        _git(clone, "checkout", "--", "manifest.json")
        _git(clone, "merge", "--ff-only", "FETCH_HEAD")
        _commit(clone, "local.txt", "mine\n")
        self.assertEqual(inspect(clone)["state"], "ahead")

        _git(clone, "reset", "--hard", "HEAD~2")
        _commit(clone, "other.txt", "side\n")
        self.assertEqual(inspect(clone)["state"], "diverged")

    def test_missing_origin_is_offline(self) -> None:
        tmp, _origin, clone = _pair()
        self.addCleanup(tmp.cleanup)
        _git(clone, "remote", "set-url", "origin", str(Path(tmp.name) / "no-such.git"))
        report = inspect(clone)
        self.assertEqual(report["state"], "offline")
        self.assertFalse(report["ok"])

    def test_not_a_checkout(self) -> None:
        with TemporaryDirectory() as raw:
            report = inspect(Path(raw))
        self.assertEqual(report["state"], "notgit")

    def test_apply_calls_omarchy_only_when_behind_and_clean(self) -> None:
        tmp, _origin, clone = _pair()
        self.addCleanup(tmp.cleanup)
        calls: list[list[str]] = []

        def runner(argv: list[str]):
            calls.append(argv)

            class Result:
                returncode = 0
                stdout = "Updated.\n"
                stderr = ""

            return Result()

        refused = apply_update(clone, runner=runner)
        self.assertFalse(refused["ok"])
        self.assertEqual(calls, [])

        seed = Path(tmp.name) / "seed"
        _commit(seed, "manifest.json", "two\n")
        _git(seed, "push", "origin", "main")
        (clone / "manifest.json").write_text("dirty\n", encoding="utf-8")
        blocked = apply_update(clone, runner=runner)
        self.assertFalse(blocked["ok"])
        self.assertTrue(blocked["dirty"])
        self.assertEqual(calls, [])

        _git(clone, "checkout", "--", "manifest.json")
        applied = apply_update(clone, runner=runner)
        self.assertTrue(applied["ok"])
        self.assertEqual(calls, [UPDATE_ARGV])

    def test_agent_cannot_apply(self) -> None:
        out = StringIO()
        with patch("vigil.cli.caller_is_agent", return_value=True), patch("sys.stdout", out):
            rc = main(["update-apply"])
        self.assertEqual(rc, 2)
        self.assertIn("agent", out.getvalue().lower())

    def test_check_cli_json(self) -> None:
        tmp, _origin, clone = _pair()
        self.addCleanup(tmp.cleanup)
        out = StringIO()
        with patch("sys.stdout", out):
            rc = main(["update-check", "--root", str(clone)])
        self.assertEqual(rc, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["state"], "current")

    def test_update_apply_is_self_approve(self) -> None:
        self.assertEqual(classify(bash("vigil update-apply")).class_id, "self-approve")
