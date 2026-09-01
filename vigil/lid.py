"""Lock the seat → freeze agents. Unlock → while-you-were-out card.

Does not replace omarchy.lock. Subscribes to the lid, nothing else.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from vigil.paths import state_dir
from vigil.policy import load_policy, save_policy
from vigil.secure import write_private


def is_locked(probe: Callable[[], bool] | None = None) -> bool:
    if probe is not None:
        return bool(probe())
    if "unittest" in sys.modules and not os.environ.get("VIGIL_TEST_LID"):
        return False
    flag = os.environ.get("VIGIL_LOCKED", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    session = os.environ.get("XDG_SESSION_ID") or "self"
    loginctl = shutil.which("loginctl")
    if loginctl:
        try:
            out = subprocess.run(
                [loginctl, "show-session", session, "-p", "LockedHint"],
                check=False,
                capture_output=True,
                text=True,
                timeout=0.4,
            )
            if "yes" in (out.stdout or "").lower():
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
    try:
        for pid in Path("/proc").iterdir():
            if not pid.name.isdigit():
                continue
            comm = (pid / "comm").read_text(encoding="utf-8", errors="replace").strip()
            if comm in {"hyprlock", "swaylock", "gtklock"}:
                return True
    except OSError:
        pass
    return False


def sync(
    home: Path,
    *,
    locked: bool | None = None,
    stamp_away: Callable[[Path], Any] | None = None,
) -> dict[str, Any]:
    """Freeze on lock. On unlock, leave frozen and stamp an away card."""
    from vigil.pending import list_pending, write_away

    locked_now = is_locked() if locked is None else bool(locked)
    policy = load_policy(home)
    away_fn = stamp_away if stamp_away is not None else write_away
    result = {
        "locked": locked_now,
        "lid": policy.lid,
        "lidHeld": policy.lid_held,
        "frozen": policy.effective_mode() == "frozen",
        "away": False,
    }
    if not policy.lid:
        return result
    if locked_now and policy.effective_mode() != "frozen":
        policy.freeze()
        policy.lid_held = True
        save_policy(home, policy)
        write_private(state_dir(home) / "lid.json", '{"locked":true}\n')
        result["lidHeld"] = True
        result["frozen"] = True
        return result
    if (not locked_now) and policy.lid_held:
        pending = list_pending(home)
        if not any(row.get("kind") == "away" for row in pending):
            away_fn(home)
            result["away"] = True
    return result
