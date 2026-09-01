"""Install / remove PreToolUse hooks. Idempotent. Never sudo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vigil import HOOK_TIMEOUT_SEC, PLUGIN_ID


MARKER = "vigil gate"


def grok_hook_document(helper: str) -> dict[str, Any]:
    handler = {
        "type": "command",
        "command": f"{helper} gate",
        "timeout": HOOK_TIMEOUT_SEC,
    }
    return {
        "hooks": {
            "PreToolUse": [{"hooks": [handler]}],
            "PostToolUse": [{"hooks": [{**handler, "timeout": 5}]}],
        }
    }


def grok_hook_path(home: Path) -> Path:
    return home / ".grok" / "hooks" / "vigil.json"


def claude_settings_path(home: Path) -> Path:
    return home / ".claude" / "settings.json"


def _is_our_handler(handler: Any, helper: str) -> bool:
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command") or "")
    return MARKER in command or helper in command


def _strip_event(groups: list[Any], helper: str) -> list[Any]:
    kept = []
    for group in groups:
        if not isinstance(group, dict):
            kept.append(group)
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            kept.append(group)
            continue
        handlers = [h for h in handlers if not _is_our_handler(h, helper)]
        if handlers:
            nxt = dict(group)
            nxt["hooks"] = handlers
            kept.append(nxt)
    return kept


def merge_claude_hooks(settings: dict[str, Any], helper: str) -> dict[str, Any]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    new_hooks = dict(hooks)
    pre = hooks.get("PreToolUse") if isinstance(hooks.get("PreToolUse"), list) else []
    post = hooks.get("PostToolUse") if isinstance(hooks.get("PostToolUse"), list) else []
    new_hooks["PreToolUse"] = _strip_event(pre, helper) + [
        {"hooks": [{"type": "command", "command": f"{helper} gate", "timeout": HOOK_TIMEOUT_SEC}]}
    ]
    new_hooks["PostToolUse"] = _strip_event(post, helper) + [
        {"hooks": [{"type": "command", "command": f"{helper} gate", "timeout": 5}]}
    ]
    out = dict(settings)
    out["hooks"] = new_hooks
    return out


def strip_claude_hooks(settings: dict[str, Any], helper: str) -> dict[str, Any]:
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return settings
    new_hooks = dict(hooks)
    for event in ("PreToolUse", "PostToolUse"):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept = _strip_event(groups, helper)
        if kept:
            new_hooks[event] = kept
        else:
            new_hooks.pop(event, None)
    out = dict(settings)
    out["hooks"] = new_hooks
    return out


def hooks_installed(home: Path, helper: str) -> dict[str, bool]:
    grok = grok_hook_path(home)
    grok_ok = False
    if grok.is_file():
        try:
            grok_ok = MARKER in grok.read_text(encoding="utf-8")
        except OSError:
            grok_ok = False
    claude_ok = False
    cpath = claude_settings_path(home)
    if cpath.is_file():
        try:
            data = json.loads(cpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        claude_ok = MARKER in json.dumps(data) or helper in json.dumps(data)
    return {"grok": grok_ok, "claude": claude_ok}


def install(home: Path, helper: str) -> dict[str, str]:
    written: dict[str, str] = {}
    gpath = grok_hook_path(home)
    gpath.parent.mkdir(parents=True, exist_ok=True)
    doc = grok_hook_document(helper)
    gpath.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    written["grok"] = str(gpath)

    cpath = claude_settings_path(home)
    if cpath.is_file():
        try:
            settings = json.loads(cpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        merged = merge_claude_hooks(settings, helper)
        tmp = cpath.with_suffix(".tmp")
        tmp.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
        tmp.replace(cpath)
        written["claude"] = str(cpath)
    else:
        written["claude"] = "skipped (no ~/.claude/settings.json)"
    written["plugin"] = PLUGIN_ID
    written["helper"] = helper
    return written


def uninstall(home: Path, helper: str) -> dict[str, str]:
    removed: dict[str, str] = {}
    gpath = grok_hook_path(home)
    if gpath.is_file():
        gpath.unlink()
        removed["grok"] = f"removed {gpath}"
    else:
        removed["grok"] = "absent"
    cpath = claude_settings_path(home)
    if cpath.is_file():
        try:
            settings = json.loads(cpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            settings = {}
        if isinstance(settings, dict):
            stripped = strip_claude_hooks(settings, helper)
            tmp = cpath.with_suffix(".tmp")
            tmp.write_text(json.dumps(stripped, indent=2) + "\n", encoding="utf-8")
            tmp.replace(cpath)
            removed["claude"] = f"stripped {cpath}"
    return removed
