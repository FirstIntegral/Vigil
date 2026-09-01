"""Hyprland window outlines for a pending call. Empty when hyprctl is gone."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from vigil.call import ToolCall


def _clients() -> list[dict[str, Any]]:
    exe = shutil.which("hyprctl")
    if not exe:
        return []
    try:
        out = subprocess.run(
            [exe, "clients", "-j"],
            check=False,
            capture_output=True,
            text=True,
            timeout=0.6,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    try:
        data = json.loads(out.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _matches(client: dict[str, Any], call: ToolCall) -> bool:
    cwd = (call.cwd or "").rstrip("/")
    path = call.path or ""
    title = str(client.get("title") or "")
    wclass = str(client.get("class") or "")
    initial = str(client.get("initialTitle") or "")
    hay = f"{title} {wclass} {initial}".lower()
    if cwd:
        name = Path(cwd).name.lower()
        if name and name in hay:
            return True
        if cwd.lower() in hay:
            return True
    if path:
        name = Path(path).name.lower()
        if name and name in hay:
            return True
    agent = (call.agent_hint or "").lower()
    if agent and agent in hay:
        return True
    # Agent terminals often use org.omarchy.agent
    if "org.omarchy.agent" in wclass.lower() or "omarchy.agent" in wclass.lower():
        return True
    return False


def ghosts_for(call: ToolCall) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for client in _clients():
        if not _matches(client, call):
            continue
        at = client.get("at") or [0, 0]
        size = client.get("size") or [0, 0]
        if not (isinstance(at, list) and len(at) >= 2):
            continue
        if not (isinstance(size, list) and len(size) >= 2):
            continue
        workspace = client.get("workspace") or {}
        ws = workspace.get("id") if isinstance(workspace, dict) else None
        found.append(
            {
                "address": str(client.get("address") or ""),
                "at": [int(at[0]), int(at[1])],
                "size": [int(size[0]), int(size[1])],
                "title": str(client.get("title") or ""),
                "workspace": ws,
                "class": str(client.get("class") or ""),
            }
        )
    return found[:12]
