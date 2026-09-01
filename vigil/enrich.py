"""Attach session identity from on-disk agent state. Best-effort, local only."""

from __future__ import annotations

import json
from pathlib import Path

from vigil.classify import AgentMatch, with_fields

try:
    import tomllib
except ImportError:  # pragma: no cover — 3.11+ is the floor
    tomllib = None  # type: ignore[assignment]


def claude_project_dir_name(cwd: str) -> str:
    """Claude encodes a cwd as a directory name by swapping `/` for `-`."""
    return cwd.replace("/", "-")


def grok_model_from_config(config_text: str) -> str | None:
    if tomllib is None:
        return None
    try:
        data = tomllib.loads(config_text)
    except (tomllib.TOMLDecodeError, TypeError):
        return None
    models = data.get("models")
    if not isinstance(models, dict):
        return None
    default = models.get("default")
    return str(default) if default else None


def _load_json(path: Path) -> object | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def enrich_grok(match: AgentMatch, home: Path) -> AgentMatch:
    sessions = _load_json(home / ".grok" / "active_sessions.json")
    session_id = None
    opened_at = None
    cwd = match.proc.cwd
    if isinstance(sessions, list):
        for row in sessions:
            if not isinstance(row, dict):
                continue
            try:
                pid = int(row.get("pid"))
            except (TypeError, ValueError):
                continue
            if pid != match.proc.pid:
                continue
            sid = row.get("session_id")
            if isinstance(sid, str) and sid:
                session_id = sid
            opened = row.get("opened_at")
            if isinstance(opened, str) and opened:
                opened_at = opened
            row_cwd = row.get("cwd")
            if isinstance(row_cwd, str) and row_cwd:
                cwd = row_cwd
            break
    model = None
    config_path = home / ".grok" / "config.toml"
    try:
        model = grok_model_from_config(config_path.read_text(encoding="utf-8"))
    except OSError:
        model = None
    project = Path(cwd).name if cwd else match.project
    return with_fields(
        match,
        session_id=session_id or match.session_id,
        opened_at=opened_at or match.opened_at,
        model=model or match.model,
        project=project,
    )


def _tail_jsonl(path: Path, max_bytes: int = 65536) -> list[dict]:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
                fh.readline()  # drop the torn first line
            raw = fh.read()
    except OSError:
        return []
    rows: list[dict] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def enrich_claude(match: AgentMatch, home: Path) -> AgentMatch:
    cwd = match.proc.cwd
    if not cwd:
        return match
    project_dir = home / ".claude" / "projects" / claude_project_dir_name(cwd)
    if not project_dir.is_dir():
        return with_fields(match, project=Path(cwd).name)
    jsonl_files = sorted(
        (p for p in project_dir.glob("*.jsonl") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not jsonl_files:
        return with_fields(match, project=Path(cwd).name)
    rows = _tail_jsonl(jsonl_files[0])
    session_id = None
    model = None
    git_branch = None
    opened_at = None
    for row in reversed(rows):
        if session_id is None:
            sid = row.get("sessionId") or row.get("session_id")
            if isinstance(sid, str) and sid:
                session_id = sid
        if git_branch is None:
            branch = row.get("gitBranch")
            if isinstance(branch, str) and branch:
                git_branch = branch
        if opened_at is None:
            ts = row.get("timestamp")
            if isinstance(ts, str) and ts:
                opened_at = ts
        if model is None:
            m = row.get("model")
            if isinstance(m, str) and m:
                model = m
        if session_id and git_branch and opened_at and model:
            break
    return with_fields(
        match,
        session_id=session_id or match.session_id,
        model=model or match.model,
        git_branch=git_branch or match.git_branch,
        opened_at=opened_at or match.opened_at,
        project=Path(cwd).name,
    )


def enrich(match: AgentMatch, home: Path) -> AgentMatch:
    agent_id = match.spec.id
    if agent_id == "grok":
        return enrich_grok(match, home)
    if agent_id == "claude":
        return enrich_claude(match, home)
    cwd = match.proc.cwd
    if cwd:
        return with_fields(match, project=Path(cwd).name)
    return match


def enrich_all(matches: list[AgentMatch], home: Path) -> list[AgentMatch]:
    return [enrich(m, home) for m in matches]
