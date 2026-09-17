"""Install / remove PreToolUse hooks. Idempotent. Never sudo."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vigil import HOOK_TIMEOUT_SEC, PLUGIN_ID
from vigil.house import skill_markdown
from vigil.machine import write as write_machine
from vigil.paths import config_dir
from vigil.policy import load_policy, save_policy
from vigil.secure import write_private


MARKER = "vigil gate"


def stable_helper_path(home: Path) -> Path:
    """XDG helper the harness calls. Plugin id changes must not 127."""
    return config_dir(home) / "bin" / "vigil"


def write_stable_helper(home: Path, plugin_bin: str) -> Path:
    dest = stable_helper_path(home)
    plugin_id = PLUGIN_ID
    body = (
        "#!/bin/sh\n"
        "# Stable Vigil helper. The plugin directory may move; this path does not.\n"
        "set -eu\n"
        f'PLUGIN_BIN="{plugin_bin}"\n'
        f'PLUGIN_ID_BIN="$HOME/.config/omarchy/plugins/{plugin_id}/bin/vigil"\n'
        'if [ -x "$PLUGIN_BIN" ]; then exec "$PLUGIN_BIN" "$@"; fi\n'
        'if [ -x "$PLUGIN_ID_BIN" ]; then exec "$PLUGIN_ID_BIN" "$@"; fi\n'
        'for p in "$HOME/.config/omarchy/plugins/"*/bin/vigil; do\n'
        '  if [ -x "$p" ]; then exec "$p" "$@"; fi\n'
        "done\n"
        'echo "vigil: plugin helper missing" >&2\n'
        "exit 127\n"
    )
    write_private(dest, body)
    os.chmod(dest, 0o700)
    return dest


def grok_hook_document(helper: str) -> dict[str, Any]:
    handler = {
        "type": "command",
        "command": f"{helper} gate",
        "timeout": HOOK_TIMEOUT_SEC,
    }
    return {
        "hooks": {
            "PreToolUse": [{"hooks": [handler]}],
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
    return body.replace("__VIGIL_HELPER__", helper.replace("\\", "\\\\")).replace(
        "__VIGIL_HOOK_TIMEOUT_MS__", str(HOOK_TIMEOUT_SEC * 1000)
    )


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
    return merge_claude_hooks(doc, helper, post=True)


def strip_codex_hooks(doc: dict[str, Any], helper: str) -> dict[str, Any]:
    return strip_claude_hooks(doc, helper)


def _is_our_handler(handler: Any, helper: str) -> bool:
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command") or "")
    return MARKER in command or helper in command


def _is_current_handler(handler: Any, helper: str) -> bool:
    """True only when the command uses this helper path.

    Marker-only matching would treat a leftover
    ``xyz.brwsk.vigil/bin/vigil gate`` as live after an id rename.
    Strip/merge still uses ``_is_our_handler`` so the old path is removed.
    """
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command") or "").strip()
    return command == f"{helper} gate" or command.startswith(helper + " ")


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


def merge_claude_hooks(
    settings: dict[str, Any], helper: str, *, post: bool = False
) -> dict[str, Any]:
    """Merge Vigil into a Claude-shaped hooks file.

    ``post=False`` (Claude default): Grok also loads ``~/.claude/settings.json``.
    A Vigil PostToolUse there is a TUI failure line on every Grok tool call
    when the helper 127s, and a second spawn when it does not. Surprise-write
    now runs on PreToolUse. ``post=True`` keeps Codex after-hooks.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    new_hooks = dict(hooks)
    pre = hooks.get("PreToolUse") if isinstance(hooks.get("PreToolUse"), list) else []
    post_groups = hooks.get("PostToolUse") if isinstance(hooks.get("PostToolUse"), list) else []
    new_hooks["PreToolUse"] = _strip_event(pre, helper) + [
        {"hooks": [{"type": "command", "command": f"{helper} gate", "timeout": HOOK_TIMEOUT_SEC}]}
    ]
    stripped_post = _strip_event(post_groups, helper)
    if post:
        new_hooks["PostToolUse"] = stripped_post + [
            {"hooks": [{"type": "command", "command": f"{helper} gate", "timeout": 5}]}
        ]
    elif stripped_post:
        new_hooks["PostToolUse"] = stripped_post
    else:
        new_hooks.pop("PostToolUse", None)
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


def _pretool_timeouts(doc: Any, helper: str, *, current: bool = False) -> list[int]:
    out: list[int] = []
    if not isinstance(doc, dict):
        return out
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return out
    pre = hooks.get("PreToolUse")
    if not isinstance(pre, list):
        return out
    match = _is_current_handler if current else _is_our_handler
    for group in pre:
        if not isinstance(group, dict):
            continue
        handlers = group.get("hooks")
        if not isinstance(handlers, list):
            continue
        for handler in handlers:
            if not match(handler, helper):
                continue
            try:
                out.append(int(handler.get("timeout")))
            except (TypeError, ValueError):
                out.append(0)
    return out


def _json_hook_fresh(text: str, helper: str) -> bool:
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        return False
    timeouts = _pretool_timeouts(doc, helper, current=True)
    if not (timeouts and all(t >= HOOK_TIMEOUT_SEC for t in timeouts)):
        return False
    return Path(helper).is_file()


def _opencode_hook_fresh(text: str, helper: str) -> bool:
    if f'const HELPER = "{helper}"' not in text and f"const HELPER = '{helper}'" not in text:
        return False
    return str(HOOK_TIMEOUT_SEC * 1000) in text


def _fresh_any(text: str, *helpers: str, kind: str = "json") -> bool:
    for helper in helpers:
        if not helper:
            continue
        if kind == "opencode":
            if _opencode_hook_fresh(text, helper) and Path(helper).is_file():
                return True
        elif _json_hook_fresh(text, helper):
            return True
    return False


def hooks_installed(home: Path, helper: str) -> dict[str, bool]:
    stable = str(stable_helper_path(home))
    grok_ok = False
    grok = grok_hook_path(home)
    if grok.is_file():
        try:
            grok_ok = _fresh_any(grok.read_text(encoding="utf-8"), stable, helper)
        except OSError:
            grok_ok = False
    claude_ok = False
    cpath = claude_settings_path(home)
    if cpath.is_file():
        try:
            claude_ok = _fresh_any(cpath.read_text(encoding="utf-8"), stable, helper)
        except OSError:
            claude_ok = False
    opencode_ok = False
    opath = opencode_plugin_path(home)
    if opath.is_file():
        try:
            opencode_ok = _fresh_any(
                opath.read_text(encoding="utf-8"), stable, helper, kind="opencode"
            )
        except OSError:
            opencode_ok = False
    codex_ok = False
    xpath = codex_hooks_path(home)
    if xpath.is_file():
        try:
            codex_ok = _fresh_any(xpath.read_text(encoding="utf-8"), stable, helper)
        except OSError:
            codex_ok = False
    return {"grok": grok_ok, "claude": claude_ok, "opencode": opencode_ok, "codex": codex_ok}


def install(home: Path, helper: str) -> dict[str, str]:
    written: dict[str, str] = {}
    hook_helper = str(write_stable_helper(home, helper))
    written["stableHelper"] = hook_helper
    gpath = grok_hook_path(home)
    gpath.parent.mkdir(parents=True, exist_ok=True)
    doc = grok_hook_document(hook_helper)
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
        merged = merge_claude_hooks(settings, hook_helper)
        write_private(cpath, json.dumps(merged, indent=2) + "\n")
        written["claude"] = str(cpath)
    else:
        written["claude"] = "skipped (no ~/.claude/settings.json)"

    opath = opencode_plugin_path(home)
    opath.parent.mkdir(parents=True, exist_ok=True)
    write_private(opath, opencode_plugin_source(hook_helper))
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
        merged_x = merge_codex_hooks(existing, hook_helper)
    else:
        merged_x = codex_hook_document(hook_helper)
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
    written["helper"] = hook_helper
    written["pluginHelper"] = helper
    written["machine"] = str(write_machine(home))
    policy = load_policy(home)
    policy.auto_arm = True
    save_policy(home, policy)
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
    policy = load_policy(home)
    policy.auto_arm = False
    save_policy(home, policy)
    removed["autoArm"] = "off"
    stable = stable_helper_path(home)
    if stable.is_file():
        stable.unlink()
        removed["stableHelper"] = f"removed {stable}"
    else:
        removed["stableHelper"] = "absent"
    return removed
