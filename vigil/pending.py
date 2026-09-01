"""File-drop protocol between the hook and the overlay.

Hook writes pending/<id>.json, waits for pending/<id>.decision, then
unlinks both. Overlay / `vigil decide` writes the decision. Timeout is
deny. Never fail-open on silence — Grok YOLO would otherwise run it.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from vigil.call import ToolCall
from vigil.paths import pending_dir
from vigil.risk import Risk, severity_for

AGENT_DISPLAY = {
    "grok": "Grok",
    "claude": "Claude Code",
    "opencode": "OpenCode",
    "codex": "Codex",
    "cursor-agent": "Cursor",
}

ACTIONS = frozenset({"allow", "session", "always", "deny", "deny-always"})


@dataclass(frozen=True)
class Decision:
    action: str
    source: str = "user"


def new_id() -> str:
    return uuid.uuid4().hex


def request_path(home: Path, req_id: str) -> Path:
    return pending_dir(home) / f"{req_id}.json"


def decision_path(home: Path, req_id: str) -> Path:
    return pending_dir(home) / f"{req_id}.decision"


def write_request(
    home: Path,
    *,
    req_id: str,
    call: ToolCall,
    risk: Risk,
    created_at: str,
    expires_at: str,
) -> Path:
    payload = {
        "id": req_id,
        "createdAt": created_at,
        "expiresAt": expires_at,
        "agent": call.agent_hint,
        "sessionId": call.session_id,
        "cwd": call.cwd,
        "workspace": call.workspace,
        "tool": call.tool,
        "rawTool": call.raw_tool,
        "summary": call.summary,
        "command": call.command,
        "path": call.path,
        "classId": risk.class_id,
        "title": risk.title,
        "reason": risk.reason,
        "ruleKey": risk.rule_key,
        "permissionMode": call.permission_mode,
    }
    folder = pending_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    path = request_path(home, req_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def write_decision(home: Path, req_id: str, action: str, source: str = "user") -> Path:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    folder = pending_dir(home)
    folder.mkdir(parents=True, exist_ok=True)
    path = decision_path(home, req_id)
    payload = {"id": req_id, "action": action, "source": source}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def read_decision(home: Path, req_id: str) -> Decision | None:
    path = decision_path(home, req_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    action = str(data.get("action") or "")
    if action not in ACTIONS:
        return None
    return Decision(action=action, source=str(data.get("source") or "user"))


def cleanup(home: Path, req_id: str) -> None:
    for path in (request_path(home, req_id), decision_path(home, req_id)):
        try:
            path.unlink()
        except OSError:
            pass


def decorate(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    agent = str(item.get("agent") or "agent")
    display = AGENT_DISPLAY.get(agent, agent)
    summary = str(item.get("summary") or item.get("title") or "a command")
    if len(summary) > 48:
        summary = summary[:45] + "…"
    item["severity"] = severity_for(str(item.get("classId") or ""))
    item["barLine"] = f"{display} is trying to {summary}"
    return item


def list_pending(home: Path) -> list[dict[str, Any]]:
    folder = pending_dir(home)
    if not folder.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        if path.name.endswith(".tmp"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("id"):
            rows.append(decorate(data))
    return rows


def wait_for_decision(
    home: Path,
    req_id: str,
    timeout_sec: float,
    *,
    poll_sec: float = 0.05,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Decision | None:
    deadline = clock() + timeout_sec
    while clock() < deadline:
        got = read_decision(home, req_id)
        if got is not None:
            return got
        remaining = deadline - clock()
        if remaining <= 0:
            break
        sleeper(min(poll_sec, remaining))
    return None
