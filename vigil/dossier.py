"""Today's black box: counts, files touched, last denied command."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil.paths import audit_path, state_dir
from vigil.secure import redact, redact_path, write_private


def last_denied_path(home: Path) -> Path:
    return state_dir(home) / "last-denied.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def write_last_denied(home: Path, record: dict[str, Any]) -> None:
    row = dict(record)
    if isinstance(row.get("summary"), str):
        row["summary"] = redact(row["summary"])
    if isinstance(row.get("command"), str):
        row["command"] = redact(row["command"])
    if isinstance(row.get("reason"), str):
        row["reason"] = redact(row["reason"])
    if isinstance(row.get("path"), str):
        row["path"] = redact_path(row["path"])
    path = last_denied_path(home)
    write_private(path, json.dumps(row, indent=2) + "\n")


def read_last_denied(home: Path) -> dict[str, Any] | None:
    path = last_denied_path(home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def summarize(home: Path, limit_files: int = 12) -> dict[str, Any]:
    today = _today()
    counts = {"allow": 0, "deny": 0, "ask": 0, "tools": 0}
    files: list[str] = []
    seen_files: set[str] = set()
    path = audit_path(home)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        at = str(row.get("at") or "")
        if not at.startswith(today):
            continue
        counts["tools"] += 1
        event = str(row.get("event") or "")
        if event in counts:
            counts[event] += 1
        if row.get("asked"):
            counts["ask"] += 1
        fpath = row.get("path")
        if isinstance(fpath, str) and fpath and fpath not in seen_files:
            seen_files.add(fpath)
            files.append(fpath)
    return {
        "date": today,
        "counts": counts,
        "files": files[-limit_files:],
        "lastDenied": read_last_denied(home),
    }
