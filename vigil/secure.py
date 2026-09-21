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

_PLACEHOLDER = "<redacted>"
_PEM_PLACEHOLDER = "<redacted-pem>"

# Names the old regex already treated as credentials, plus env-style
# prefixes (GITHUB_TOKEN, AWS_SECRET_ACCESS_KEY).
_NAME = r"api[_-]?key|authorization|bearer|secret|password|passwd|token"
_QUOTED = r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\""
_ATOM = rf"(?:{_QUOTED}|[^\s]+)"
_KEYWORD = re.compile(rf"(?i)\b(?:{_NAME})\b")
_SECRET_PARTS = frozenset(
    {
        "authorization",
        "bearer",
        "secret",
        "password",
        "passwd",
        "token",
        "apikey",
    }
)

_PEM = re.compile(
    r"-----BEGIN [A-Z0-9 ]+-----.*?-----END [A-Z0-9 ]+-----",
    re.DOTALL,
)
_QUOTED_RE = re.compile(rf"({_QUOTED})")
# One argv after -H/--header. Do not special-case Bearer here: a
# scheme-plus-one-atom grab leaves Digest params (and non-Bearer
# schemes) on the command. _AUTH consumes the full header value.
_HEADER_FLAG = re.compile(rf"(?i)(-H|--header)(\s+|=)({_ATOM})")
_SECRET_FLAG = re.compile(rf"(?i)(--(?:{_NAME}))(\s+|=)({_ATOM})")
# Complete Authorization value, any scheme (Basic, Bearer, Digest,
# Token, unknown). Stop before the next CLI flag or a URL argv.
_AUTH_END = r"(?=\s+(?:-+[A-Za-z]|https?://)|$)"
_AUTH = re.compile(
    rf"(?i)\b(authorization)(\s*[:=]\s*)({_QUOTED}|.+?){_AUTH_END}"
)
_ASSIGN = re.compile(rf"(?i)\b([A-Za-z_][A-Za-z0-9_-]*)(\s*[:=]\s*)({_ATOM})")
_BEARER = re.compile(rf"(?i)\b(Bearer)(\s+)({_ATOM})")


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


def _key_is_secret(key: str) -> bool:
    parts = [p for p in re.split(r"[-_]", key.lower()) if p]
    if "api" in parts and "key" in parts:
        return True
    return any(p in _SECRET_PARTS for p in parts)


def _has_secret_keyword(text: str) -> bool:
    return bool(_KEYWORD.search(text))


def _flag_repl(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{_PLACEHOLDER}"


def _auth_repl(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{_PLACEHOLDER}"


def _assign_repl(match: re.Match[str]) -> str:
    key = match.group(1)
    # Authorization values are consumed whole by _AUTH, any scheme.
    # Re-matching the first word would leave the credential behind.
    if key.lower() == "authorization":
        return match.group(0)
    if not _key_is_secret(key):
        return match.group(0)
    return f"{key}{match.group(2)}{_PLACEHOLDER}"


def _bearer_repl(match: re.Match[str]) -> str:
    value = match.group(3)
    if value == _PLACEHOLDER:
        return match.group(0)
    return f"{match.group(1)}{match.group(2)}{_PLACEHOLDER}"


def _redact_unquoted(text: str) -> str:
    def header_repl(match: re.Match[str]) -> str:
        opt, sep, raw = match.group(1), match.group(2), match.group(3)
        quote = ""
        inner = raw
        if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "'\"":
            quote = raw[0]
            inner = raw[1:-1]
        if not _has_secret_keyword(inner):
            return match.group(0)
        scrubbed = _redact_unquoted_body(inner)
        if quote:
            return f"{opt}{sep}{quote}{scrubbed}{quote}"
        return f"{opt}{sep}{scrubbed}"

    out = _HEADER_FLAG.sub(header_repl, text)
    return _redact_unquoted_body(out)


def _redact_unquoted_body(text: str) -> str:
    out = _SECRET_FLAG.sub(_flag_repl, text)
    out = _AUTH.sub(_auth_repl, out)
    out = _ASSIGN.sub(_assign_repl, out)
    return _BEARER.sub(_bearer_repl, out)


def _redact_quoted(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        blob = match.group(1)
        inner = blob[1:-1]
        if not _has_secret_keyword(inner):
            return blob
        return blob[0] + _redact_unquoted_body(inner) + blob[0]

    return _QUOTED_RE.sub(repl, text)


def redact(text: str) -> str:
    """Strip credentials from command text before it is stored or shown.

    Handles `password=…`, `--token SECRET`, quoted and unquoted
    `Authorization` headers of any scheme, `Bearer` tokens, env-style
    keys, and PEM blocks.
    """
    if not text:
        return ""
    out = _PEM.sub(_PEM_PLACEHOLDER, text)
    out = _redact_quoted(out)
    return _redact_unquoted(out)


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
