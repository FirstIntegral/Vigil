"""Private files, redaction, hash-chained audit rows.

Vigil state is the user's, mode 0700/0600. Never log secrets or PEM.
No network. No cloud.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Any

_TOKEN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|secret|password|passwd|token)\s*[:=]\s*\S+"
)
_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]+-----.*?-----END [A-Z0-9 ]+-----",
    re.DOTALL,
)


def ensure_private_dir(path: Path) -> Path:
    if path.is_symlink():
        raise OSError(f"refusing symlink directory {path}")
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError(f"refusing symlink directory {path}")
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def write_private(path: Path, text: str) -> None:
    ensure_private_dir(path.parent)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(str(tmp), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        tmp = None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def redact(text: str) -> str:
    if not text:
        return ""
    out = _PEM.sub("<redacted-pem>", text)
    return _TOKEN.sub(lambda m: m.group(1) + "=<redacted>", out)


def redact_path(path: str) -> str:
    if not path:
        return ""
    from vigil.risk import is_secret_path

    if is_secret_path(path):
        return "<secret>/" + Path(path).name
    return path


def chain_row(record: dict[str, Any], prev_hash: str) -> dict[str, Any]:
    row = dict(record)
    row.pop("hash", None)
    row.pop("prev", None)
    body = json.dumps(row, separators=(",", ":"), sort_keys=True)
    digest = hashlib.sha256((prev_hash + body).encode("utf-8")).hexdigest()
    row["prev"] = prev_hash
    row["hash"] = digest
    return row


def last_hash(path: Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "0" * 64
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("hash"):
            return str(obj["hash"])
    return "0" * 64
