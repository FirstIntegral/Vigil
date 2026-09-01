"""Read Linux /proc into a small dataclass. No agent policy here."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Proc:
    pid: int
    comm: str
    cmdline: tuple[str, ...]
    exe: str | None
    cwd: str | None
    rss_bytes: int
    state: str
    start_time_ticks: int
    uid: int


def parse_stat(stat_text: str) -> tuple[str, str, int] | None:
    """Return (comm, state, start_time_ticks) from /proc/pid/stat.

    comm sits in parentheses and may contain spaces. starttime is field 22
    after the closing paren (field 1 is pid, 2 is comm, 3 is state).
    """
    start = stat_text.find("(")
    end = stat_text.rfind(")")
    if start < 0 or end < 0 or end <= start:
        return None
    comm = stat_text[start + 1 : end]
    rest = stat_text[end + 1 :].split()
    if len(rest) < 20:
        return None
    state = rest[0]
    try:
        start_time = int(rest[19])
    except ValueError:
        return None
    return comm, state, start_time


def parse_status_rss_uid(status_text: str) -> tuple[int, int]:
    """Return (rss_bytes, uid) from /proc/pid/status. Missing fields → 0."""
    rss_kb = 0
    uid = 0
    for line in status_text.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    rss_kb = int(parts[1])
                except ValueError:
                    rss_kb = 0
        elif line.startswith("Uid:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    uid = int(parts[1])
                except ValueError:
                    uid = 0
    return rss_kb * 1024, uid


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeError):
        return None


def _read_cmdline(path: Path) -> tuple[str, ...]:
    try:
        raw = path.read_bytes()
    except OSError:
        return ()
    if not raw:
        return ()
    parts = raw.split(b"\0")
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        out.append(part.decode("utf-8", errors="replace"))
    return tuple(out)


def read_proc(pid_dir: Path) -> Proc | None:
    """Load one /proc/<pid> directory. None if the process vanished."""
    try:
        pid = int(pid_dir.name)
    except ValueError:
        return None
    if pid <= 0:
        return None
    stat_text = _read_text(pid_dir / "stat")
    if stat_text is None:
        return None
    parsed = parse_stat(stat_text)
    if parsed is None:
        return None
    comm, state, start_time = parsed
    status_text = _read_text(pid_dir / "status") or ""
    rss_bytes, uid = parse_status_rss_uid(status_text)
    cmdline = _read_cmdline(pid_dir / "cmdline")
    exe: str | None
    cwd: str | None
    try:
        exe = os.readlink(pid_dir / "exe")
    except OSError:
        exe = None
    try:
        cwd = os.readlink(pid_dir / "cwd")
    except OSError:
        cwd = None
    return Proc(
        pid=pid,
        comm=comm,
        cmdline=cmdline,
        exe=exe,
        cwd=cwd,
        rss_bytes=rss_bytes,
        state=state,
        start_time_ticks=start_time,
        uid=uid,
    )


def iter_procs(proc_root: Path | str = "/proc") -> list[Proc]:
    root = Path(proc_root)
    found: list[Proc] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return found
    for entry in entries:
        name = entry.name
        if not name.isdigit():
            continue
        proc = read_proc(entry)
        if proc is not None:
            found.append(proc)
    return found
