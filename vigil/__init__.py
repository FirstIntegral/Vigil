"""Vigil — permission broker for coding agents on Omarchy."""

__version__ = "0.6.2"
PLUGIN_ID = "xyz.brwsk.vigil"
SNAPSHOT_SCHEMA = 1
POLICY_SCHEMA = 1
# Card window. Harness timeout must exceed this so Vigil denies before
# Grok/OpenCode fail-open. Was 90 / 120; glass 2026-09-05 felt short.
ASK_WAIT_SEC = 300
HOOK_TIMEOUT_SEC = 330
