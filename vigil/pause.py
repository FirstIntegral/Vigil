"""SIGSTOP / SIGCONT classified agents. Same inspect as kill. Not a jail."""

from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from typing import Any, Callable

from vigil.kill import KillRefused, inspect_target
from vigil.paths import paused_path
from vigil.secure import write_private

STOP = signal.SIGSTOP
CONT = signal.SIGCONT


def _load_pids(home: Path) -> list[int]:
    try:
        data = json.loads(paused_path(home).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    rows = data.get("pids") or []
    out: list[int] = []
    for item in rows:
        try:
            n = int(item)
        except (TypeError, ValueError):
            continue
        if n > 1:
            out.append(n)
    return out


def _save_pids(home: Path, pids: list[int]) -> None:
    write_private(paused_path(home), json.dumps({"pids": sorted(set(pids))}) + "\n")


def _live_agent_pids(proc_root: Path | str = "/proc") -> list[int]:
    from vigil.classify import discover
    from vigil.proc import iter_procs

    uid = os.getuid()
    return [m.proc.pid for m in discover(iter_procs(proc_root), uid=uid)]


def pause_pid(
    pid: int,
    *,
    proc_root: Path | str = "/proc",
    kill_fn: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    inspected = inspect_target(pid, proc_root)
    sender = kill_fn if kill_fn is not None else os.kill
    try:
        sender(pid, STOP)
    except ProcessLookupError as exc:
        raise KillRefused(f"pid {pid} vanished before stop") from exc
    except PermissionError as exc:
        raise KillRefused(f"permission denied stopping pid {pid}") from exc
    return {"ok": True, "pid": inspected.pid, "agent": inspected.agent, "signal": "stop"}


def resume_pid(
    pid: int,
    *,
    proc_root: Path | str = "/proc",
    kill_fn: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    inspected = inspect_target(pid, proc_root)
    sender = kill_fn if kill_fn is not None else os.kill
    try:
        sender(pid, CONT)
    except ProcessLookupError as exc:
        raise KillRefused(f"pid {pid} vanished before continue") from exc
    except PermissionError as exc:
        raise KillRefused(f"permission denied continuing pid {pid}") from exc
    return {"ok": True, "pid": inspected.pid, "agent": inspected.agent, "signal": "cont"}


def pause_all(
    home: Path,
    *,
    pids: list[int] | None = None,
    proc_root: Path | str = "/proc",
    kill_fn: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Stop every classified agent. Tests must pass pids or kill_fn. Never in unittest by accident."""
    if pids is None:
        if "unittest" in sys.modules and kill_fn is None:
            return {"ok": True, "paused": [], "skipped": "unittest"}
        pids = _live_agent_pids(proc_root)
    paused: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    kept = _load_pids(home)
    for pid in pids:
        try:
            row = pause_pid(pid, proc_root=proc_root, kill_fn=kill_fn)
        except KillRefused as exc:
            errors.append({"pid": pid, "error": str(exc)})
            continue
        paused.append(row)
        kept.append(int(row["pid"]))
    _save_pids(home, kept)
    return {"ok": not errors, "paused": paused, "errors": errors}


def resume_all(
    home: Path,
    *,
    proc_root: Path | str = "/proc",
    kill_fn: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    if "unittest" in sys.modules and kill_fn is None:
        _save_pids(home, [])
        return {"ok": True, "resumed": [], "skipped": "unittest"}
    resumed: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for pid in _load_pids(home):
        try:
            row = resume_pid(pid, proc_root=proc_root, kill_fn=kill_fn)
        except KillRefused as exc:
            errors.append({"pid": pid, "error": str(exc)})
            continue
        resumed.append(row)
    _save_pids(home, [])
    return {"ok": not errors, "resumed": resumed, "errors": errors}
