"""Install / remove PreToolUse hooks. Idempotent. Never sudo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vigil import HOOK_TIMEOUT_SEC, PLUGIN_ID
from vigil.house import skill_markdown
from vigil.machine import write as write_machine
from vigil.secure import write_private


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


def opencode_plugin_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "plugins" / "vigil.js"


def codex_hooks_path(home: Path) -> Path:
    return home / ".codex" / "hooks.json"


def _plugin_root_from_helper(helper: str) -> Path:
    return Path(helper).resolve().parent.parent


def opencode_plugin_source(helper: str) -> str:
    candidates = (
        _plugin_root_from_helper(helper) / "harnesses" / "opencode-plugin.js",
        Path(__file__).resolve().parent.parent / "harnesses" / "opencode-plugin.js",
    )
    body = ""
    for src in candidates:
        if src.is_file():
            body = src.read_text(encoding="utf-8")
            break
    if not body:
        raise FileNotFoundError("missing harnesses/opencode-plugin.js")
    return body.replace("__VIGIL_HELPER__", helper.replace("\\", "\\\\"))


def codex_hook_document(helper: str) -> dict[str, Any]:
    handler = {
        "type": "command",
        "command": f"{helper} gate",
        "timeout": HOOK_TIMEOUT_SEC,
        "statusMessage": "Vigil",
    }
    return {
        "hooks": {
            "PreToolUse": [{"hooks": [handler]}],
            "PostToolUse": [{"hooks": [{**handler, "timeout": 5}]}],
        }
    }


def merge_codex_hooks(doc: dict[str, Any], helper: str) -> dict[str, Any]:
    return merge_claude_hooks(doc, helper)


def strip_codex_hooks(doc: dict[str, Any], helper: str) -> dict[str, Any]:
    return strip_claude_hooks(doc, helper)


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
    opencode_ok = False
    opath = opencode_plugin_path(home)
    if opath.is_file():
        try:
            obody = opath.read_text(encoding="utf-8")
            opencode_ok = MARKER in obody or helper in obody
        except OSError:
            opencode_ok = False
    codex_ok = False
    xpath = codex_hooks_path(home)
    if xpath.is_file():
        try:
            body = xpath.read_text(encoding="utf-8")
            codex_ok = MARKER in body or helper in body
        except OSError:
            codex_ok = False
    return {"grok": grok_ok, "claude": claude_ok, "opencode": opencode_ok, "codex": codex_ok}


def install(home: Path, helper: str) -> dict[str, str]:
    written: dict[str, str] = {}
    gpath = grok_hook_path(home)
    gpath.parent.mkdir(parents=True, exist_ok=True)
    doc = grok_hook_document(helper)
    write_private(gpath, json.dumps(doc, indent=2) + "\n")
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
        write_private(cpath, json.dumps(merged, indent=2) + "\n")
        written["claude"] = str(cpath)
    else:
        written["claude"] = "skipped (no ~/.claude/settings.json)"

    opath = opencode_plugin_path(home)
    opath.parent.mkdir(parents=True, exist_ok=True)
    write_private(opath, opencode_plugin_source(helper))
    written["opencode"] = str(opath)

    xpath = codex_hooks_path(home)
    xpath.parent.mkdir(parents=True, exist_ok=True)
    if xpath.is_file():
        try:
            existing = json.loads(xpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}
        merged_x = merge_codex_hooks(existing, helper)
    else:
        merged_x = codex_hook_document(helper)
    write_private(xpath, json.dumps(merged_x, indent=2) + "\n")
    written["codex"] = str(xpath)

    skill_dest = home / ".agents" / "skills" / "vigil" / "SKILL.md"
    root = Path(helper).resolve().parent.parent
    src = root / "skill" / "SKILL.md"
    body = src.read_text(encoding="utf-8") if src.is_file() else skill_markdown()
    skill_dest.parent.mkdir(parents=True, exist_ok=True)
    skill_dest.write_text(body, encoding="utf-8")
    written["skill"] = str(skill_dest)
    written["plugin"] = PLUGIN_ID
    written["helper"] = helper
    written["machine"] = str(write_machine(home))
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
            write_private(cpath, json.dumps(stripped, indent=2) + "\n")
            removed["claude"] = f"stripped {cpath}"
    opath = opencode_plugin_path(home)
    if opath.is_file():
        opath.unlink()
        removed["opencode"] = f"removed {opath}"
    else:
        removed["opencode"] = "absent"
    xpath = codex_hooks_path(home)
    if xpath.is_file():
        try:
            settings = json.loads(xpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            settings = {}
        if isinstance(settings, dict):
            stripped = strip_codex_hooks(settings, helper)
            if stripped.get("hooks"):
                write_private(xpath, json.dumps(stripped, indent=2) + "\n")
                removed["codex"] = f"stripped {xpath}"
            else:
                xpath.unlink()
                removed["codex"] = f"removed {xpath}"
    else:
        removed["codex"] = "absent"
    return removed
