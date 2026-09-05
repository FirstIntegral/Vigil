"""Per-folder leases. Human-owned. Agents cannot write this file."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vigil.envelope import ENVELOPES, normalize
from vigil.paths import folders_path
from vigil.risk import path_inside
from vigil.secure import write_private

SCHEMA = 1
TIGHTNESS = ("seatbelt", "desktop", "project", "hermit", "read")


def _empty() -> dict[str, Any]:
    return {"schemaVersion": SCHEMA, "folders": []}


def load(home: Path) -> dict[str, Any]:
    path = folders_path(home)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    rows = data.get("folders")
    if not isinstance(rows, list):
        data["folders"] = []
    return data


def save(home: Path, data: dict[str, Any]) -> None:
    payload = {
        "schemaVersion": SCHEMA,
        "folders": list(data.get("folders") or []),
    }
    write_private(folders_path(home), json.dumps(payload, indent=2) + "\n")


def _resolve(path: str) -> str:
    raw = (path or "").strip()
    if not raw:
        return ""
    try:
        return str(Path(raw).expanduser().resolve())
    except (OSError, RuntimeError):
        return str(Path(raw).expanduser())


def tighter(a: str, b: str) -> str:
    left = normalize(a)
    right = normalize(b)
    ia = TIGHTNESS.index(left) if left in TIGHTNESS else 0
    ib = TIGHTNESS.index(right) if right in TIGHTNESS else 0
    return right if ib > ia else left


def match(home: Path, cwd: str) -> dict[str, Any] | None:
    """Longest resolved prefix. No match → None."""
    want = _resolve(cwd)
    if not want:
        return None
    best: dict[str, Any] | None = None
    best_len = -1
    for row in load(home).get("folders") or []:
        if not isinstance(row, dict):
            continue
        root = _resolve(str(row.get("path") or ""))
        if not root:
            continue
        if want == root or path_inside(want, root):
            if len(root) > best_len:
                best = dict(row)
                best["path"] = root
                best_len = len(root)
    return best


def envelope_for_cwd(home: Path, cwd: str, passport_envelope: str = "seatbelt") -> str:
    row = match(home, cwd)
    folder_env = normalize(str((row or {}).get("envelope") or "seatbelt"))
    return tighter(passport_envelope, folder_env)


def is_exclusive(home: Path, cwd: str) -> bool:
    row = match(home, cwd)
    return bool(row and row.get("exclusive") is True)


def cage_wanted(home: Path, cwd: str) -> bool:
    row = match(home, cwd)
    return bool(row and row.get("cage") is True)


def upsert(
    home: Path,
    path: str,
    envelope: str,
    *,
    exclusive: bool | None = None,
    cage: bool | None = None,
) -> dict[str, Any]:
    root = _resolve(path)
    if not root:
        raise ValueError("folder path required")
    env = normalize(envelope)
    if env not in ENVELOPES:
        raise ValueError(f"unknown envelope {envelope!r}")
    data = load(home)
    rows: list[Any] = list(data.get("folders") or [])
    found = False
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if _resolve(str(row.get("path") or "")) == root:
            nxt = dict(row)
            nxt["path"] = root
            nxt["envelope"] = env
            if exclusive is not None:
                nxt["exclusive"] = bool(exclusive)
            if cage is not None:
                nxt["cage"] = bool(cage)
            rows[i] = nxt
            found = True
            break
    if not found:
        rows.append(
            {
                "path": root,
                "envelope": env,
                "exclusive": bool(exclusive) if exclusive is not None else False,
                "cage": bool(cage) if cage is not None else False,
            }
        )
    data["folders"] = rows
    save(home, data)
    return match(home, root) or {}


def drop(home: Path, path: str) -> bool:
    root = _resolve(path)
    data = load(home)
    rows = [
        row
        for row in (data.get("folders") or [])
        if isinstance(row, dict) and _resolve(str(row.get("path") or "")) != root
    ]
    changed = len(rows) != len(data.get("folders") or [])
    data["folders"] = rows
    if changed:
        save(home, data)
    return changed


def list_folders(home: Path) -> list[dict[str, Any]]:
    rows = []
    for row in load(home).get("folders") or []:
        if isinstance(row, dict) and row.get("path"):
            rows.append(row)
    return rows
