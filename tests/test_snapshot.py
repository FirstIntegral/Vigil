from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil import PLUGIN_ID, SNAPSHOT_SCHEMA
from vigil.proc import Proc
from vigil.snapshot import build_snapshot, dumps


class SnapshotTests(unittest.TestCase):
    def test_empty(self) -> None:
        snap = build_snapshot(
            [],
            home=Path("/tmp"),
            uid=1000,
            host="xigmatic",
            generated_at="2026-09-01T00:00:00Z",
        )
        self.assertEqual(snap["schemaVersion"], SNAPSHOT_SCHEMA)
        self.assertEqual(snap["pluginId"], PLUGIN_ID)
        self.assertEqual(snap["sessions"], [])
        self.assertEqual(snap["totals"]["agents"], 0)
        self.assertIsNone(snap["totals"]["todayUsd"])

    def test_two_agents(self) -> None:
        uid = os.getuid()
        procs = [
            Proc(
                pid=10931,
                comm="grok",
                cmdline=("grok",),
                exe="/usr/bin/grok",
                cwd="/home/brwsk/Projects/Vigil",
                rss_bytes=50_000_000,
                state="S",
                start_time_ticks=1,
                uid=uid,
            ),
            Proc(
                pid=21351,
                comm="claude",
                cmdline=("claude",),
                exe="/usr/bin/claude",
                cwd="/home/brwsk",
                rss_bytes=80_000_000,
                state="R",
                start_time_ticks=2,
                uid=uid,
            ),
        ]
        with TemporaryDirectory() as tmp:
            snap = build_snapshot(
                procs,
                home=Path(tmp),
                uid=uid,
                host="xigmatic",
                generated_at="2026-09-01T00:00:00Z",
            )
        ids = [s["id"] for s in snap["sessions"]]
        self.assertEqual(ids, ["claude:21351", "grok:10931"])
        self.assertEqual(snap["totals"]["running"], 2)
        grok = next(s for s in snap["sessions"] if s["agent"] == "grok")
        self.assertEqual(grok["project"], "Vigil")
        self.assertTrue(grok["killable"])

    def test_dumps_is_one_json_object(self) -> None:
        snap = build_snapshot(
            [],
            home=Path("/tmp"),
            uid=1,
            host="h",
            generated_at="2026-09-01T00:00:00Z",
        )
        parsed = json.loads(dumps(snap))
        self.assertEqual(parsed["host"], "h")


if __name__ == "__main__":
    unittest.main()
