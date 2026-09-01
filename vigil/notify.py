"""Omarchy alerts: bar, toast, or both.

Default is `both` — Omarchy's top bar *and* its notification daemon
(`notify-send` lands in `omarchy.notifications`). `t` cycles
bar / toast / both. Tests and `VIGIL_SILENT=1` never toast.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ALERTS = ("bar", "toast", "both")
DEFAULT_ALERT = "both"


def silent() -> bool:
    if os.environ.get("VIGIL_SILENT", "").strip() in {"1", "true", "yes"}:
        return True
    if "unittest" in sys.modules:
        return True
    return False


def wants_toast(alert: str | None = None) -> bool:
    if silent():
        return False
    env = os.environ.get("VIGIL_ALERT", "").strip().lower()
    channel = env or (alert or DEFAULT_ALERT)
    return channel in {"toast", "both"}


def notify(
    title: str,
    body: str,
    *,
    urgency: str = "normal",
    expire_ms: int = 8000,
    alert: str | None = None,
) -> bool:
    """Send a toast only when toasts are enabled. Returns whether it sent."""
    if not wants_toast(alert):
        return False
    if not shutil.which("notify-send"):
        return False
    level = {"low": "low", "normal": "normal", "critical": "critical"}.get(urgency, "normal")
    try:
        subprocess.run(
            [
                "notify-send",
                "--app-name=Vigil",
                f"--urgency={level}",
                f"--expire-time={expire_ms}",
                "--icon=security-high",
                title,
                body,
            ],
            check=False,
            timeout=2,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True
