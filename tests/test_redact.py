"""Credential redaction. Marketplace #7376: do not persist raw secrets."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from vigil.audit import append, tail
from vigil.call import ToolCall
from vigil.dossier import read_last_denied, write_last_denied
from vigil.pending import write_request
from vigil.risk import classify
from vigil.secure import redact


SECRET = "supersecretvalue"


def bash(cmd: str) -> ToolCall:
    return ToolCall(
        event="pre_tool_use",
        tool="bash",
        raw_tool="run_terminal_command",
        command=cmd,
        path=None,
        cwd="/home/brwsk/Projects/Vigil",
        workspace="/home/brwsk/Projects/Vigil",
        session_id="s",
        permission_mode="always-approve",
        agent_hint="grok",
        raw_input={"command": cmd},
    )


class RedactFormTests(unittest.TestCase):
    def _gone(self, text: str) -> str:
        out = redact(text)
        self.assertNotIn(SECRET, out)
        self.assertIn("<redacted>", out)
        return out

    def test_authorization_bearer_unquoted(self) -> None:
        out = self._gone(f"Authorization: Bearer {SECRET}")
        self.assertIn("Authorization:", out)
        self.assertNotIn("Bearer", out)

    def test_quoted_single_header(self) -> None:
        out = self._gone(f"curl -H 'Authorization: Bearer {SECRET}' https://api.example.com")
        self.assertIn("curl", out)
        self.assertIn("https://api.example.com", out)
        self.assertIn("Authorization:", out)
        self.assertNotIn("Bearer", out)

    def test_quoted_double_header(self) -> None:
        out = self._gone(f'curl -H "Authorization: Bearer {SECRET}" https://api.example.com')
        self.assertIn("curl", out)
        self.assertIn("https://api.example.com", out)
        self.assertNotIn("Bearer", out)

    def test_unquoted_header(self) -> None:
        out = self._gone(f"curl -H Authorization: Bearer {SECRET} https://api.example.com")
        self.assertIn("curl", out)
        self.assertIn("https://api.example.com", out)
        self.assertNotIn("Bearer", out)

    def test_long_header_flag(self) -> None:
        self._gone(f"curl --header 'Authorization: Bearer {SECRET}'")

    def test_authorization_without_bearer(self) -> None:
        self._gone(f"curl -H 'Authorization: {SECRET}'")

    def test_authorization_basic_quoted_single(self) -> None:
        cred = "dXNlcjpwYXNz"
        out = redact(f"curl -H 'Authorization: Basic {cred}' https://api.example.com")
        self.assertNotIn(cred, out)
        self.assertNotIn("Basic", out)
        self.assertIn("<redacted>", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_basic_quoted_double(self) -> None:
        cred = "dXNlcjpwYXNz"
        out = redact(f'curl -H "Authorization: Basic {cred}" https://api.example.com')
        self.assertNotIn(cred, out)
        self.assertNotIn("Basic", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_basic_unquoted(self) -> None:
        cred = "dXNlcjpwYXNz"
        out = redact(f"curl -H Authorization: Basic {cred} https://api.example.com")
        self.assertNotIn(cred, out)
        self.assertNotIn("Basic", out)
        self.assertIn("<redacted>", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_digest_quoted(self) -> None:
        user = "Mufasa"
        nonce = "dcd98b7102dd2f0e8b11d0f600bfb0c093"
        response = "6629fae49393a05397450978507c4ef1"
        cmd = (
            "curl -H 'Authorization: Digest "
            f'username="{user}", realm="testrealm@host.com", '
            f'nonce="{nonce}", uri="/dir/index.html", '
            f'response="{response}"\' https://api.example.com'
        )
        out = redact(cmd)
        self.assertNotIn(user, out)
        self.assertNotIn(nonce, out)
        self.assertNotIn(response, out)
        self.assertNotIn("Digest", out)
        self.assertIn("<redacted>", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_digest_unquoted(self) -> None:
        user = "Mufasa"
        nonce = "dcd98b7102dd2f0e8b11d0f600bfb0c093"
        cmd = (
            f'curl -H Authorization: Digest username="{user}", '
            f'nonce="{nonce}" https://api.example.com'
        )
        out = redact(cmd)
        self.assertNotIn(user, out)
        self.assertNotIn(nonce, out)
        self.assertIn("<redacted>", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_token_quoted(self) -> None:
        cred = "tok_live_abc123secret"
        out = redact(f"curl -H 'Authorization: Token {cred}' https://api.example.com")
        self.assertNotIn(cred, out)
        self.assertNotIn("Token", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_token_unquoted(self) -> None:
        cred = "tok_live_abc123secret"
        out = redact(f"curl -H Authorization: Token {cred} https://api.example.com")
        self.assertNotIn(cred, out)
        self.assertNotIn("Token", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_unknown_scheme_quoted(self) -> None:
        cred = "s3cretfragment.xyz"
        out = redact(f"curl -H 'Authorization: HOBA {cred}' https://api.example.com")
        self.assertNotIn(cred, out)
        self.assertNotIn("HOBA", out)
        self.assertIn("https://api.example.com", out)

    def test_authorization_unknown_scheme_unquoted(self) -> None:
        cred = "s3cretfragment.xyz"
        out = redact(f"curl -H Authorization: HOBA {cred} https://api.example.com")
        self.assertNotIn(cred, out)
        self.assertNotIn("HOBA", out)
        self.assertIn("https://api.example.com", out)

    def test_password_flag_separated(self) -> None:
        out = self._gone(f"cmd --password {SECRET}")
        self.assertIn("--password", out)

    def test_token_flag_separated(self) -> None:
        self._gone(f"cmd --token {SECRET}")

    def test_password_flag_equals(self) -> None:
        self._gone(f"cmd --password={SECRET}")

    def test_token_flag_equals(self) -> None:
        self._gone(f"cmd --token={SECRET}")

    def test_api_key_flag_separated(self) -> None:
        self._gone(f"cmd --api-key {SECRET}")

    def test_quoted_flag_value(self) -> None:
        out = redact(f"cmd --password '{SECRET} with spaces'")
        self.assertNotIn(SECRET, out)
        self.assertIn("<redacted>", out)
        self.assertIn("cmd", out)

    def test_assignment_password(self) -> None:
        self._gone(f"password={SECRET}")

    def test_assignment_token_colon(self) -> None:
        self._gone(f"token: {SECRET}")

    def test_env_style_key(self) -> None:
        self._gone(f"GITHUB_TOKEN={SECRET}")

    def test_two_secrets_in_one_command(self) -> None:
        out = redact(
            f"curl --token {SECRET} -H 'Authorization: Bearer {SECRET}' --password {SECRET}"
        )
        self.assertNotIn(SECRET, out)
        self.assertEqual(out.count("<redacted>"), 3)

    def test_leaves_ordinary_commands(self) -> None:
        cmd = "git push origin main && pytest tests/test_token.py"
        self.assertEqual(redact(cmd), cmd)

    def test_leaves_content_type_header(self) -> None:
        cmd = "curl -H 'Content-Type: application/json' https://example.com"
        self.assertEqual(redact(cmd), cmd)

    def test_pem_still_redacted(self) -> None:
        pem = "-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----"
        self.assertIn("<redacted-pem>", redact(pem))
        self.assertNotIn("BEGIN PRIVATE KEY", redact(pem))


class RedactPersistenceTests(unittest.TestCase):
    def test_audit_strips_command_secret(self) -> None:
        cmd = f"curl -H 'Authorization: Bearer {SECRET}'"
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            append(home, {"event": "deny", "command": cmd, "summary": cmd, "reason": cmd})
            rows = tail(home, limit=5)
            self.assertEqual(len(rows), 1)
            blob = json.dumps(rows[0])
            self.assertNotIn(SECRET, blob)
            self.assertIn("<redacted>", rows[0]["command"])
            self.assertIn("<redacted>", rows[0]["summary"])
            self.assertIn("<redacted>", rows[0]["reason"])

    @patch("vigil.ghosts.shutil.which", return_value=None)
    def test_pending_strips_command_secret(self, _which: object) -> None:
        cmd = f"curl -H 'Authorization: Bearer {SECRET}' --password {SECRET}"
        call = bash(cmd)
        risk = classify(call)
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = write_request(
                home,
                req_id="fix7376",
                call=call,
                risk=risk,
                created_at="t0",
                expires_at="t1",
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            blob = json.dumps(data)
            self.assertNotIn(SECRET, blob)
            self.assertIn("<redacted>", data["command"])
            self.assertIn("<redacted>", data["summary"])
            self.assertIn("<redacted>", data["reason"])
            self.assertIn("<redacted>", data["blast"])

    def test_last_denied_strips_command_secret(self) -> None:
        cmd = f"curl --token {SECRET}"
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            write_last_denied(
                home,
                {
                    "summary": cmd,
                    "command": cmd,
                    "path": "/tmp/x",
                    "reason": "held",
                },
            )
            row = read_last_denied(home)
            assert row is not None
            blob = json.dumps(row)
            self.assertNotIn(SECRET, blob)
            self.assertIn("<redacted>", row["command"])


if __name__ == "__main__":
    unittest.main()
