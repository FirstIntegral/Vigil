"""Omarchy alerts: bar, toast, or both.

Default is `both` — Omarchy's top bar *and* its notification daemon.
`t` cycles bar / toast / both. Tests and `VIGIL_SILENT=1` never toast.

Toasts use the same eye as the bar (`omarchy notification send -g`), not
the generic `security-high` shield. That shield is a dark tile in the
toast's 40px slot.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

ALERTS = ("bar", "toast", "both")
DEFAULT_ALERT = "both"
GLYPH_EYE = "󰈈"
GLYPH_ALERT = "󰀪"


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


def toast_command(title: str, body: str, *, urgency: str = "normal", expire_ms: int = 8000) -> list[str] | None:
    """Argv for a Vigil toast. Eye glyph, never security-high."""
    level = {"low": "low", "normal": "normal", "critical": "critical"}.get(urgency, "normal")
    glyph = GLYPH_ALERT if level == "critical" else GLYPH_EYE
    helper = shutil.which("omarchy-notification-send")
    if helper:
        return [
            helper,
            "--app-name",
            "Vigil",
            "-g",
            glyph,
            "-u",
            level,
            "-t",
            str(expire_ms),
            title,
            body,
        ]
    if shutil.which("notify-send"):
        return [
            "notify-send",
            "--app-name=Vigil",
            f"--urgency={level}",
            f"--expire-time={expire_ms}",
            title,
            body,
        ]
    return None


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
    cmd = toast_command(title, body, urgency=urgency, expire_ms=expire_ms)
    if not cmd:
        return False
    try:
        subprocess.run(
            cmd,
            check=False,
            timeout=2,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True
