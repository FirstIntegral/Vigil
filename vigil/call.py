"""Normalize Claude and Grok PreToolUse envelopes into one ToolCall."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


TOOL_ALIASES = {
    "bash": "bash",
    "run_terminal_command": "bash",
    "run_terminal_cmd": "bash",
    "shell": "bash",
    "read": "read",
    "read_file": "read",
    "write": "write",
    "edit": "write",
    "multiedit": "write",
    "search_replace": "write",
    "strreplace": "write",
    "grep": "grep",
    "glob": "list",
    "listdir": "list",
    "list_dir": "list",
    "websearch": "web",
    "web_search": "web",
    "webfetch": "web",
    "web_fetch": "web",
    "open_page": "web",
    "task": "subagent",
    "spawn_subagent": "subagent",
}


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data and data[key] is not None:
            return data[key]
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def normalize_tool(name: str) -> str:
    key = name.strip()
    if not key:
        return "unknown"
    lower = key.lower()
    if lower in TOOL_ALIASES:
        return TOOL_ALIASES[lower]
    # MCP: server__tool — treat as unknown-ask unless it is clearly a read.
    if "__" in key:
        return "mcp"
    return lower


def normalize_event(name: str) -> str:
    text = name.strip().lower().replace("-", "_")
    aliases = {
        "pretooluse": "pre_tool_use",
        "pre_tool_use": "pre_tool_use",
        "posttooluse": "post_tool_use",
        "post_tool_use": "post_tool_use",
        "sessionstart": "session_start",
        "session_start": "session_start",
    }
    return aliases.get(text, text)


@dataclass(frozen=True)
class ToolCall:
    event: str
    tool: str
    raw_tool: str
    command: str | None
    path: str | None
    cwd: str
    workspace: str
    session_id: str
    permission_mode: str
    agent_hint: str
    raw_input: dict[str, Any] = field(default_factory=dict)

    @property
    def is_pre_tool(self) -> bool:
        return self.event == "pre_tool_use"

    @property
    def is_post_tool(self) -> bool:
        return self.event == "post_tool_use"

    @property
    def summary(self) -> str:
        if self.command:
            one = " ".join(self.command.split())
            if len(one) > 220:
                return one[:217] + "…"
            return one
        if self.path:
            return self.path
        return self.raw_tool or self.tool


def parse_envelope(data: dict[str, Any]) -> ToolCall:
    event = normalize_event(_as_str(_first(data, "hook_event_name", "hookEventName")))
    raw_tool = _as_str(_first(data, "tool_name", "toolName"))
    tool_input = _as_dict(_first(data, "tool_input", "toolInput") or {})
    command = _first(tool_input, "command", "cmd", "script")
    command_s = _as_str(command) if command else None
    path = _first(
        tool_input,
        "file_path",
        "filePath",
        "target_file",
        "targetFile",
        "path",
    )
    path_s = _as_str(path) if path else None
    cwd = _as_str(_first(data, "cwd"))
    workspace = _as_str(_first(data, "workspaceRoot", "workspace_root")) or cwd
    session_id = _as_str(_first(data, "session_id", "sessionId"))
    permission_mode = _as_str(_first(data, "permission_mode", "permissionMode"))
    # Grok camelCase envelope vs Claude snake_case.
    agent_hint = "grok" if "toolName" in data or "hookEventName" in data else "claude"
    if "tool_name" in data or "hook_event_name" in data:
        if "toolName" not in data and "hookEventName" not in data:
            agent_hint = "claude"
    return ToolCall(
        event=event or "unknown",
        tool=normalize_tool(raw_tool),
        raw_tool=raw_tool,
        command=command_s or None,
        path=path_s or None,
        cwd=cwd,
        workspace=workspace,
        session_id=session_id,
        permission_mode=permission_mode,
        agent_hint=agent_hint,
        raw_input=tool_input,
    )
