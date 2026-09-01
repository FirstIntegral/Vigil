"""Stable tickets. Always remembers a class, not an argv string."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from vigil.call import ToolCall

_HOST_URL = re.compile(r"https?://[^\s'\"\\]+", re.IGNORECASE)
_SSH_HOST = re.compile(
    r"\b(?:ssh|scp|rsync)\b(?:\s+\S+)*?\s+(?:[A-Za-z0-9._-]+@)?([A-Za-z0-9._-]+\.[A-Za-z0-9._-]+)",
    re.IGNORECASE,
)


def project_id(path: str) -> str:
    raw = (path or "").rstrip("/")
    if not raw:
        return "_"
    base = Path(raw).name.replace(":", "_")[:48] or "_"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


def _safe(part: str) -> str:
    return re.sub(r"[^A-Za-z0-9._*-]+", "_", part)[:80]


def ticket_key(call: ToolCall, class_id: str, extra: str = "") -> str:
    agent = _safe(call.agent_hint or "agent") or "agent"
    proj = project_id(call.workspace or call.cwd)
    parts = ["t", agent, proj, class_id]
    if extra:
        parts.append(_safe(extra))
    return ":".join(parts)


def mcp_server(raw_tool: str) -> str:
    if not raw_tool or "__" not in raw_tool:
        return ""
    return raw_tool.split("__", 1)[0].lower()


def network_host(command: str) -> str:
    if not command:
        return ""
    match = _HOST_URL.search(command)
    if match:
        parsed = urlparse(match.group(0))
        return (parsed.hostname or "").lower()
    ssh = _SSH_HOST.search(command)
    if ssh:
        return ssh.group(1).lower()
    return ""
