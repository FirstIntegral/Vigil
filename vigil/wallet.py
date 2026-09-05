"""Subagent child counts. Empty wallet: children do not mint Always tickets.

Always tickets are agent×project×class, so a child that shares the parent
agent still matches them. The hold is on *spawning* the child (seatbelt
card) plus a per-parent daily cap. Documented limit, not a kernel jail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil.paths import children_path
from vigil.secure import write_private

DEFAULT_MAX_CHILDREN = 2


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load(home: Path) -> dict[str, Any]:
    try:
        data = json.loads(children_path(home).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _save(home: Path, data: dict[str, Any]) -> None:
    write_private(children_path(home), json.dumps(data, indent=2) + "\n")


def count_today(home: Path, parent_id: str) -> int:
    data = _load(home)
    day = data.get(_today())
    if not isinstance(day, dict):
        return 0
    try:
        return int(day.get(parent_id) or 0)
    except (TypeError, ValueError):
        return 0


def record(home: Path, parent_id: str) -> int:
    data = _load(home)
    today = _today()
    # Drop other days so the file stays tiny.
    day = data.get(today)
    if not isinstance(day, dict):
        day = {}
    n = 0
    try:
        n = int(day.get(parent_id) or 0)
    except (TypeError, ValueError):
        n = 0
    n += 1
    day[parent_id] = n
    _save(home, {today: day})
    return n


def over_cap(home: Path, parent_id: str, cap: int = DEFAULT_MAX_CHILDREN) -> bool:
    if cap <= 0:
        return False
    return count_today(home, parent_id) >= cap
