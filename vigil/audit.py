"""Append-only JSONL audit. Local only. Hash-chained. Secrets redacted."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil.paths import audit_path
from vigil.secure import chain_row, last_hash, redact, redact_path, ensure_private_dir


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append(home: Path, record: dict[str, Any]) -> None:
    path = audit_path(home)
    ensure_private_dir(path.parent)
    row = dict(record)
    row.setdefault("at", _now())
    if "summary" in row and isinstance(row["summary"], str):
        row["summary"] = redact(row["summary"])
    if "command" in row and isinstance(row["command"], str):
        row["command"] = redact(row["command"])
    if "path" in row and isinstance(row["path"], str):
        row["path"] = redact_path(row["path"])
    row = chain_row(row, last_hash(path))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, separators=(",", ":")) + "\n")
    try:
        import os

        os.chmod(path, 0o600)
    except OSError:
        pass


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
