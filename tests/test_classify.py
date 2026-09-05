from __future__ import annotations

import unittest

from vigil.classify import classify, discover
from vigil.proc import Proc


def proc(
    pid: int,
    comm: str,
    *,
    cmdline: tuple[str, ...] = (),
    exe: str | None = None,
    cwd: str | None = "/home/brwsk/Projects/vigil",
    uid: int = 1000,
    state: str = "S",
) -> Proc:
    if not cmdline:
        cmdline = (comm,)
    return Proc(
        pid=pid,
        comm=comm,
        cmdline=cmdline,
        exe=exe,
        cwd=cwd,
        rss_bytes=10_000_000,
        state=state,
        start_time_ticks=1,
        uid=uid,
    )


class ClassifyTests(unittest.TestCase):
    def test_grok_binary(self) -> None:
        match = classify(proc(10931, "grok", exe="/home/brwsk/.local/bin/grok"))
        assert match is not None
        self.assertEqual(match.spec.id, "grok")
        self.assertEqual(match.matched_bin, "grok")
        self.assertEqual(match.status, "running")

    def test_claude_binary(self) -> None:
        match = classify(proc(21351, "claude"))
        assert match is not None
        self.assertEqual(match.spec.display, "Claude Code")

    def test_pgrep_is_not_an_agent(self) -> None:
        self.assertIsNone(
            classify(
                proc(
                    99,
                    "pgrep",
                    cmdline=("pgrep", "-af", "claude"),
                )
            )
        )

    def test_bash_wrapper_is_not_an_agent(self) -> None:
        self.assertIsNone(
            classify(
                proc(
                    32591,
                    "bash",
                    cmdline=("bash", "-c", "export GROK_AGENT=1; python3 foo"),
                )
            )
        )

    def test_systemd_inhibit_is_not_an_agent(self) -> None:
        self.assertIsNone(
            classify(
                proc(
                    31996,
                    "systemd-inhibit",
                    cmdline=(
                        "systemd-inhibit",
                        "--who=grok",
                        "--why=agent turn in progress",
                        "sleep",
                        "infinity",
                    ),
                )
            )
        )

    def test_pid_one_refused(self) -> None:
        self.assertIsNone(classify(proc(1, "grok")))

    def test_python_running_vigil_is_not_an_agent(self) -> None:
        self.assertIsNone(
            classify(
                proc(
                    50,
                    "python3",
                    cmdline=("python3", "/home/brwsk/Projects/vigil/bin/vigil", "snapshot"),
                    exe="/usr/bin/python3",
                )
            )
        )

    def test_later_argv_mention_does_not_match(self) -> None:
        self.assertIsNone(
            classify(
                proc(
                    8,
                    "ps",
                    cmdline=("ps", "aux"),
                )
            )
        )

    def test_discover_filters_uid(self) -> None:
        procs = [
            proc(10, "grok", uid=1000),
            proc(11, "claude", uid=0),
        ]
        matches = discover(procs, uid=1000)
        self.assertEqual([m.proc.pid for m in matches], [10])


if __name__ == "__main__":
    unittest.main()
