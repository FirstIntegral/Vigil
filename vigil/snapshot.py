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
from vigil.claims import count_for
from vigil.classify import AgentMatch, discover
from vigil.dossier import summarize
from vigil.enrich import enrich_all
from vigil.envelope import DEFAULT_ENVELOPE
from vigil.folders import list_folders
from vigil.install import hooks_installed
from vigil.lid import sync as lid_sync
from vigil.passport import envelope_for, list_passports, make_id, reap, upsert
from vigil.pending import list_pending
from vigil.policy import load_policy
from vigil.proc import Proc, iter_procs


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def session_dict(match: AgentMatch, *, home: Path | None = None, host: str = "") -> dict[str, Any]:
    proc = match.proc
    cwd = proc.cwd or ""
    agent = match.spec.id
    session_id = match.session_id or ""
    passport_id = make_id(agent, session_id, proc.pid)
    envelope = DEFAULT_ENVELOPE
    claims_n = 0
    if home is not None:
        paper = upsert(
            home,
            agent=agent,
            session_id=session_id,
            pid=proc.pid,
            cwd=cwd,
            model=match.model or "",
            host=host,
        )
        passport_id = str(paper.get("id") or passport_id)
        envelope = str(paper.get("envelope") or envelope_for(home, agent=agent, session_id=session_id, cwd=cwd))
        claims_n = count_for(home, passport_id)
    return {
        "id": f"{agent}:{proc.pid}",
        "passportId": passport_id,
        "agent": agent,
        "displayName": match.spec.display,
        "pid": proc.pid,
        "cwd": cwd,
        "project": match.project or (Path(cwd).name if cwd else None),
        "model": match.model,
        "sessionId": session_id or None,
        "gitBranch": match.git_branch,
        "status": match.status,
        "openedAt": match.opened_at,
        "rssBytes": proc.rss_bytes,
        "killable": True,
        "matchedBin": match.matched_bin,
        "envelope": envelope,
        "claims": claims_n,
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
    hostname = host or socket.gethostname()
    sessions = [session_dict(m, home=home, host=hostname) for m in matches]
    live_pids = {int(s["pid"]) for s in sessions}
    reap(home, live_pids)
    running = sum(1 for s in sessions if s["status"] == "running")
    pending = list_pending(home)
    lid = lid_sync(home)
    policy = load_policy(home)
    mode = policy.effective_mode()
    helper = str(Path(__file__).resolve().parent.parent / "bin" / "vigil")
    hooks = hooks_installed(home, helper)
    dossier = summarize(home)
    incident = any(row.get("kind") in {"away", "surprise"} for row in pending)
    return {
        "schemaVersion": SNAPSHOT_SCHEMA,
        "pluginId": PLUGIN_ID,
        "collectorVersion": __version__,
        "generatedAt": generated_at or _iso_now(),
        "host": hostname,
        "sessions": sessions,
        "passports": list_passports(home),
        "pending": pending,
        "mode": mode,
        "alert": policy.alert,
        "trustUntil": policy.trust_until,
        "trustRoot": policy.trust_root,
        "lid": lid,
        "frozen": mode == "frozen",
        "incident": incident,
        "hooks": hooks,
        "audit": audit_tail(home, limit=20),
        "dossier": dossier,
        "brief": dossier,
        "tickets": {
            "allow": sorted(policy.allow_keys),
            "deny": sorted(policy.deny_keys),
        },
        "folders": list_folders(home),
        "trustUntilLock": policy.trust_until_lock,
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
