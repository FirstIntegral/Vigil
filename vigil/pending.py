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
from vigil.secure import ensure_private_dir, redact, redact_path, write_private

AGENT_DISPLAY = {
    "grok": "Grok",
    "claude": "Claude Code",
    "opencode": "OpenCode",
    "codex": "Codex",
    "cursor-agent": "Cursor",
}

ACTIONS = frozenset({"allow", "session", "always", "deny", "deny-always", "rewind", "unfreeze"})


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
    envelope: str = "",
) -> Path:
    from vigil.ghosts import ghosts_for

    ghosts = ghosts_for(call)
    blast = risk.blast or ""
    if ghosts and not blast:
        blast = f"{len(ghosts)} windows"
    elif ghosts:
        blast = f"{blast} · {len(ghosts)} windows"
    payload = {
        "id": req_id,
        "kind": "tool",
        "createdAt": created_at,
        "expiresAt": expires_at,
        "agent": call.agent_hint,
        "sessionId": call.session_id,
        "cwd": call.cwd,
        "workspace": call.workspace,
        "tool": call.tool,
        "rawTool": call.raw_tool,
        "summary": redact(call.summary),
        "command": redact(call.command or ""),
        "path": redact_path(call.path or ""),
        "classId": risk.class_id,
        "title": risk.title,
        "reason": risk.reason,
        "ruleKey": risk.rule_key,
        "ticket": risk.rule_key,
        "article": risk.article,
        "blast": blast,
        "envelope": envelope,
        "reversible": risk.reversible,
        "ghosts": ghosts,
        "permissionMode": call.permission_mode,
    }
    folder = ensure_private_dir(pending_dir(home))
    path = request_path(home, req_id)
    write_private(path, json.dumps(payload, indent=2) + "\n")
    return path


def write_decision(home: Path, req_id: str, action: str, source: str = "user") -> Path:
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}")
    folder = ensure_private_dir(pending_dir(home))
    path = decision_path(home, req_id)
    payload = {"id": req_id, "action": action, "source": source}
    write_private(path, json.dumps(payload) + "\n")
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


def write_away(home: Path) -> Path:
    """While-you-were-out card. Not a tool-call wait."""
    req_id = "away-" + new_id()[:12]
    from vigil.dossier import summarize

    dossier = summarize(home)
    counts = dossier.get("counts") or {}
    files = dossier.get("files") or []
    payload = {
        "id": req_id,
        "kind": "away",
        "createdAt": "",
        "expiresAt": "",
        "agent": "vigil",
        "title": "Agents were frozen while the screen was locked",
        "reason": "Locking the session froze every coding agent. Unlocking does not start them again. Press U to let them run, W to restore files they changed, or N to keep them frozen.",
        "summary": f"{counts.get('tools') or 0} tool calls today, {len(files)} files touched",
        "classId": "lid",
        "barLine": "Vigil · while you were out",
        "blast": " · ".join(files[-4:]) if files else "no files logged",
        "article": "",
        "ghosts": [],
        "ticket": "",
        "cwd": "",
        "command": "",
        "path": "",
        "reversible": True,
    }
    ensure_private_dir(pending_dir(home))
    path = request_path(home, req_id)
    write_private(path, json.dumps(payload, indent=2) + "\n")
    return path


def write_surprise(home: Path, *, summary: str, path: str, agent: str) -> Path:
    req_id = "surprise-" + new_id()[:12]
    payload = {
        "id": req_id,
        "kind": "surprise",
        "agent": agent,
        "title": "This agent wrote somewhere it should not",
        "reason": "The original call was allowed, but the file that landed is a secret or sits outside the project. Press U to unfreeze after you have looked, W to restore tracked files, or N to keep the agent frozen.",
        "summary": redact(summary),
        "path": redact_path(path),
        "classId": "surprise",
        "barLine": "Vigil · incident",
        "blast": redact_path(path),
        "article": "",
        "ghosts": [],
        "ticket": "",
        "cwd": "",
        "command": "",
        "reversible": False,
    }
    ensure_private_dir(pending_dir(home))
    dest = request_path(home, req_id)
    write_private(dest, json.dumps(payload, indent=2) + "\n")
    return dest


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
