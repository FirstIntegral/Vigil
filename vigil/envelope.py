"""Per-agent cage. Global mode is the human temperature; envelope is the lease."""

from __future__ import annotations

from dataclasses import replace

from vigil.call import ToolCall
from vigil.risk import ASK, DENY, Risk

ENVELOPES = ("seatbelt", "project", "hermit", "desktop", "read")
DEFAULT_ENVELOPE = "seatbelt"

# Classes that a given envelope still holds even when global mode is seatbelt.
_HOLD = {
    "project": frozenset(
        {
            "write-outside",
            "secret-write",
            "secret-read",
            "plugin-inject",
            "desktop-kill",
            "self-approve",
        }
    ),
    "hermit": frozenset(
        {
            "network",
            "mcp",
            "web",
            "write-outside",
            "secret-write",
            "secret-read",
            "desktop-kill",
            "desktop",
            "plugin-inject",
            "packages",
            "subagent",
            "self-approve",
        }
    ),
    "read": frozenset(
        {
            "write",
            "write-outside",
            "secret-write",
            "shell",
            "destructive",
            "git-push",
            "git-force",
            "git-reset",
            "packages",
            "network",
            "mcp",
            "sudo",
            "desktop",
            "desktop-kill",
            "plugin-inject",
            "subagent",
            "self-approve",
        }
    ),
    "desktop": frozenset(
        {
            "desktop-kill",
            "plugin-inject",
            "self-approve",
            "secret-write",
        }
    ),
    "seatbelt": frozenset(),
}


def normalize(name: str) -> str:
    key = (name or "").strip().lower()
    return key if key in ENVELOPES else DEFAULT_ENVELOPE


def cycle(current: str) -> str:
    cur = normalize(current)
    return ENVELOPES[(ENVELOPES.index(cur) + 1) % len(ENVELOPES)]


def apply_envelope(name: str, risk: Risk, call: ToolCall) -> Risk:
    """Upgrade a call that leaves this envelope into a held card."""
    env = normalize(name)
    hold_set = _HOLD.get(env, frozenset())
    class_id = risk.class_id
    if class_id.startswith("mcp:"):
        class_id = "mcp"
    held = class_id in hold_set or risk.class_id in hold_set
    if env == "project" and call.tool == "write":
        if risk.class_id in {"write-outside", "secret-write"}:
            held = True
    if env == "read" and call.tool in {"write", "edit"}:
        held = True
    if not held:
        return risk
    title = risk.title
    reason = risk.reason + f" Envelope `{env}` holds this."
    decision = risk.decision if risk.decision == DENY else ASK
    return replace(risk, decision=decision, hold=True, title=title, reason=reason)
