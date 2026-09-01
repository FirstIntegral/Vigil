"""Agent papers. Pid death does not erase the name."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil.envelope import DEFAULT_ENVELOPE, ENVELOPES, normalize
from vigil.paths import passports_dir
from vigil.secure import ensure_private_dir, write_private
from vigil.ticket import project_id


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_id(agent: str, session_id: str = "", pid: int | None = None) -> str:
    agent = (agent or "agent").replace(":", "_")
    if session_id:
        return f"{agent}:{session_id}"
    if pid:
        return f"{agent}:pid:{pid}"
    return f"{agent}:anon"


def path_for(home: Path, passport_id: str) -> Path:
    safe = passport_id.replace("/", "_")
    return passports_dir(home) / f"{safe}.json"


def load(home: Path, passport_id: str) -> dict[str, Any] | None:
    path = path_for(home, passport_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save(home: Path, row: dict[str, Any]) -> dict[str, Any]:
    pid = str(row.get("id") or "")
    if not pid:
        raise ValueError("passport id required")
    ensure_private_dir(passports_dir(home))
    write_private(path_for(home, pid), json.dumps(row, indent=2) + "\n")
    return row


def upsert(
    home: Path,
    *,
    agent: str,
    session_id: str = "",
    pid: int | None = None,
    cwd: str = "",
    model: str = "",
    host: str = "",
    envelope: str | None = None,
) -> dict[str, Any]:
    pid_key = make_id(agent, session_id, pid)
    existing = load(home, pid_key) or {}
    root = cwd.rstrip("/")
    row = {
        "id": pid_key,
        "agent": agent,
        "pid": pid if pid is not None else existing.get("pid"),
        "sessionId": session_id or existing.get("sessionId") or "",
        "project": project_id(root),
        "projectRoot": root,
        "envelope": normalize(
            envelope if envelope is not None else str(existing.get("envelope") or DEFAULT_ENVELOPE)
        ),
        "model": model or existing.get("model") or "",
        "status": "running",
        "parent": existing.get("parent") or "",
        "startedAt": existing.get("startedAt") or _now(),
        "host": host or existing.get("host") or "",
        "updatedAt": _now(),
    }
    return save(home, row)


def set_envelope(home: Path, passport_id: str, envelope: str) -> dict[str, Any]:
    env = normalize(envelope)
    row = load(home, passport_id) or {"id": passport_id, "agent": passport_id.split(":")[0]}
    row["envelope"] = env
    row["updatedAt"] = _now()
    return save(home, row)


def envelope_for(home: Path, *, agent: str, session_id: str, cwd: str) -> str:
    for candidate in (
        make_id(agent, session_id, None),
    ):
        row = load(home, candidate)
        if row:
            return normalize(str(row.get("envelope") or DEFAULT_ENVELOPE))
    want = project_id(cwd)
    folder = passports_dir(home)
    if not folder.is_dir():
        return DEFAULT_ENVELOPE
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if str(data.get("agent") or "") != agent:
            continue
        if str(data.get("project") or "") == want or str(data.get("projectRoot") or "").rstrip("/") == cwd.rstrip("/"):
            return normalize(str(data.get("envelope") or DEFAULT_ENVELOPE))
    return DEFAULT_ENVELOPE


def list_passports(home: Path) -> list[dict[str, Any]]:
    folder = passports_dir(home)
    if not folder.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("id"):
            rows.append(data)
    return rows


def reap(home: Path, live_pids: set[int]) -> None:
    """Mark passports whose pid is gone. Keep  the file; status=dead."""
    now = _now()
    for row in list_passports(home):
        pid = row.get("pid")
        try:
            n = int(pid) if pid is not None else 0
        except (TypeError, ValueError):
            n = 0
        if n and n not in live_pids and row.get("status") != "dead":
            row["status"] = "dead"
            row["updatedAt"] = now
            try:
                save(home, row)
            except ValueError:
                continue


def cycle_envelope(home: Path, passport_id: str) -> dict[str, Any]:
    row = load(home, passport_id) or {"id": passport_id, "envelope": DEFAULT_ENVELOPE}
    cur = normalize(str(row.get("envelope") or DEFAULT_ENVELOPE))
    nxt = ENVELOPES[(ENVELOPES.index(cur) + 1) % len(ENVELOPES)]
    return set_envelope(home, passport_id, nxt)
