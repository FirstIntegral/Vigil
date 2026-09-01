"""Advisory file leases. Same passport rewrite is silent. Other passport → card."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil.paths import claims_path
from vigil.secure import ensure_private_dir, write_private


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(home: Path) -> dict[str, Any]:
    path = claims_path(home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(home: Path, data: dict[str, Any]) -> None:
    ensure_private_dir(claims_path(home).parent)
    write_private(claims_path(home), json.dumps(data, indent=2) + "\n")


def normalize_path(path: str) -> str:
    return str(Path(path).expanduser()) if path else ""


def conflict(home: Path, path: str, passport_id: str) -> dict[str, Any] | None:
    if not path or not passport_id:
        return None
    key = normalize_path(path)
    data = _load(home)
    row = data.get(key)
    if not isinstance(row, dict):
        return None
    holder = str(row.get("passportId") or "")
    if not holder or holder == passport_id:
        return None
    return row


def claim(home: Path, path: str, passport_id: str, agent: str = "") -> dict[str, Any]:
    key = normalize_path(path)
    data = _load(home)
    row = {"passportId": passport_id, "agent": agent, "path": key, "at": _now()}
    data[key] = row
    _save(home, data)
    return row


def drop_passport(home: Path, passport_id: str) -> None:
    data = _load(home)
    nxt = {k: v for k, v in data.items() if not (isinstance(v, dict) and v.get("passportId") == passport_id)}
    _save(home, nxt)


def drop_dead(home: Path, live_ids: set[str]) -> None:
    data = _load(home)
    nxt = {
        k: v
        for k, v in data.items()
        if isinstance(v, dict) and str(v.get("passportId") or "") in live_ids
    }
    if len(nxt) != len(data):
        _save(home, nxt)


def count_for(home: Path, passport_id: str) -> int:
    data = _load(home)
    return sum(
        1
        for v in data.values()
        if isinstance(v, dict) and v.get("passportId") == passport_id
    )
