"""Append-only JSONL audit. Local only."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil.paths import audit_path


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(home: Path, record: dict[str, Any]) -> None:
    path = audit_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(record)
    row.setdefault("at", _now())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")


def tail(home: Path, limit: int = 50) -> list[dict[str, Any]]:
    path = audit_path(home)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in text.splitlines()[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows
