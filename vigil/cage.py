"""Optional net-only cage for `vigil spawn --exec --cage`.

Full filesystem Landlock/bwrap is a fake jail if we get the allowlist
wrong. This only unshares the network namespace. Wayland is a unix
socket and still works. Fail closed when --cage is requested and bwrap
is missing. Default spawn does not cage.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any


class CageRefused(Exception):
    """Caller asked for a cage we cannot honour."""


def bwrap_bin() -> str | None:
    return shutil.which("bwrap")


def plan(command: list[str], *, cwd: str, net: bool = False) -> dict[str, Any]:
    """Build argv. net=True keeps the network (no cage). net=False unshares it."""
    if not command:
        raise CageRefused("empty command")
    helper = bwrap_bin()
    if helper is None:
        raise CageRefused("bwrap is not installed. Envelope still applies at the gate.")
    argv = [
        helper,
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
    ]
    if not net:
        argv.append("--unshare-net")
    argv.extend(["--chdir", cwd, "--", *command])
    return {
        "ok": True,
        "argv": argv,
        "cwd": cwd,
        "unshareNet": not net,
        "helper": helper,
        "note": "Filesystem is not jailed. Only the network namespace is dropped.",
    }


def exec_caged(command: list[str], *, cwd: str, net: bool = False) -> None:
    spec = plan(command, cwd=cwd, net=net)
    os.chdir(cwd)
    argv = spec["argv"]
    os.execvp(argv[0], argv)
