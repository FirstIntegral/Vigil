"""Known coding-agent binaries Omarchy treats as first-class."""

from __future__ import annotations

from dataclasses import dataclass

# Omarchy's default-agent list (quattro) plus Cursor, which the distro
# also wires. `pi` is intentionally absent: the process name is too
# generic and would false-positive on any python/package named pi.
#
# Matching uses the process comm, the exe basename, or argv0 basename —
# never later arguments, so `pgrep -af claude` is not an agent.


@dataclass(frozen=True)
class AgentSpec:
    id: str
    display: str
    bins: tuple[str, ...]


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("grok", "Grok", ("grok",)),
    AgentSpec("claude", "Claude Code", ("claude",)),
    AgentSpec("opencode", "OpenCode", ("opencode",)),
    AgentSpec("codex", "Codex", ("codex",)),
    AgentSpec("cursor-agent", "Cursor", ("cursor-agent",)),
    AgentSpec("copilot", "Copilot CLI", ("copilot",)),
    AgentSpec("crush", "Crush", ("crush",)),
    AgentSpec("gemini", "Gemini", ("gemini",)),
    AgentSpec("omp", "Oh My Pi", ("omp",)),
    AgentSpec("agy", "Antigravity", ("agy",)),
    AgentSpec("hermes", "Hermes", ("hermes",)),
    AgentSpec("ori", "Ori", ("ori",)),
)

BINS_TO_AGENT: dict[str, AgentSpec] = {}
for _spec in AGENTS:
    for _bin in _spec.bins:
        BINS_TO_AGENT[_bin] = _spec

# Never treat these as agents, even if cmdline mentions one.
SKIP_COMMS = frozenset(
    {
        "systemd",
        "systemd-inhibit",
        "init",
        "hyprland",
        "Hyprland",
        "omarchy-shell",
        "quickshell",
        "sshd",
        "login",
        "bash",
        "sh",
        "zsh",
        "fish",
        "dash",
        "sudo",
        "grep",
        "rg",
        "ugrep",
        "pgrep",
        "ps",
        "python",
        "python3",
        "busybox",
    }
)

PROTECTED_COMMS = frozenset(
    {
        "systemd",
        "init",
        "hyprland",
        "Hyprland",
        "omarchy-shell",
        "quickshell",
        "sshd",
        "login",
        "dbus-daemon",
        "wireplumber",
        "pipewire",
    }
)
