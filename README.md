# Vigil

**The constitution for coding agents on [Omarchy](https://omarchy.org).**

Omarchy already launches agents, meters their spend, and tiles their panes. Vigil is the missing piece: **who they are, what they may do, and what happens when they leave the lease.**

An agent with your keys is more dangerous than a new network connection. Little Snitch asked before a process talked to the internet. Polkit asked before a process became root. Vigil asks before an agent does something **irreversible to this machine** — and stays quiet for everything else.

YOLO is the point. The seatbelt is not a nanny.

## In one breath

You pick a default agent. It runs fast. Vigil sits on the tool-call hook, never on the harness “ask” (YOLO would auto-allow that). When a call is deadly, Omarchy paints the same **polkit** card you already know, outlines the real Hyprland windows that would feel it, and toasts through the native notification daemon. Walk away → denied.

`A` no longer saves a command string. It mints a **ticket**: this agent, this project, this class, until you revoke it. A spawned subagent does not inherit the parent’s *session* wallet.

## Capabilities

| Piece | What it does |
| --- | --- |
| **Seatbelt** | Default mode. `git push`, `sudo`, `pytest` pass. Machine-killers wait for you. |
| **Tickets** | Always / never remember a *class* (git-push, mcp:github, write `~/.ssh`), not the full argv. |
| **Passport** | Every live agent gets papers: harness, project, envelope, pid. Survives a restart of the pane. |
| **Envelope** | Per-agent lease: `seatbelt` · `project` · `hermit` · `desktop` · `read`. `e` cycles it. |
| **Ghosts** | Deadly call outlines the real windows on the glass. Mute the toasts — you still see the blast. |
| **Lid** | Lock the seat → agents freeze. Unlock does **not** unfreeze. Card: while you were out. |
| **Rewind** | Restore git-tracked files this session touched, plus a CoW copy of Omarchy/Hypr config. |
| **Claims** | Two agents, one file → card. Advisory, for harness writes. |
| **Panic** | One key: freeze every tool call and SIGTERM every classified agent. |
| **Black box** | Local, hash-chained JSONL. Secrets redacted. No cloud. |
| **House law** | Five articles, quoted on the card. A skill agents can read. Not a policy compiler. |

Four global modes, `m` cycles them:

| Mode | What is held |
| --- | --- |
| **off** | Nothing. Full bypass. |
| **seatbelt** (default) | Deadly only: `rm -rf /`, `curl \| sh`, mkfs, `dd` to a disk, force-push to main, compositor kill, plugin inject, self-approve, reboot. |
| **ask** | Seatbelt plus every risky call. |
| **frozen** | Everything. Panic, or the lid. |

**Alerts:** default **both** — bar glyph + `Grok is trying to rm -rf /`, and a native Omarchy toast. `t` cycles `bar` / `toast` / `both`.

**Trust:** `h` — one hour of seatbelt on this project even in ask mode. Deadly still stops.

## Install (Omarchy)

```
omarchy plugin add git@github.com:FirstIntegral/vigil.git --enable
```

Private repo: GitHub SSH must work on that machine.

Then arm the hooks (once):

```
python3 ~/.config/omarchy/plugins/xyz.brwsk.vigil/bin/vigil install
```

or open the bar panel and press `i`.

Restart the agent session so the hook loads. Left-click the eye.

| Key | Action |
| --- | --- |
| `Y` / Enter | Allow once |
| `N` / Esc | Deny |
| `S` | Allow this session |
| `A` | Mint a ticket (this agent × project × class) |
| `D` | Deny-always that ticket |
| `U` | Unfreeze (lid / incident card) |
| `W` | Rewind this session’s tracked files |
| `M` | Cycle mode |
| `E` | Cycle envelope on the selected agent |
| `L` | Lid on / off |
| `F` | Freeze / unfreeze |
| `P` | Panic (freeze + kill all) |
| `T` | Cycle alerts |
| `H` | Trust this project 1h |
| `I` | Arm hooks |

## Limitations (read this)

Vigil is a **consent UI on the hooked path**, not a jail.

- **Cooperative.** An agent that never loads the hook, that writes files from an unhooked child, or that talks to Hyprland through a helper Vigil does not see, is not stopped. Seatbelt is honest about that.
- **Same user.** Agents run as you. Unix file mode `0700` on Vigil’s state stops *other* accounts, not the agent. The hook treats writes to `~/.local/state/vigil` and `vigil decide` as **self-approve** (deadly). That is the real gate.
- **Cannot sandbox other plugins.** Omarchy plugins share `omarchy-shell`. Vigil cannot confine a sibling. It can refuse `omarchy plugin add` / `enable` / `remove`.
- **No Landlock, no seccomp, no cgroup.** An Omarchy plugin has no sudo and no install hooks. `vigil spawn --exec` stamps an envelope and execs. It does not jail the process.
- **Ghosts need Hyprland.** No `hyprctl` → no outlines. The polkit card still works.
- **Rewind is not backup.** Git-tracked project files + CoW of `~/.config/omarchy` / `hypr` / `vigil`. It does not delete files the agent created. It never touches secrets. It is not Timeshift.
- **Claims are advisory.** Agents that bypass tools stomp anyway.
- **OpenCode / Codex hooks** are not wired yet. The gate already parses generic envelopes; `install` writes Grok + Claude (if `~/.claude/settings.json` exists).
- **QML is Omarchy-only.** This tree is not a generic Linux daemon.

## By design

These are not missing features. They are the product.

- **YOLO is not the enemy.** Default is seatbelt, not ask. A popup on `pytest` is how users disable the hook.
- **Never harness `ask`.** Grok YOLO / Claude bypassPermissions auto-allow it. Vigil holds the hook and returns only `allow` or `deny`.
- **Silence is deny.** Timeout, crash, walk away.
- **No cloud, no telemetry, no `$` in the bar.** Spend belongs to `omarchy.agents`. Vigil will not draw a meter. `todayUsd` stays null.
- **No LLM in the yes-path.** Classification is regex. A model granting models is capture.
- **Local constitution.** Tickets and the black box live under `~/.config/vigil` and `~/.local/state/vigil`, mode `0700` / `0600`, hash-chained, secrets redacted.
- **Agents cannot mint their own tickets.** `vigil decide` from an agent pid is refused. Overlay IPC has no `allow()` verb.
- **Does not replace** Herdr (panes), `omarchy.agents` (billing), `omarchy.polkit` (sudo), `omarchy.lock` (the lock screen), or omaharness (desktop hands). Vigil is the lid on hands, not the hands.
- **Omarchy chrome only.** `Color.polkit`, `BorderSurface`, `notify-send --app-name=Vigil`, bar widget, exclusive-focus overlay. No homemade toast, no mascot.
- **Name is Vigil.** The job is still watch. The expansion is *what the watchman sees*.

## What is blocked outright (seatbelt)

- `rm -rf /` and `$HOME`
- `curl \| sh` / `wget \| bash`
- fork bombs
- `mkfs`, `dd` to `/dev`
- `chmod 777 /`
- `git push --force` to `main` / `master`
- `hyprctl dispatch exit` / `killwindow` / `exec`
- `omarchy plugin add|enable|remove|update`
- `reboot` / `shutdown` / `poweroff`
- `vigil decide` and writes under Vigil’s own state

Everything else risky waits in **ask** mode, and passes in **seatbelt**. Envelope `project` also holds writes outside that repo. Envelope `hermit` holds network and MCP. Envelope `read` holds writes.

## Tests

```
bash scripts/test.sh
```

Do not arm hooks in a session you need unblocked until you have the overlay (or `vigil decide <id> allow` from a **human** terminal) ready.

Hot path is `bin/vigil gate` on every tool call. Next compile target is **Rust** (lowest RSS, no GC). QML stays QML.

Plugin id: `xyz.brwsk.vigil`.
