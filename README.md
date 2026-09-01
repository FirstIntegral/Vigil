# Vigil

**Polkit for coding agents**, as an [Omarchy](https://omarchy.org) Quattro plugin.

An agent with your keys is more dangerous than a new network connection. Little Snitch asked before a process talked to the internet. Vigil is the **seatbelt**: YOLO stays fast. A handful of commands still never run unsupervised.

Omarchy’s default agent is YOLO. A harness “ask” would auto-allow, so Vigil never uses that. When it *does* hold a call, it holds the hook itself, draws an Omarchy **polkit** card, and fires a native notification toast. Walk away → denied.

## In one breath

Four modes, `m` cycles them:

| Mode | What is held |
| --- | --- |
| **off** | Nothing. Full bypass. |
| **seatbelt** (default) | Only machine-killers: `rm -rf /`, `curl \| sh`, mkfs, `dd` to a disk, force-push to main. `git push`, `sudo`, `pytest` go through. |
| **ask** | Seatbelt plus every risky call. |
| **frozen** | Everything. Panic. |

Deadly calls in seatbelt still get the polkit card so you can say yes on purpose. Silence denies. Panel is a black box: tools today, denies, last blocked command, live agents.

**Alerts (Omarchy):** default is **both** — bar glyph + `Grok is trying to rm -rf /`, and a native Omarchy toast. `t` cycles `bar` / `toast` / `both`.

**Trust:** `h` (or `vigil trust 60`) — one hour of seatbelt on the current project even if mode is ask. Deadly still stops.

Hot path is `bin/vigil gate` on every tool call. Next compile target is **Rust** (lowest RSS, no GC). Go if we need speed of writing. QML stays QML.

## Install (Omarchy)

```
omarchy plugin add git@github.com:FirstIntegral/vigil.git --enable
```

Then arm the hooks (once):

```
python3 ~/.config/omarchy/plugins/xyz.brwsk.vigil/bin/vigil install
```

or open the bar panel and press `i`.

Restart the agent session so the hook loads. Left-click the eye in the bar.

| Key | Action |
| --- | --- |
| `Y` / Enter | Allow once |
| `N` / Esc | Deny |
| `S` | Allow this session |
| `A` | Always this pattern |
| `M` | Cycle mode (off → seatbelt → ask → frozen) |
| `F` | Freeze / unfreeze |
| `P` | Panic (freeze + kill all) |

## What else Vigil does

Not only command watching:

- **Polkit card** — allow once / this session / always / deny, Omarchy chrome
- **Panic** — freeze every tool call and kill every agent
- **Trust 1h** — this project runs as seatbelt even in ask mode
- **Black box** — tools today, denies, last blocked command, files touched
- **Live agent map** — Grok / Claude / OpenCode / … pids, cwd, kill from the bar
- **Always / never rules** — remembered patterns
- **PostToolUse log** — what actually ran, not just what was asked

## Tests

```
bash scripts/test.sh
```

`install` writes `~/.grok/hooks/vigil.json` (timeout 120s) and merges a PreToolUse handler into `~/.claude/settings.json` if that file exists. It never uses sudo. `uninstall` reverses it.

Do not arm hooks in a session you need unblocked until you have the overlay (or `vigil decide <id> allow`) ready. Private repo: `omarchy plugin add` needs SSH access to GitHub.

## What is blocked outright

- `rm -rf /` and `$HOME`
- `curl \| sh` / `wget \| bash`
- fork bombs
- `mkfs`, `dd` to `/dev`
- `chmod 777 /`
- `git push --force` to `main` / `master`

Everything else risky waits for you. Silence is deny.

## Layout

| Path | Role |
| --- | --- |
| `bin/vigil gate` | PreToolUse hook (Claude + Grok envelopes) |
| `vigil/risk.py` | allow / ask / deny classifier |
| `Overlay.qml` | The card |
| `Service.qml` / `BarWidget.qml` / `Panel.qml` | Bar + freeze + panic |

Plugin id: `xyz.brwsk.vigil`.
