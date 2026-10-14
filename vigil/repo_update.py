"""Fast-forward check for the installed Vigil checkout.

The panel asks GitHub whether origin HEAD is ahead. A human click then runs
the same command as `omarchy plugin update brwsk.vigil --yes`. Agents never
get here: the CLI refuses them, and the risk rules card the command.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from vigil import PLUGIN_ID

FETCH_TIMEOUT_SEC = 20
APPLY_TIMEOUT_SEC = 120
UPDATE_ARGV = ["omarchy", "plugin", "update", PLUGIN_ID, "--yes"]


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -oBatchMode=yes")
    return env


def _run(root: Path, args: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_git_env(),
    )


def _blank(state: str, *, ok: bool = True, error: str = "") -> dict[str, object]:
    return {
        "ok": ok,
        "state": state,
        "behind": 0,
        "dirty": False,
        "head": "",
        "upstream": "",
        "error": error,
    }


def inspect(root: Path) -> dict[str, object]:
    """Fetch origin HEAD and say whether this checkout can fast-forward."""
    root = root.resolve()
    if not (root / ".git").exists():
        return _blank("notgit", ok=False, error="not a git checkout")
    try:
        fetched = _run(root, ["fetch", "--quiet", "origin", "HEAD"], timeout=FETCH_TIMEOUT_SEC)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return _blank("offline", ok=False, error=str(exc))
    if fetched.returncode != 0:
        err = (fetched.stderr or fetched.stdout or "fetch failed").strip()
        line = err.splitlines()[-1] if err else "fetch failed"
        return _blank("offline", ok=False, error=line)
    head = _run(root, ["rev-parse", "HEAD"], timeout=10)
    upstream = _run(root, ["rev-parse", "FETCH_HEAD"], timeout=10)
    if head.returncode != 0 or upstream.returncode != 0:
        return _blank("offline", ok=False, error="could not read HEAD")
    head_s = head.stdout.strip()
    up_s = upstream.stdout.strip()
    dirty_run = _run(root, ["status", "--porcelain", "--untracked-files=no"], timeout=10)
    report = _blank("current")
    report["head"] = head_s
    report["upstream"] = up_s
    report["dirty"] = bool((dirty_run.stdout or "").strip())
    if head_s == up_s:
        return report
    behind = _run(root, ["merge-base", "--is-ancestor", head_s, up_s], timeout=10)
    if behind.returncode == 0:
        count = _run(root, ["rev-list", "--count", f"{head_s}..{up_s}"], timeout=10)
        try:
            report["behind"] = int((count.stdout or "0").strip() or "0")
        except ValueError:
            report["behind"] = 0
        report["state"] = "behind"
        return report
    ahead = _run(root, ["merge-base", "--is-ancestor", up_s, head_s], timeout=10)
    report["state"] = "ahead" if ahead.returncode == 0 else "diverged"
    return report


def _omarchy(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=APPLY_TIMEOUT_SEC,
    )


def apply_update(root: Path, *, runner=None) -> dict[str, object]:
    """Fast-forward the installed plugin. The caller already refused agents."""
    status = inspect(root)
    state = str(status["state"])
    if state in {"offline", "notgit"}:
        return {"ok": False, "state": state, "error": status["error"] or state}
    if state != "behind":
        return {"ok": False, "state": state, "error": "no fast-forward update"}
    if status["dirty"]:
        return {
            "ok": False,
            "state": "behind",
            "dirty": True,
            "error": "local edits block the update",
        }
    run = runner or _omarchy
    try:
        result = run(list(UPDATE_ARGV))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "state": "behind", "error": str(exc)}
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "update failed").strip()
        line = err.splitlines()[-1] if err else "update failed"
        return {"ok": False, "state": "behind", "error": line}
    return {"ok": True, "state": "current", "error": ""}
