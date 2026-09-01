from __future__ import annotations

import os
import signal
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.kill import KillRefused, inspect_target, kill_agent
from vigil.proc import Proc


def write_fake_proc(
    root: Path,
    proc: Proc,
) -> Path:
    pid_dir = root / str(proc.pid)
    pid_dir.mkdir(parents=True)
    # /proc/pid/stat: pid (comm) state ... starttime as field 22
    after = [proc.state] + ["0"] * 18 + [str(proc.start_time_ticks)]
    (pid_dir / "stat").write_text(
        f"{proc.pid} ({proc.comm}) " + " ".join(after) + "\n", encoding="utf-8"
    )
    rss_kb = proc.rss_bytes // 1024
    (pid_dir / "status").write_text(
        f"Name:\t{proc.comm}\nUid:\t{proc.uid}\t{proc.uid}\t{proc.uid}\t{proc.uid}\nVmRSS:\t{rss_kb} kB\n",
        encoding="utf-8",
    )
    raw = b"\0".join(a.encode() for a in proc.cmdline) + b"\0"
    (pid_dir / "cmdline").write_bytes(raw)
    if proc.exe:
        (pid_dir / "exe").symlink_to(proc.exe)
    if proc.cwd:
        cwd_target = Path(proc.cwd)
        cwd_target.mkdir(parents=True, exist_ok=True)
        (pid_dir / "cwd").symlink_to(proc.cwd)
    return pid_dir


class KillTests(unittest.TestCase):
    def test_refuses_pid_one(self) -> None:
        with self.assertRaises(KillRefused):
            inspect_target(1)

    def test_refuses_non_agent(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fake_proc(
                root,
                Proc(
                    pid=42,
                    comm="bash",
                    cmdline=("bash",),
                    exe="/bin/bash",
                    cwd=tmp,
                    rss_bytes=1024,
                    state="S",
                    start_time_ticks=1,
                    uid=os.getuid(),
                ),
            )
            with self.assertRaises(KillRefused) as ctx:
                inspect_target(42, proc_root=root)
            self.assertIn("not a known coding agent", str(ctx.exception))

    def test_refuses_protected_comm(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fake_proc(
                root,
                Proc(
                    pid=7,
                    comm="hyprland",
                    cmdline=("Hyprland",),
                    exe="/usr/bin/Hyprland",
                    cwd=tmp,
                    rss_bytes=1024,
                    state="S",
                    start_time_ticks=1,
                    uid=os.getuid(),
                ),
            )
            with self.assertRaises(KillRefused) as ctx:
                inspect_target(7, proc_root=root)
            self.assertIn("protected", str(ctx.exception))

    def test_kills_classified_agent_via_injected_fn(self) -> None:
        sent: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            sent.append((pid, sig))

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_fake_proc(
                root,
                Proc(
                    pid=10931,
                    comm="grok",
                    cmdline=("grok",),
                    exe="/usr/bin/grok",
                    cwd=tmp,
                    rss_bytes=1024,
                    state="S",
                    start_time_ticks=1,
                    uid=os.getuid(),
                ),
            )
            result = kill_agent(10931, proc_root=root, kill_fn=fake_kill)
            self.assertEqual(result.agent, "grok")
            self.assertEqual(result.signal, "term")
            self.assertEqual(sent, [(10931, signal.SIGTERM)])

    def test_refuses_unknown_signal(self) -> None:
        with self.assertRaises(KillRefused):
            kill_agent(10931, sig="hup", kill_fn=lambda *_: None)


if __name__ == "__main__":
    unittest.main()
