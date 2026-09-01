"""Decide whether a process is a coding agent. Pure: no I/O."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from vigil.agents import AGENTS, BINS_TO_AGENT, SKIP_COMMS, AgentSpec
from vigil.proc import Proc


@dataclass(frozen=True)
class AgentMatch:
    spec: AgentSpec
    proc: Proc
    matched_bin: str
    session_id: str | None = None
    model: str | None = None
    git_branch: str | None = None
    opened_at: str | None = None
    project: str | None = None
    status: str = "running"


def _basename(path: str | None) -> str:
    if not path:
        return ""
    # argv0 can be a path or a leading dash (login shells).
    name = Path(path).name
    if name.startswith("-") and len(name) > 1:
        name = name[1:]
    return name


def classify(proc: Proc) -> AgentMatch | None:
    """Return an AgentMatch if this process *is* an agent, else None.

    Only comm, exe basename, and argv0 basename are consulted. Later
    argv tokens are ignored so scanners (`pgrep -af grok`) do not match.
    Shells, python interpreters, and systemd-inhibit are never agents
    even if their command line mentions one.
    """
    if proc.pid <= 1:
        return None
    comm = proc.comm
    if comm in SKIP_COMMS:
        return None
    candidates = (
        comm,
        _basename(proc.exe),
        _basename(proc.cmdline[0] if proc.cmdline else ""),
    )
    for name in candidates:
        spec = BINS_TO_AGENT.get(name)
        if spec is not None:
            return AgentMatch(spec=spec, proc=proc, matched_bin=name, status=_status(proc))
    return None


def _status(proc: Proc) -> str:
    # D = uninterruptible, Z = zombie, T = stopped. The rest of the
    # live letter codes (R/S/I) mean the agent is up.
    if proc.state in {"Z"}:
        return "dead"
    if proc.state in {"T", "t"}:
        return "stopped"
    if proc.state in {"D"}:
        return "blocked"
    return "running"


def discover(procs: list[Proc], uid: int | None = None) -> list[AgentMatch]:
    """Classify a process list. Optionally keep only one uid (the user)."""
    matches: list[AgentMatch] = []
    seen_pids: set[int] = set()
    for proc in procs:
        if uid is not None and proc.uid != uid:
            continue
        match = classify(proc)
        if match is None:
            continue
        if proc.pid in seen_pids:
            continue
        seen_pids.add(proc.pid)
        matches.append(match)
    matches.sort(key=lambda m: (m.spec.id, m.proc.pid))
    return matches


def with_fields(match: AgentMatch, **kwargs: object) -> AgentMatch:
    return replace(match, **kwargs)


# Re-export for callers that want the catalogue without importing agents.
AGENT_IDS = tuple(spec.id for spec in AGENTS)
