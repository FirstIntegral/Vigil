"""Short card about this computer. Agents may read it. It is not a classifier."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from vigil.paths import machine_path
from vigil.secure import write_private


def render(*, home: Path | None = None, user: str = "", host: str = "") -> str:
    home_path = Path(home) if home is not None else Path.home()
    who = user or os.environ.get("USER") or os.environ.get("LOGNAME") or "the owner"
    name = host or socket.gethostname()
    lines = [
        "# This machine",
        "",
        f"You are a coding agent on Omarchy. The human is {who}. This computer is called {name}.",
        "",
        "Vigil is the seatbelt for your tool calls. YOLO is fine for ordinary work inside the lease.",
        "If a polkit card is on screen, wait. If nobody answers, the call is denied. Silence is deny.",
        "",
        "## Off limits unless a human allowed it",
        "",
        "- `/` and the human's home directory as a delete target",
        "- `~/.ssh`, keys, `.env`, and other secrets",
        "- `~/.config/vigil` and `~/.local/state/vigil` (you cannot approve yourself)",
        "- `~/.config/omarchy/plugins` and agent hook files",
        "- The compositor (`hyprctl dispatch exit`) and `omarchy plugin add|enable|remove`",
        "- Piping the internet into a shell, formatting disks, force-pushing `main`",
        "",
        "House law is quoted on the card. It is a reminder, not a second policy engine.",
        "",
    ]
    return "\n".join(lines)


def write(home: Path) -> Path:
    path = machine_path(home)
    write_private(path, render(home=home))
    return path


def read(home: Path) -> str:
    path = machine_path(home)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return render(home=home)
    return text if text.strip() else render(home=home)
