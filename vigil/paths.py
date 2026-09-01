"""Well-known directories. All local, no network."""

from __future__ import annotations

from pathlib import Path


def config_dir(home: Path) -> Path:
    return home / ".config" / "vigil"


def state_dir(home: Path) -> Path:
    return home / ".local" / "state" / "vigil"


def policy_path(home: Path) -> Path:
    return config_dir(home) / "policy.json"


def pending_dir(home: Path) -> Path:
    return state_dir(home) / "pending"


def audit_path(home: Path) -> Path:
    return state_dir(home) / "audit.jsonl"


def session_allow_path(home: Path) -> Path:
    return state_dir(home) / "session-allow.json"
