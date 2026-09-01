"""PreToolUse gate. Fail-closed on ask timeout. Never return harness `ask`.

Grok YOLO / Claude bypassPermissions auto-answers a harness ask. Vigil
holds the hook, pops its own overlay, then returns allow or deny.
Silence is deny. A crash here must still print valid JSON (fail-closed
for the ask path; non-pre-tool events pass through).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from vigil import ASK_WAIT_SEC
from vigil.audit import append as audit_append
from vigil.call import ToolCall, parse_envelope
from vigil.dossier import write_last_denied
from vigil.notify import notify
from vigil.pending import (
    cleanup,
    new_id,
    wait_for_decision,
    write_request,
)
from vigil.policy import Policy, load_policy, save_policy
from vigil.risk import ALLOW, ASK, DENY, Risk, classify

WaitFn = Callable[..., Any]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def hook_response(decision: str, reason: str) -> dict[str, Any]:
    """Both Grok (top-level decision) and Claude (hookSpecificOutput)."""
    return {
        "decision": decision,
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        },
    }


@dataclass(frozen=True)
class GateResult:
    decision: str
    reason: str
    risk: Risk | None
    asked: bool
    response: dict[str, Any]


def apply_mode(mode: str, classified: str) -> str:
    """YOLO-friendly seatbelt: only deadly calls are held. Off holds nothing."""
    if mode == "off":
        return ALLOW
    if mode == "frozen":
        return DENY
    if mode == "seatbelt":
        return ASK if classified == DENY else ALLOW
    return classified


def _apply_human(action: str, policy: Policy, risk: Risk, session_id: str) -> tuple[str, str]:
    if action == "allow":
        return ALLOW, "Allowed once."
    if action == "session":
        policy.remember_session(session_id, risk.rule_key)
        return ALLOW, "Allowed for this session."
    if action == "always":
        policy.remember_allow(risk.rule_key)
        return ALLOW, "Always allowed this pattern."
    if action == "deny-always":
        policy.remember_deny(risk.rule_key)
        return DENY, "Always denied this pattern."
    return DENY, "Denied."


def gate_call(
    call: ToolCall,
    *,
    home: Path,
    policy: Policy | None = None,
    wait_fn: WaitFn | None = None,
    audit: bool = True,
    clock: Callable[[], datetime] | None = None,
) -> GateResult:
    now = (clock or _now)()
    pol = policy if policy is not None else load_policy(home)

    if call.is_post_tool:
        if audit:
            audit_append(
                home,
                {
                    "event": "ran",
                    "tool": call.tool,
                    "summary": call.summary,
                    "path": call.path,
                    "agent": call.agent_hint,
                    "phase": "post",
                },
            )
        resp = hook_response(ALLOW, "logged")
        return GateResult(ALLOW, "logged", None, False, resp)

    if not call.is_pre_tool:
        resp = hook_response(ALLOW, "not a tool gate")
        return GateResult(ALLOW, "not a tool gate", None, False, resp)

    mode = pol.effective_mode()
    if mode == "frozen":
        reason = "Vigil is frozen. Unfreeze from the bar."
        if audit:
            audit_append(home, {"event": "deny", "why": "frozen", "mode": mode, "summary": call.summary})
        notify("Vigil · frozen", call.summary, urgency="critical", alert=pol.alert)
        resp = hook_response(DENY, reason)
        return GateResult(DENY, reason, None, False, resp)

    if mode == "off":
        if audit:
            audit_append(home, {"event": "allow", "why": "off", "mode": mode, "summary": call.summary, "path": call.path})
        resp = hook_response(ALLOW, "Vigil is off.")
        return GateResult(ALLOW, "Vigil is off.", None, False, resp)

    risk = classify(call)
    override = pol.key_override(risk, call.session_id)
    effective = "seatbelt" if pol.is_trusted(call.cwd, now) and mode == "ask" else mode
    decision = override or apply_mode(effective, risk.decision)
    reason = risk.reason
    asked = False

    if decision == ASK:
        asked = True
        req_id = new_id()
        wait_sec = pol.timeout_sec or ASK_WAIT_SEC
        expires = now + timedelta(seconds=wait_sec)
        write_request(
            home,
            req_id=req_id,
            call=call,
            risk=risk,
            created_at=_iso(now),
            expires_at=_iso(expires),
        )
        notify("Vigil", risk.title + "\n" + call.summary, urgency="critical", alert=pol.alert)
        waiter = wait_fn if wait_fn is not None else wait_for_decision
        human = waiter(home, req_id, wait_sec)
        cleanup(home, req_id)
        if human is None:
            decision = DENY
            reason = "No one answered. Vigil denied the call."
        else:
            decision, reason = _apply_human(human.action, pol, risk, call.session_id)
            save_policy(home, pol)

    if audit:
        audit_append(
            home,
            {
                "event": decision,
                "classId": risk.class_id,
                "tool": call.tool,
                "summary": call.summary,
                "path": call.path,
                "reason": reason,
                "asked": asked,
                "mode": mode,
                "agent": call.agent_hint,
                "sessionId": call.session_id,
            },
        )

    if decision == DENY:
        write_last_denied(
            home,
            {
                "summary": call.summary,
                "command": call.command,
                "path": call.path,
                "reason": reason,
                "classId": risk.class_id,
                "agent": call.agent_hint,
            },
        )
        notify("Vigil denied", reason + "\n" + call.summary, urgency="critical", alert=pol.alert)

    resp = hook_response(decision, reason)
    return GateResult(decision, reason, risk, asked, resp)


def gate_payload(raw: str | bytes | dict[str, Any], *, home: Path, **kwargs: Any) -> GateResult:
    if isinstance(raw, dict):
        data = raw
    else:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        text = text.strip()
        if not text:
            resp = hook_response(ALLOW, "empty hook payload")
            return GateResult(ALLOW, "empty hook payload", None, False, resp)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            resp = hook_response(DENY, "Vigil could not read the hook payload.")
            return GateResult(DENY, "unreadable payload", None, False, resp)
        if not isinstance(parsed, dict):
            resp = hook_response(DENY, "Vigil could not read the hook payload.")
            return GateResult(DENY, "unreadable payload", None, False, resp)
        data = parsed
    call = parse_envelope(data)
    return gate_call(call, home=home, **kwargs)
