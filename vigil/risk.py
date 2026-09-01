"""Classify a tool call: allow, ask, or deny. Pure: no I/O."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from vigil.call import ToolCall
from vigil.house import article_for
from vigil.ticket import mcp_server, network_host, ticket_key

# Hard deny = do not even ask. These destroy the machine or pipe the
# internet into a shell. Overlay never sees them.
DENY = "deny"
ASK = "ask"
ALLOW = "allow"

CRITICAL_CLASSES = frozenset(
    {
        "rm-root",
        "pipe-shell",
        "fork-bomb",
        "mkfs",
        "dd-device",
        "chmod-root",
        "force-main",
        "power",
        "desktop-kill",
        "plugin-inject",
        "self-approve",
    }
)


def severity_for(class_id: str) -> str:
    return "critical" if class_id in CRITICAL_CLASSES else "warning"


@dataclass(frozen=True)
class Risk:
    decision: str
    class_id: str
    title: str
    reason: str
    rule_key: str
    extra: str = ""
    reversible: bool = True
    hold: bool = False
    blast: str = ""
    article: str = ""


_SECRET_NAMES = frozenset(
    {
        ".env",
        ".netrc",
        ".npmrc",
        ".pypirc",
        "id_rsa",
        "id_ed25519",
        "id_ecdsa",
        "id_dsa",
        "auth.json",
        "credentials",
        "credentials.json",
        "secrets.json",
        "wallet.json",
    }
)
_SECRET_SUFFIXES = (".pem", ".p12", ".pfx", ".key", ".kdbx")
_SECRET_DIR_PARTS = (".ssh", ".gnupg", ".gpg", "gpg-signing")

_SAFE_BASH = re.compile(
    r"^(ls|pwd|true|false|date|uname|hostname|whoami|id|env|printenv)\b|"
    r"^git (status|diff|log|show|rev-parse|describe|add)(\s|$)|"
    r"^git branch$|"
    r"^python3? -m (unittest|pytest)\b|"
    r"^pytest\b|"
    r"^bash scripts/test\.sh|"
    r"^rg\b|^grep\b|^wc\b|^head\b|^tail\b|"
    r"^mkdir -p |"
    r"^git fetch\b|^git pull\b"
)

_RM_RF_ROOT = re.compile(
    r"\brm\s+-[^\s]*[rf][^\s]*\s+(?:--\s+)?(/|~|/home|/Users|\$HOME|\$\{HOME\})(?:\s|/|\*|$)",
    re.IGNORECASE,
)
_MKFS = re.compile(r"\bmkfs(\.\w+)?\b", re.IGNORECASE)
_DD_DEV = re.compile(r"\bdd\b[^\n]*\bof=/dev/", re.IGNORECASE)
_FORK_BOMB = re.compile(r":\(\)\s*\{[^}]*\|[^}]*&")
_PIPE_SHELL = re.compile(
    r"\b(curl|wget|fetch)\b[^\n]*\|\s*(sudo\s+)?((ba)?sh|zsh|fish|python3?)\b",
    re.IGNORECASE,
)
_CHMOD_ROOT = re.compile(r"\bchmod\s+(-R\s+)?0?777\s+/", re.IGNORECASE)
_FORCE_MAIN = re.compile(
    r"\bgit\s+push\b[^\n]*--force[^\n]*\b(origin\s+)?(main|master)\b"
    r"|\bgit\s+push\b[^\n]*\b(origin\s+)?(main|master)\b[^\n]*--force",
    re.IGNORECASE,
)
_SUDO = re.compile(r"(^|[;&|]\s*)sudo\b")
_GIT_PUSH = re.compile(r"\bgit\s+push\b", re.IGNORECASE)
_GIT_RESET_HARD = re.compile(r"\bgit\s+reset\s+[^\n]*--hard", re.IGNORECASE)
_GIT_FORCE = re.compile(r"\bgit\s+push\b[^\n]*--force", re.IGNORECASE)
_RM_RF = re.compile(r"\brm\s+-[^\s]*[rf][^\s]*\b", re.IGNORECASE)
_NET = re.compile(
    r"\b(curl|wget|nc|ncat|ssh|scp|rsync|ftp|telnet)\b",
    re.IGNORECASE,
)
_PKG = re.compile(
    r"\b(pacman|apt|apt-get|dnf|yum|pip3?|npm|pnpm|yarn|cargo|gem)\s+"
    r"(install|-S|add|i)\b",
    re.IGNORECASE,
)
_POWER = re.compile(
    r"\b(reboot|shutdown|poweroff|halt|systemctl\s+(stop|disable|mask)|"
    r"mkfs|fdisk|parted)\b",
    re.IGNORECASE,
)
_KILL = re.compile(r"\b(kill|killall|pkill)\b")
_FIND_DELETE = re.compile(r"\bfind\b[^\n]*-delete", re.IGNORECASE)
_HYPR_DEADLY = re.compile(
    r"\bhyprctl\s+dispatch\s+(exit|killactive|killwindow|forcekillactive|exec)\b",
    re.IGNORECASE,
)
_HYPR = re.compile(r"\bhyprctl\b", re.IGNORECASE)
_PLUGIN_MUTATE = re.compile(
    r"\bomarchy\s+plugin\s+(add|enable|disable|remove|update)\b",
    re.IGNORECASE,
)
_SELF_APPROVE = re.compile(
    r"\bvigil\s+decide\b|\.local/state/vigil|\.config/vigil|pending/\S+\.decision",
    re.IGNORECASE,
)
_IDENTITY = re.compile(
    r"\b(ssh-add|gpg\s+--(clearsign|sign|detach-sign)|gh\s+auth)\b",
    re.IGNORECASE,
)
_OMARCHY_RESTART = re.compile(
    r"\b(omarchy-restart|systemctl\s+--user\s+restart\s+omarchy)\b",
    re.IGNORECASE,
)


def _collapse(command: str) -> str:
    return " ".join(command.split())


def is_secret_path(path: str) -> bool:
    if not path:
        return False
    p = Path(path)
    name = p.name.lower()
    if name in _SECRET_NAMES:
        return True
    if name.startswith(".env"):
        return True
    if any(name.endswith(suf) for suf in _SECRET_SUFFIXES):
        return True
    parts = {part.lower() for part in p.parts}
    return bool(parts & {d.lower() for d in _SECRET_DIR_PARTS})


def _inside(path: str, root: str) -> bool:
    if not path or not root:
        return False
    try:
        base = Path(root).resolve()
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = base / resolved
        candidate = Path(os.path.normpath(str(resolved)))
        if candidate.exists() or candidate.is_symlink():
            candidate = candidate.resolve()
        return os.path.commonpath([str(candidate), str(base)]) == str(base)
    except (OSError, ValueError):
        return False


def path_inside(path: str, root: str) -> bool:
    return _inside(path, root)


def is_vigil_state(path: str) -> bool:
    if not path:
        return False
    text = path.replace("\\", "/")
    return "/.local/state/vigil" in text or text.endswith(".config/vigil") or "/.config/vigil/" in text


def _rule_key(call: ToolCall, class_id: str, extra: str = "") -> str:
    return ticket_key(call, class_id, extra)


def _risk(
    call: ToolCall,
    decision: str,
    class_id: str,
    title: str,
    reason: str,
    extra: str = "",
    reversible: bool = True,
    blast: str = "",
) -> Risk:
    return Risk(
        decision=decision,
        class_id=class_id,
        title=title,
        reason=reason,
        rule_key=_rule_key(call, class_id, extra),
        extra=extra,
        reversible=reversible,
        hold=False,
        blast=blast or (call.path or ""),
        article=article_for(class_id),
    )


def classify(call: ToolCall) -> Risk:
    if call.path and (is_secret_path(call.path) or is_vigil_state(call.path)) and call.tool == "write":
        if is_vigil_state(call.path):
            return _risk(
                call,
                DENY,
                "self-approve",
                "Rewrite Vigil's own state",
                "Blocked. An agent cannot mint its own approval.",
                reversible=False,
                blast=call.path,
            )
        return _risk(
            call,
            ASK,
            "secret-write",
            "Write a secret file",
            f"Agent wants to change {call.path}.",
            extra=Path(call.path).name,
            reversible=False,
            blast=call.path,
        )

    if call.tool in {"read", "grep", "list"}:
        if call.path and is_secret_path(call.path):
            return _risk(
                call,
                ASK,
                "secret-read",
                "Read a secret file",
                f"Agent wants to read {call.path}.",
                extra=Path(call.path).name,
                reversible=True,
                blast=call.path,
            )
        return _risk(call, ALLOW, "read", "Read", "Project read.")

    if call.tool == "write":
        path = call.path or ""
        root = call.workspace or call.cwd
        if path and root and not _inside(path, root):
            return _risk(
                call,
                ASK,
                "write-outside",
                "Write outside the project",
                f"Agent wants to write {path}, which is outside {root}.",
                extra=str(Path(path).parent),
                blast=path,
            )
        return _risk(call, ALLOW, "write", "Edit project file", "Write inside the project.", blast=path)

    if call.tool == "web":
        host = network_host(call.summary)
        return _risk(
            call,
            ASK,
            "network",
            "Talk to the network",
            call.summary,
            extra=host,
            reversible=False,
            blast=host or call.summary,
        )

    if call.tool == "subagent":
        return _risk(
            call,
            ASK,
            "subagent",
            "Spawn another agent",
            call.summary + " Child starts with an empty session wallet.",
            blast="child wallet empty",
        )

    if call.tool == "mcp":
        server = mcp_server(call.raw_tool)
        return _risk(
            call,
            ASK,
            "mcp",
            f"Call {server or 'an external tool'}",
            f"{call.raw_tool}: {call.summary}",
            extra=server,
            reversible=False,
            blast=server or call.raw_tool,
        )

    if call.tool != "bash" or not call.command:
        return _risk(
            call,
            ASK,
            "unknown",
            f"Use {call.raw_tool or call.tool}",
            call.summary,
        )

    cmd = _collapse(call.command)

    if _SELF_APPROVE.search(cmd):
        return _risk(
            call,
            DENY,
            "self-approve",
            "Self-approve",
            "Blocked. An agent cannot answer its own card or rewrite Vigil.",
            reversible=False,
        )
    if _FORK_BOMB.search(cmd):
        return _risk(call, DENY, "fork-bomb", "Fork bomb", "Blocked. This would hang the machine.", reversible=False)
    if _MKFS.search(cmd):
        return _risk(call, DENY, "mkfs", "Format a disk", "Blocked. mkfs destroys disks.", reversible=False)
    if _DD_DEV.search(cmd):
        return _risk(
            call, DENY, "dd-device", "Raw write to a device", "Blocked. dd to /dev would destroy a disk.", reversible=False
        )
    if _RM_RF_ROOT.search(cmd):
        return _risk(
            call, DENY, "rm-root", "Delete the filesystem", "Blocked. Recursive delete of / or $HOME.", reversible=False
        )
    if _PIPE_SHELL.search(cmd):
        return _risk(
            call,
            DENY,
            "pipe-shell",
            "Pipe the internet into a shell",
            "Blocked. curl|sh is how machines get owned.",
            reversible=False,
        )
    if _CHMOD_ROOT.search(cmd):
        return _risk(call, DENY, "chmod-root", "chmod 777 /", "Blocked.", reversible=False)
    if _FORCE_MAIN.search(cmd):
        return _risk(
            call,
            DENY,
            "force-main",
            "Force-push main",
            "Blocked. Force-push to main/master is not silent.",
            reversible=False,
        )
    if _HYPR_DEADLY.search(cmd) or _OMARCHY_RESTART.search(cmd):
        return _risk(
            call,
            DENY,
            "desktop-kill",
            "Kill the compositor",
            "Blocked. This would take down the Omarchy desktop.",
            reversible=False,
            blast="Hyprland / omarchy-shell",
        )
    if _PLUGIN_MUTATE.search(cmd):
        return _risk(
            call,
            DENY,
            "plugin-inject",
            "Change an Omarchy plugin",
            "Blocked. Plugin code runs inside omarchy-shell, unsandboxed.",
            reversible=False,
            blast="~/.config/omarchy/plugins",
        )
    if _POWER.search(cmd):
        return _risk(
            call,
            DENY,
            "power",
            "Power or disk command",
            "Blocked. Reboot, shutdown, and disk tools are not silent.",
            reversible=False,
        )
    if _HYPR.search(cmd):
        return _risk(call, ASK, "desktop", "Talk to Hyprland", cmd, reversible=False, blast="hyprctl")
    if _IDENTITY.search(cmd):
        return _risk(call, ASK, "identity", "Use a signing key", cmd, reversible=False)
    if _SUDO.search(cmd):
        return _risk(call, ASK, "sudo", "Run as root", cmd, reversible=False)
    if _GIT_FORCE.search(cmd):
        return _risk(call, ASK, "git-force", "Force-push", cmd, reversible=False)
    if _GIT_PUSH.search(cmd):
        return _risk(call, ASK, "git-push", "git push", cmd, extra=network_host(cmd), reversible=False)
    if _GIT_RESET_HARD.search(cmd):
        return _risk(call, ASK, "git-reset", "git reset --hard", cmd, reversible=False)
    if _RM_RF.search(cmd) or _FIND_DELETE.search(cmd):
        return _risk(call, ASK, "destructive", "Recursive delete", cmd, reversible=False)
    if _PKG.search(cmd):
        return _risk(call, ASK, "packages", "Install packages", cmd, reversible=False)
    if _NET.search(cmd):
        host = network_host(cmd)
        return _risk(call, ASK, "network", "Network from the shell", cmd, extra=host, reversible=False, blast=host or cmd)
    if _KILL.search(cmd):
        return _risk(call, ASK, "kill", "Signal a process", cmd)
    if _SAFE_BASH.match(cmd):
        return _risk(call, ALLOW, "safe-bash", "Safe command", cmd)

    return _risk(call, ASK, "shell", "Run a shell command", cmd)
