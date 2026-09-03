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
from vigil.claims import claim as take_claim
from vigil.claims import conflict as claim_conflict
from vigil.envelope import apply_envelope
from vigil.passport import envelope_for, make_id, upsert as upsert_passport
from vigil.pending import write_surprise
from vigil.rewind import should_cow, snapshot_file
from vigil.risk import ALLOW, ASK, CRITICAL_CLASSES, DENY, Risk, classify, is_secret_path, path_inside

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


def apply_mode(mode: str, classified: str, hold: bool = False) -> str:
    """YOLO-friendly seatbelt: only deadly (or envelope-held) calls wait."""
    if mode == "off":
        return ALLOW
    if mode == "frozen":
        return DENY
    if mode == "seatbelt":
        return ASK if classified == DENY or hold else ALLOW
    if hold and classified == ALLOW:
        return ASK
    return classified


def _apply_human(action: str, policy: Policy, risk: Risk, session_id: str) -> tuple[str, str]:
    if action == "allow":
        return ALLOW, "Allowed once."
    if action in {"session", "always"} and risk.class_id in CRITICAL_CLASSES:
        return ALLOW, "Allowed once. Deadly classes cannot be ticketed."
    if action == "session":
        policy.remember_session(session_id, risk.rule_key)
        return ALLOW, "Allowed for this session."
    if action == "always":
        policy.remember_allow(risk.rule_key)
        return ALLOW, "Ticket minted for this agent, project, and class."
    if action == "deny-always":
        policy.remember_deny(risk.rule_key)
        return DENY, "Ticket denied for this agent, project, and class."
    if action in {"rewind", "unfreeze"}:
        return DENY, "Not a tool-call action."
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
                    "sessionId": call.session_id,
                },
            )
        if _surprise(call):
            pol.freeze()
            save_policy(home, pol)
            write_surprise(
                home,
                summary=call.summary,
                path=call.path or "",
                agent=call.agent_hint,
            )
            notify(
                "Vigil · incident",
                "An allowed write landed on a secret or outside the project.",
                urgency="critical",
                alert=pol.alert,
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
    env_name = envelope_for(
        home, agent=call.agent_hint, session_id=call.session_id, cwd=call.workspace or call.cwd
    )
    risk = apply_envelope(env_name, risk, call)
    passport_id = make_id(call.agent_hint, call.session_id, None)
    if call.path and call.tool == "write":
        held = claim_conflict(home, call.path, passport_id)
        if held:
            from dataclasses import replace

            risk = replace(
                risk,
                decision=ASK,
                hold=True,
                class_id="claim",
                title="Another agent holds this file",
                reason=f"{held.get('agent') or 'another agent'} already writes {call.path}.",
            )
    override = pol.key_override(risk, call.session_id)
    effective = "seatbelt" if pol.is_trusted(call.cwd, now) and mode == "ask" else mode
    decision = override or apply_mode(effective, risk.decision, hold=risk.hold)
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
            envelope=env_name,
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

    if decision == ALLOW:
        upsert_passport(
            home,
            agent=call.agent_hint,
            session_id=call.session_id,
            cwd=call.workspace or call.cwd,
        )
        if call.tool == "write" and call.path:
            take_claim(home, call.path, passport_id, agent=call.agent_hint)
            if should_cow(call.path, home):
                snapshot_file(home, call.path)

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
                "ticket": risk.rule_key,
                "envelope": env_name,
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


def _surprise(call) -> bool:
    """Allowed write whose real path is a secret or escaped the project."""
    if call.tool != "write" or not call.path:
        return False
    if is_secret_path(call.path):
        return False
    root = call.workspace or call.cwd
    try:
        from pathlib import Path as P

        real = str(P(call.path).resolve())
    except OSError:
        return False
    if is_secret_path(real):
        return True
    if root and (not path_inside(real, root)) and path_inside(call.path, root):
        return True
    return False


def gate_payload(raw: str | bytes | dict[str, Any], *, home: Path, **kwargs: Any) -> GateResult:
    if isinstance(raw, dict):
        data = raw
    else:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        text = text.strip()
        if not text:
            resp = hook_response(DENY, "empty hook payload")
            return GateResult(DENY, "empty hook payload", None, False, resp)
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
