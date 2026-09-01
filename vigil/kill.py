"""Kill only processes that still classify as coding agents."""

from __future__ import annotations

import os
import signal
from dataclasses import dataclass
from pathlib import Path

from vigil.agents import PROTECTED_COMMS
from vigil.classify import classify
from vigil.proc import read_proc

# Signals we will send. Nothing else — no SIGSTOP games, no pkill patterns.
ALLOWED_SIGNALS = {
    "term": signal.SIGTERM,
    "kill": signal.SIGKILL,
}


class KillRefused(Exception):
    """The pid is not a live coding agent we are willing to signal."""


@dataclass(frozen=True)
class KillResult:
    pid: int
    agent: str
    signal: str
    comm: str


def _signal_name(value: str | int) -> tuple[str, int]:
    if isinstance(value, int):
        for name, num in ALLOWED_SIGNALS.items():
            if num == value:
                return name, num
        raise KillRefused(f"signal {value} is not allowed")
    key = str(value).lower()
    if key in {"term", "sigterm", "15"}:
        key = "term"
    elif key in {"kill", "sigkill", "9"}:
        key = "kill"
    if key not in ALLOWED_SIGNALS:
        raise KillRefused(f"signal {value!r} is not allowed")
    return key, ALLOWED_SIGNALS[key]


def inspect_target(pid: int, proc_root: Path | str = "/proc") -> KillResult:
    """Re-read /proc and refuse anything that is not a current agent."""
    if pid <= 1:
        raise KillRefused("refusing pid <= 1")
    proc = read_proc(Path(proc_root) / str(pid))
    if proc is None:
        raise KillRefused(f"pid {pid} is gone")
    if proc.comm in PROTECTED_COMMS:
        raise KillRefused(f"refusing protected process {proc.comm!r}")
    match = classify(proc)
    if match is None:
        raise KillRefused(
            f"pid {pid} ({proc.comm!r}) is not a known coding agent"
        )
    if proc.uid != os.getuid():
        raise KillRefused("refusing to signal another user's process")
    return KillResult(pid=pid, agent=match.spec.id, signal="term", comm=proc.comm)


def kill_agent(
    pid: int,
    *,
    proc_root: Path | str = "/proc",
    sig: str | int = "term",
    kill_fn=None,
) -> KillResult:
    """Signal one agent. Re-classifies at kill time to close TOCTOU."""
    name, number = _signal_name(sig)
    inspected = inspect_target(pid, proc_root)
    sender = kill_fn if kill_fn is not None else os.kill
    try:
        sender(pid, number)
    except ProcessLookupError as exc:
        raise KillRefused(f"pid {pid} vanished before signal") from exc
    except PermissionError as exc:
        raise KillRefused(f"permission denied signalling pid {pid}") from exc
    return KillResult(
        pid=inspected.pid,
        agent=inspected.agent,
        signal=name,
        comm=inspected.comm,
    )
