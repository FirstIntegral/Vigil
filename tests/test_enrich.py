from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.classify import classify
from vigil.enrich import claude_project_dir_name, enrich, grok_model_from_config
from vigil.proc import Proc


def grok_proc(pid: int = 10931) -> Proc:
    return Proc(
        pid=pid,
        comm="grok",
        cmdline=("grok",),
        exe="/home/brwsk/.local/bin/grok",
        cwd="/home/brwsk",
        rss_bytes=1,
        state="S",
        start_time_ticks=1,
        uid=1000,
    )


class EnrichTests(unittest.TestCase):
    def test_claude_project_dir_name(self) -> None:
        self.assertEqual(claude_project_dir_name("/home/brwsk"), "-home-brwsk")
        self.assertEqual(
            claude_project_dir_name("/home/brwsk/projects/vigil"),
            "-home-brwsk-projects-vigil",
        )

    def test_grok_model_from_config(self) -> None:
        toml = '[ui]\npermission_mode = "always-approve"\n\n[models]\ndefault = "grok-4.6"\n'
        self.assertEqual(grok_model_from_config(toml), "grok-4.6")

    def test_enrich_grok_from_active_sessions(self) -> None:
        match = classify(grok_proc())
        assert match is not None
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            grok_dir = home / ".grok"
            grok_dir.mkdir()
            (grok_dir / "active_sessions.json").write_text(
                json.dumps(
                    [
                        {
                            "session_id": "abc-123",
                            "pid": 10931,
                            "cwd": "/home/brwsk/projects/vigil",
                            "opened_at": "2026-09-01T20:12:33Z",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (grok_dir / "config.toml").write_text(
                '[models]\ndefault = "grok-4.6"\n', encoding="utf-8"
            )
            out = enrich(match, home)
            self.assertEqual(out.session_id, "abc-123")
            self.assertEqual(out.opened_at, "2026-09-01T20:12:33Z")
            self.assertEqual(out.model, "grok-4.6")
            self.assertEqual(out.project, "vigil")

    def test_enrich_claude_from_jsonl(self) -> None:
        proc = Proc(
            pid=21351,
            comm="claude",
            cmdline=("claude",),
            exe=None,
            cwd="/home/brwsk",
            rss_bytes=1,
            state="S",
            start_time_ticks=1,
            uid=1000,
        )
        match = classify(proc)
        assert match is not None
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            project = home / ".claude" / "projects" / "-home-brwsk"
            project.mkdir(parents=True)
            (project / "sess.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps({"type": "user", "sessionId": "sid-1", "cwd": "/home/brwsk"}),
                        json.dumps(
                            {
                                "type": "assistant",
                                "sessionId": "sid-1",
                                "model": "claude-opus-4-6",
                                "gitBranch": "main",
                                "timestamp": "2026-09-01T20:05:41.660Z",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            out = enrich(match, home)
            self.assertEqual(out.session_id, "sid-1")
            self.assertEqual(out.model, "claude-opus-4-6")
            self.assertEqual(out.git_branch, "main")
            self.assertEqual(out.project, "brwsk")


if __name__ == "__main__":
    unittest.main()
