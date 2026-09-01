"""Is the process asking Vigil an agent? Agents may not mint their own tickets."""

from __future__ import annotations

import os
from pathlib import Path

from vigil.classify import classify
from vigil.proc import read_proc


def ppid_of(pid: int) -> int:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    end = text.rfind(")")
    rest = text[end + 1 :].split()
    if len(rest) < 2:
        return 0
    try:
        return int(rest[1])
    except ValueError:
        return 0


def caller_is_agent(start_pid: int | None = None) -> bool:
    pid = int(start_pid or os.getpid())
    seen: set[int] = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        proc = read_proc(Path("/proc") / str(pid))
        if proc is not None and classify(proc) is not None:
            return True
        pid = ppid_of(pid)
    return False
