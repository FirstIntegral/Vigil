"""Classify a tool call: allow, ask, or deny. Pure: no I/O."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from vigil.call import ToolCall

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
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = Path(root) / resolved
        base = Path(root).resolve()
        # Don't require the file to exist.
        candidate = Path(os.path.normpath(str(resolved)))
        return os.path.commonpath([str(candidate), str(base)]) == str(base)
    except (OSError, ValueError):
        return False


def _rule_key(call: ToolCall, class_id: str) -> str:
    body = call.command or call.path or call.tool
    body = _collapse(body) if call.command else body
    return f"{call.tool}:{class_id}:{body}"


def classify(call: ToolCall) -> Risk:
    if call.tool in {"read", "grep", "list"}:
        if call.path and is_secret_path(call.path):
            return Risk(
                ASK,
                "secret-read",
                "Read a secret file",
                f"Agent wants to read {call.path}.",
                _rule_key(call, "secret-read"),
            )
        return Risk(
            ALLOW,
            "read",
            "Read",
            "Project read.",
            _rule_key(call, "read"),
        )

    if call.tool == "write":
        path = call.path or ""
        if is_secret_path(path):
            return Risk(
                ASK,
                "secret-write",
                "Write a secret file",
                f"Agent wants to change {path}.",
                _rule_key(call, "secret-write"),
            )
        root = call.workspace or call.cwd
        if path and root and not _inside(path, root):
            return Risk(
                ASK,
                "write-outside",
                "Write outside the project",
                f"Agent wants to write {path}, which is outside {root}.",
                _rule_key(call, "write-outside"),
            )
        return Risk(
            ALLOW,
            "write",
            "Edit project file",
            "Write inside the project.",
            _rule_key(call, "write"),
        )

    if call.tool == "web":
        return Risk(
            ASK,
            "network",
            "Talk to the network",
            call.summary,
            _rule_key(call, "network"),
        )

    if call.tool == "subagent":
        return Risk(
            ASK,
            "subagent",
            "Spawn another agent",
            call.summary,
            _rule_key(call, "subagent"),
        )

    if call.tool == "mcp":
        return Risk(
            ASK,
            "mcp",
            "Call an external tool",
            f"{call.raw_tool}: {call.summary}",
            _rule_key(call, "mcp"),
        )

    if call.tool != "bash" or not call.command:
        # Unknown tools get a human look, not a silent pass.
        return Risk(
            ASK,
            "unknown",
            f"Use {call.raw_tool or call.tool}",
            call.summary,
            _rule_key(call, "unknown"),
        )

    cmd = _collapse(call.command)

    if _FORK_BOMB.search(cmd):
        return Risk(DENY, "fork-bomb", "Fork bomb", "Blocked. This would hang the machine.", _rule_key(call, "fork-bomb"))
    if _MKFS.search(cmd):
        return Risk(DENY, "mkfs", "Format a disk", "Blocked. mkfs destroys disks.", _rule_key(call, "mkfs"))
    if _DD_DEV.search(cmd):
        return Risk(DENY, "dd-device", "Raw write to a device", "Blocked. dd to /dev would destroy a disk.", _rule_key(call, "dd-device"))
    if _RM_RF_ROOT.search(cmd):
        return Risk(DENY, "rm-root", "Delete the filesystem", "Blocked. Recursive delete of / or $HOME.", _rule_key(call, "rm-root"))
    if _PIPE_SHELL.search(cmd):
        return Risk(DENY, "pipe-shell", "Pipe the internet into a shell", "Blocked. curl|sh is how machines get owned.", _rule_key(call, "pipe-shell"))
    if _CHMOD_ROOT.search(cmd):
        return Risk(DENY, "chmod-root", "chmod 777 /", "Blocked.", _rule_key(call, "chmod-root"))
    if _FORCE_MAIN.search(cmd):
        return Risk(DENY, "force-main", "Force-push main", "Blocked. Force-push to main/master is not silent.", _rule_key(call, "force-main"))
    if _POWER.search(cmd):
        return Risk(ASK, "power", "Power or disk command", cmd, _rule_key(call, "power"))
    if _SUDO.search(cmd):
        return Risk(ASK, "sudo", "Run as root", cmd, _rule_key(call, "sudo"))
    if _GIT_FORCE.search(cmd):
        return Risk(ASK, "git-force", "Force-push", cmd, _rule_key(call, "git-force"))
    if _GIT_PUSH.search(cmd):
        return Risk(ASK, "git-push", "git push", cmd, _rule_key(call, "git-push"))
    if _GIT_RESET_HARD.search(cmd):
        return Risk(ASK, "git-reset", "git reset --hard", cmd, _rule_key(call, "git-reset"))
    if _RM_RF.search(cmd) or _FIND_DELETE.search(cmd):
        return Risk(ASK, "destructive", "Recursive delete", cmd, _rule_key(call, "destructive"))
    if _PKG.search(cmd):
        return Risk(ASK, "packages", "Install packages", cmd, _rule_key(call, "packages"))
    if _NET.search(cmd):
        return Risk(ASK, "network", "Network from the shell", cmd, _rule_key(call, "network"))
    if _KILL.search(cmd):
        return Risk(ASK, "kill", "Signal a process", cmd, _rule_key(call, "kill"))
    if _SAFE_BASH.match(cmd):
        return Risk(ALLOW, "safe-bash", "Safe command", cmd, _rule_key(call, "safe-bash"))

    return Risk(ASK, "shell", "Run a shell command", cmd, _rule_key(call, "shell"))
