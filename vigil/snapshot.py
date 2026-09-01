"""Build the JSON snapshot the QML service consumes."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vigil import PLUGIN_ID, SNAPSHOT_SCHEMA, __version__
from vigil.audit import tail as audit_tail
from vigil.classify import AgentMatch, discover
from vigil.dossier import summarize
from vigil.enrich import enrich_all
from vigil.install import hooks_installed
from vigil.pending import list_pending
from vigil.policy import load_policy
from vigil.proc import Proc, iter_procs


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_dict(match: AgentMatch) -> dict[str, Any]:
    proc = match.proc
    cwd = proc.cwd
    return {
        "id": f"{match.spec.id}:{proc.pid}",
        "agent": match.spec.id,
        "displayName": match.spec.display,
        "pid": proc.pid,
        "cwd": cwd,
        "project": match.project or (Path(cwd).name if cwd else None),
        "model": match.model,
        "sessionId": match.session_id,
        "gitBranch": match.git_branch,
        "status": match.status,
        "openedAt": match.opened_at,
        "rssBytes": proc.rss_bytes,
        "killable": True,
        "matchedBin": match.matched_bin,
    }


def build_snapshot(
    procs: list[Proc],
    *,
    home: Path,
    uid: int | None,
    host: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    matches = enrich_all(discover(procs, uid=uid), home)
    sessions = [session_dict(m) for m in matches]
    running = sum(1 for s in sessions if s["status"] == "running")
    pending = list_pending(home)
    policy = load_policy(home)
    mode = policy.effective_mode()
    helper = str(Path(__file__).resolve().parent.parent / "bin" / "vigil")
    hooks = hooks_installed(home, helper)
    dossier = summarize(home)
    return {
        "schemaVersion": SNAPSHOT_SCHEMA,
        "pluginId": PLUGIN_ID,
        "collectorVersion": __version__,
        "generatedAt": generated_at or _iso_now(),
        "host": host or socket.gethostname(),
        "sessions": sessions,
        "pending": pending,
        "mode": mode,
        "alert": policy.alert,
        "trustUntil": policy.trust_until,
        "trustRoot": policy.trust_root,
        "frozen": mode == "frozen",
        "hooks": hooks,
        "audit": audit_tail(home, limit=20),
        "dossier": dossier,
        "totals": {
            "agents": len(sessions),
            "running": running,
            "waiting": len(pending),
            "frozen": mode == "frozen",
            "todayUsd": None,
        },
    }


def collect(
    *,
    proc_root: Path | str = "/proc",
    home: Path | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    home_path = Path(home) if home is not None else Path.home()
    if uid is None:
        uid = os.getuid()
    return build_snapshot(iter_procs(proc_root), home=home_path, uid=uid)


def dumps(snapshot: dict[str, Any], *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(snapshot, indent=2, sort_keys=False) + "\n"
    return json.dumps(snapshot, separators=(",", ":")) + "\n"


def write_snapshot(snapshot: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dumps(snapshot), encoding="utf-8")
    tmp.replace(path)


def default_state_path(home: Path | None = None) -> Path:
    base = Path(home) if home is not None else Path.home()
    return base / ".local" / "state" / "vigil" / "snapshot.json"
