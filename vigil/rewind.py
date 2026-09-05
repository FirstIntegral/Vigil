"""Undo this session's writes. Git-tracked project files + config CoW.

Never follows a symlink out of the project. Never touches secret paths.
Does not delete files the agent created. Not a backup product.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from vigil.audit import tail as audit_tail
from vigil.paths import cow_dir
from vigil.risk import is_secret_path, path_inside
from vigil.secure import ensure_private_dir

_CONFIG_PARTS = (".config/omarchy", ".config/hypr", ".config/vigil")


def cow_key(path: str) -> str:
    return hashlib.sha256(path.encode("utf-8")).hexdigest()


def should_cow(path: str, home: Path) -> bool:
    if not path:
        return False
    try:
        resolved = Path(path).expanduser()
        if not resolved.is_absolute():
            return False
        text = str(resolved)
        home_s = str(home)
        return any(f"{home_s}/{part}" in text or text.endswith(part) for part in _CONFIG_PARTS) or any(
            part in text for part in _CONFIG_PARTS
        )
    except (OSError, ValueError):
        return False


def snapshot_file(home: Path, path: str) -> Path | None:
    """Copy path to CoW once. Skip secrets. Skip missing files (new file)."""
    if not path or is_secret_path(path):
        return None
    src = Path(path)
    if not src.is_file() or src.is_symlink():
        # Still record "did not exist" so we know it was new — do not delete on rewind.
        return None
    try:
        real = src.resolve()
    except OSError:
        return None
    if is_secret_path(str(real)):
        return None
    dest_dir = ensure_private_dir(cow_dir(home))
    dest = dest_dir / cow_key(str(real))
    if dest.exists():
        return dest
    try:
        shutil.copy2(real, dest)
        meta = dest.with_suffix(".path")
        meta.write_text(str(real) + "\n", encoding="utf-8")
        os.chmod(dest, 0o600)
        os.chmod(meta, 0o600)
    except OSError:
        return None
    return dest


def _git_root(path: Path) -> Path | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    root = Path((out.stdout or "").strip())
    return root if root.is_dir() else None


def _restore_git(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--error-unmatch", str(rel)],
            check=False,
            capture_output=True,
            timeout=2,
        )
        if listed.returncode != 0:
            return False
        out = subprocess.run(
            ["git", "-C", str(root), "checkout", "--", str(rel)],
            check=False,
            capture_output=True,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0


def _restore_cow(home: Path, path: str) -> bool:
    src = cow_dir(home) / cow_key(str(Path(path).resolve())) if Path(path).exists() else None
    if src is None or not src.is_file():
        # Try the key of the given string without resolve.
        src = cow_dir(home) / cow_key(path)
    if not src.is_file():
        return False
    dest = Path(path)
    if dest.is_symlink() or is_secret_path(path):
        return False
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError:
        return False
    return True


def files_from_audit(home: Path, limit: int = 80) -> list[str]:
    seen: list[str] = []
    have: set[str] = set()
    for row in audit_tail(home, limit=400):
        path = row.get("path")
        if not isinstance(path, str) or not path or path in have:
            continue
        if is_secret_path(path):
            continue
        have.add(path)
        seen.append(path)
        if len(seen) >= limit:
            break
    return seen


def files_for_session(home: Path, session_id: str, limit: int = 80) -> list[str]:
    if not session_id:
        return files_from_audit(home, limit=limit)
    seen: list[str] = []
    have: set[str] = set()
    for row in audit_tail(home, limit=400):
        if str(row.get("sessionId") or "") != session_id:
            continue
        path = row.get("path")
        if not isinstance(path, str) or not path or path in have:
            continue
        if is_secret_path(path):
            continue
        have.add(path)
        seen.append(path)
        if len(seen) >= limit:
            break
    return seen


def rewind(
    home: Path,
    project_root: str = "",
    paths: list[str] | None = None,
    session_id: str = "",
) -> dict[str, Any]:
    if paths is not None:
        targets = paths
    elif session_id:
        targets = files_for_session(home, session_id)
    else:
        targets = files_from_audit(home)
    restored: list[str] = []
    skipped: list[str] = []
    root = Path(project_root).resolve() if project_root else None
    git_root = _git_root(root) if root else None
    for raw in targets:
        if is_secret_path(raw):
            skipped.append(raw)
            continue
        path = Path(raw)
        if git_root is not None:
            try:
                resolved = path if path.is_absolute() else git_root / path
                if not path_inside(str(resolved), str(git_root)):
                    skipped.append(raw)
                    continue
                if _restore_git(resolved, git_root):
                    restored.append(raw)
                    continue
            except (OSError, ValueError):
                pass
        if _restore_cow(home, raw):
            restored.append(raw)
        else:
            skipped.append(raw)
    return {"ok": True, "restored": restored, "skipped": skipped}
