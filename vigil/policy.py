"""Persistent allow/deny rules, freeze flag, session grants."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datetime import datetime, timezone

from vigil import ASK_WAIT_SEC, POLICY_SCHEMA
from vigil.notify import ALERTS, DEFAULT_ALERT
from vigil.paths import policy_path, session_allow_path
from vigil.risk import CRITICAL_CLASSES, Risk
from vigil.secure import write_private

MODES = ("off", "seatbelt", "ask", "frozen")
DEFAULT_MODE = "seatbelt"


def _timeout_sec(raw: dict[str, Any]) -> int:
    if "timeoutSec" not in raw:
        return ASK_WAIT_SEC
    try:
        timeout_i = int(raw["timeoutSec"])
    except (TypeError, ValueError):
        return ASK_WAIT_SEC
    if timeout_i == 90:
        return ASK_WAIT_SEC
    return max(5, min(ASK_WAIT_SEC, timeout_i))


def _max_subagents(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 2
    return max(0, min(32, n))


def _load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


@dataclass
class Policy:
    mode: str = DEFAULT_MODE
    previous_mode: str = DEFAULT_MODE
    frozen: bool = False
    timeout_sec: int = ASK_WAIT_SEC
    allow_keys: set[str] = field(default_factory=set)
    deny_keys: set[str] = field(default_factory=set)
    session_allow: dict[str, set[str]] = field(default_factory=dict)
    alert: str = DEFAULT_ALERT
    trust_until: str = ""
    trust_root: str = ""
    trust_until_lock: bool = False
    max_subagents: int = 2
    lid: bool = True
    lid_held: bool = False
    auto_arm: bool = True

    def effective_mode(self) -> str:
        if self.frozen or self.mode == "frozen":
            return "frozen"
        if self.mode in MODES:
            return self.mode
        return DEFAULT_MODE

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode!r}")
        current = self.effective_mode()
        if mode == "frozen" and current != "frozen":
            self.previous_mode = current if current != "frozen" else DEFAULT_MODE
        self.mode = mode
        self.frozen = mode == "frozen"

    def cycle_mode(self) -> str:
        order = ("off", "seatbelt", "ask", "frozen")
        current = self.effective_mode()
        nxt = order[(order.index(current) + 1) % len(order)]
        self.set_mode(nxt)
        return nxt

    def freeze(self) -> None:
        self.set_mode("frozen")

    def unfreeze(self) -> None:
        restore = self.previous_mode if self.previous_mode in MODES and self.previous_mode != "frozen" else DEFAULT_MODE
        self.lid_held = False
        self.set_mode(restore)

    def remember_allow(self, key: str) -> None:
        self.allow_keys.add(key)
        self.deny_keys.discard(key)

    def remember_deny(self, key: str) -> None:
        self.deny_keys.add(key)
        self.allow_keys.discard(key)

    def remember_session(self, session_id: str, key: str) -> None:
        if not session_id:
            session_id = "_"
        self.session_allow.setdefault(session_id, set()).add(key)

    def set_alert(self, alert: str) -> None:
        if alert not in ALERTS:
            raise ValueError(f"unknown alert {alert!r}")
        self.alert = alert

    def cycle_alert(self) -> str:
        order = ALERTS
        idx = order.index(self.alert) if self.alert in order else 0
        self.alert = order[(idx + 1) % len(order)]
        return self.alert

    def trust_for(self, minutes: int, root: str) -> None:
        minutes = max(1, min(24 * 60, int(minutes)))
        until = datetime.now(timezone.utc).timestamp() + minutes * 60
        self.trust_until = datetime.fromtimestamp(until, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.trust_root = root.rstrip("/")
        self.trust_until_lock = False

    def trust_until_lid(self, root: str) -> None:
        self.trust_root = root.rstrip("/")
        self.trust_until = ""
        self.trust_until_lock = True

    def clear_trust(self) -> None:
        self.trust_until = ""
        self.trust_root = ""
        self.trust_until_lock = False

    def revoke(self, key: str) -> bool:
        key = str(key or "")
        if not key:
            return False
        hit = key in self.allow_keys or key in self.deny_keys
        self.allow_keys.discard(key)
        self.deny_keys.discard(key)
        return hit

    def set_lid(self, enabled: bool) -> None:
        self.lid = bool(enabled)
        if not self.lid:
            self.lid_held = False

    def is_trusted(self, cwd: str, now: datetime | None = None) -> bool:
        path = (cwd or "").rstrip("/")
        root = self.trust_root.rstrip("/")
        if not root:
            return False
        under = path == root or path.startswith(root + "/")
        if not under:
            return False
        if self.trust_until_lock:
            return True
        if not self.trust_until:
            return False
        try:
            expiry = datetime.strptime(self.trust_until, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            return False
        stamp = now or datetime.now(timezone.utc)
        return stamp < expiry

    def key_override(self, risk: Risk, session_id: str) -> str | None:
        if risk.rule_key in self.deny_keys:
            return "deny"
        if risk.class_id in CRITICAL_CLASSES:
            return None
        if risk.rule_key in self.allow_keys:
            return "allow"
        grants = self.session_allow.get(session_id)
        if grants is None:
            grants = self.session_allow.get("_")
        if grants and risk.rule_key in grants:
            return "allow"
        return None

    def to_json(self) -> dict[str, Any]:
        return {
            "schemaVersion": POLICY_SCHEMA,
            "mode": self.effective_mode(),
            "previousMode": self.previous_mode,
            "frozen": self.effective_mode() == "frozen",
            "timeoutSec": self.timeout_sec,
            "alert": self.alert if self.alert in ALERTS else DEFAULT_ALERT,
            "trustUntil": self.trust_until,
            "trustRoot": self.trust_root,
            "trustUntilLock": self.trust_until_lock,
            "maxSubagents": max(0, min(32, int(self.max_subagents))),
            "lid": self.lid,
            "lidHeld": self.lid_held,
            "autoArm": self.auto_arm,
            "allow": sorted(self.allow_keys),
            "deny": sorted(self.deny_keys),
        }

    def session_json(self) -> dict[str, list[str]]:
        return {sid: sorted(keys) for sid, keys in self.session_allow.items()}


def load_policy(home: Path) -> Policy:
    raw = _load_json(policy_path(home), {})
    if not isinstance(raw, dict):
        raw = {}
    timeout_i = _timeout_sec(raw)
    mode = str(raw.get("mode") or "")
    if mode not in MODES:
        mode = "frozen" if raw.get("frozen") else DEFAULT_MODE
    previous = str(raw.get("previousMode") or DEFAULT_MODE)
    if previous not in MODES:
        previous = DEFAULT_MODE
    policy = Policy(
        mode=mode,
        previous_mode=previous,
        frozen=mode == "frozen",
        timeout_sec=timeout_i,
        allow_keys=set(map(str, raw.get("allow") or [])),
        deny_keys=set(map(str, raw.get("deny") or [])),
        alert=str(raw.get("alert") or DEFAULT_ALERT),
        trust_until=str(raw.get("trustUntil") or ""),
        trust_root=str(raw.get("trustRoot") or ""),
        trust_until_lock=raw.get("trustUntilLock") is True,
        max_subagents=_max_subagents(raw.get("maxSubagents", 2)),
        lid=raw.get("lid", True) is not False,
        lid_held=raw.get("lidHeld") is True,
        auto_arm=raw.get("autoArm", True) is not False,
    )
    if policy.alert not in ALERTS:
        policy.alert = DEFAULT_ALERT
    sessions = _load_json(session_allow_path(home), {})
    if isinstance(sessions, dict):
        for sid, keys in sessions.items():
            if isinstance(keys, list):
                policy.session_allow[str(sid)] = set(map(str, keys))
    return policy


def save_policy(home: Path, policy: Policy) -> None:
    write_private(policy_path(home), json.dumps(policy.to_json(), indent=2) + "\n")
    write_private(session_allow_path(home), json.dumps(policy.session_json(), indent=2) + "\n")
