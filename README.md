# Vigil

Vigil is a seatbelt for coding agents on [Omarchy](https://omarchy.org).

Omarchy already launches agents, meters their spend, and tiles their terminals. Vigil covers the part that is still missing: **who is running, what they are allowed to do, and what happens when they try something irreversible.**

An agent with your keys is more dangerous than a new network connection. Little Snitch asked before a process talked to the internet. Polkit asked before a process became root. Vigil asks before an agent does something that can wreck this machine — and stays quiet for everything else.

Fast agents are the point. The seatbelt is not a nanny. If you want YOLO, you still get YOLO. Vigil only stops the calls that can destroy a disk, a git history, the desktop, or Vigil itself.

## What it looks like

You pick a default agent. It runs as usual.

Vigil sits on the agent’s **tool-call hook**. It does not sit on the harness “ask” prompt, because YOLO would auto-allow that and the seatbelt would be fake.

When a call is dangerous, Omarchy paints the same **polkit** card you already know: lock glyph, justification line, `BorderSurface`, native toast. The windows that would actually feel the damage are outlined on the glass (ghosts). If you walk away, the call is denied.

Pressing **A** no longer saves the whole command string. It mints a **ticket**: this agent, this project, this *class* of action, until you revoke it. A spawned subagent does not inherit the parent’s session wallet.

## Capabilities

**Seatbelt (the default).** Everyday work goes through: `git push`, `sudo`, `pytest`, edits inside the project. Only machine-killing calls wait for you.

**Tickets.** “Always allow” remembers a class, not a full command. Examples: git-push, `mcp:github`, write `~/.ssh`. That way a slightly different `curl` cannot hide behind a ticket you meant for tests.

**Passport.** Every live agent gets papers: which harness, which project, which envelope, which pid. The papers survive if the pane restarts.

**Envelope.** A per-agent lease you can tighten without changing the global mode. Cycle it with `e`:

- `seatbelt` — deadly only (the default)
- `project` — also hold writes outside this repo
- `hermit` — also hold network and MCP
- `desktop` — also hold Hyprland / plugin / power
- `read` — hold writes

**Ghosts.** A deadly call outlines the real Hyprland windows that would be hit. You can mute toasts and still see the blast radius on the glass.

**Lid.** When you lock the session, agents freeze. Unlocking the screen does **not** start them again. You get a card titled “while you were out,” and you choose: keep them frozen, unfreeze, or rewind.

**Rewind.** Restore git-tracked files this session touched, plus a copy-on-write snapshot of Omarchy / Hypr / Vigil config. It is an undo for this session, not a backup system.

**Claims.** If two agents want the same file, you get a card. This is advisory, and only for writes that go through the hooked tools.

**Panic.** One key freezes every future tool call and sends SIGTERM to every classified agent.

**Black box.** A local, hash-chained JSONL log. Secrets are redacted. Nothing is uploaded.

**House law.** Five short articles, quoted on the card, also installed as a skill the agent can read. They are reminders, not a second policy engine.

## Modes

Press `m` to cycle. There are four global modes:

**off.** Vigil does not hold anything. Full bypass. Use this when you truly want the agent unsupervised.

**seatbelt (default).** Only deadly calls wait: deleting `/` or `$HOME`, piping the internet into a shell, formatting a disk, raw `dd` to a device, force-pushing `main`, killing the compositor, injecting a plugin, self-approving Vigil, reboot / shutdown.

**ask.** Seatbelt plus every risky call (network, sudo, git push, writes outside the project, and so on). This is Little Snitch mode.

**frozen.** Every tool call is denied until you unfreeze. You get here by pressing Panic, or by locking the screen while the lid is on. Unlocking the screen does not leave this mode. On Omarchy the lid watches `omarchy.lock` (`omarchy-shell lock isLocked`), not hyprlock.

**Alerts** default to **both**: a bar glyph plus a short line like `Grok is trying to rm -rf /`, and a native Omarchy toast. Press `t` to cycle `bar` / `toast` / `both`.

**Trust.** Press `h` to treat this project as seatbelt for one hour, even if the global mode is ask. Deadly calls still stop.

## Install (Omarchy only)

```
omarchy plugin add https://github.com/FirstIntegral/vigil.git --enable
```

If the GitHub repository is still private, clone over SSH instead:

```
omarchy plugin add git@github.com:FirstIntegral/vigil.git --enable
```

Then arm the hooks once. Either:

```
python3 ~/.config/omarchy/plugins/xyz.brwsk.vigil/bin/vigil install
```

or open the bar panel and press `i`.

Restart the agent session so the hook actually loads. Left-click the eye in the bar.

Do not arm hooks in a session you still need unblocked unless the overlay (or `vigil decide` from a **human** terminal) is ready to answer cards.

## Remove

Disarm the hooks first, while the plugin is still on disk:

```
python3 ~/.config/omarchy/plugins/xyz.brwsk.vigil/bin/vigil uninstall
```

Then remove the plugin from Omarchy:

```
omarchy plugin remove xyz.brwsk.vigil
```

That does not delete `~/.config/vigil` or `~/.local/state/vigil`. Those directories are your tickets and black box. Delete them yourself if you want them gone.

## Dependencies

Python 3.11+ (stdlib only). On Omarchy: `notify-send`, `omarchy-shell`, and optionally `hyprctl` for window ghosts. No pip packages.

## License

Vigil is **MIT**. You may use, copy, modify, merge, publish, and sell it, so long as you keep the copyright notice. There is **no warranty**.

That matches Omarchy itself (MIT) and the plugin marketplace, which asks for a root `LICENSE` file and does not require a copyleft license. First-party Omarchy plugins (`omarchy.agents`, and so on) are MIT too. A GPL-only plugin would be an awkward fit next to MIT QML in `omarchy-shell`; MIT is the usual choice.

### First run checklist

Do this on Omarchy, not on Ubuntu.

1. Confirm GitHub SSH works: `ssh -T git@github.com`
2. Add and enable the plugin (command above).
3. Press `i` in the Vigil panel, or run the `install` command above.
4. Quit and restart Grok / Claude Code / whichever agent you use, so it picks up the hook.
5. Run something harmless (`pytest` in a project). Nothing should pop up.
6. From a **human** terminal, not from an agent:

   ```
   python3 ~/.config/omarchy/plugins/xyz.brwsk.vigil/bin/vigil prove
   ```

   That mints the real polkit card, bar line, and toast for a **drill**. Nothing is deleted. Deny it.
7. To prove the *live hook* (the path that actually sits on tool calls), ask the agent to run `vigil-glass-proof`. Same card. If you only see `command not found` and no card, the hook did not load — restart the agent.
8. Lock the session. Agents should freeze. Unlock. They should stay frozen until you press `U`.

Do **not** ask an agent to delete `/` or `$HOME` to test this. Grok hooks fail *open* if the hook is missing, crashes, or times out. GNU `rm` may refuse `rm -rf /` without `--no-preserve-root`, but that is not a seatbelt. The drill is.

If step 6 never appears, check that `~/.grok/hooks/vigil.json` (or Claude `settings.json`) exists. If step 7 never appears, restart the agent so it loads that file.

| Key | Action |
| --- | --- |
| `Y` / Enter | Allow this call once |
| `N` / Esc | Deny this call |
| `S` | Allow this class for the rest of the session |
| `A` | Mint a ticket (this agent × this project × this class) |
| `D` | Deny-always that ticket |
| `U` | Unfreeze (after lid / incident) |
| `W` | Rewind this session’s tracked files |
| `M` | Cycle mode |
| `E` | Cycle envelope on the selected agent |
| `L` | Lid on / off |
| `F` | Freeze / unfreeze |
| `P` | Panic (freeze + kill all classified agents) |
| `T` | Cycle alerts |
| `H` | Trust this project for one hour |
| `I` | Arm hooks |

## Limitations

Vigil is a **consent UI on the hooked path**. It is not a jail, a sandbox, or a kernel security module. Read this before you trust it with a machine you cannot restore.

**It is cooperative.** An agent that never loads the hook, that writes files from an unhooked child process, or that talks to Hyprland through a helper Vigil does not see, is not stopped. The seatbelt is honest about that.

**Agents run as you.** Unix mode `0700` on Vigil’s state stops *other accounts*, not the agent on this account. The real gate is the hook: writes to `~/.local/state/vigil` and any `vigil decide` from an agent are treated as **self-approve** and denied.

**It cannot sandbox other plugins.** Omarchy plugins share `omarchy-shell`. Vigil cannot confine a sibling. It *can* refuse `omarchy plugin add` / `enable` / `remove`.

**No Landlock, no seccomp, no cgroup.** An Omarchy plugin has no sudo and no install hooks. `vigil spawn --exec` stamps an envelope and execs. It does not jail the process.

**Ghosts need Hyprland.** If `hyprctl` is missing, there are no outlines. The polkit card still works.

**Rewind is not backup.** It restores git-tracked project files and a copy of `~/.config/omarchy`, `hypr`, and `vigil`. It does not delete files the agent created. It never touches secrets. It is not Timeshift.

**Claims are advisory.** Agents that bypass tools can still stomp the same file.

**OpenCode / Codex hooks are not wired yet.** The gate already understands generic envelopes. `install` currently writes Grok hooks, and Claude hooks if `~/.claude/settings.json` exists.

**QML is Omarchy-only.** This tree is not a generic Linux daemon. Do not expect it to run as a service on Ubuntu or another distro.

## By design

These are not missing features. They are the product.

**YOLO is not the enemy.** The default is seatbelt, not ask. A popup on `pytest` is how people disable the hook and then have no seatbelt at all.

**Never return harness `ask`.** Grok YOLO and Claude `bypassPermissions` auto-allow that. Vigil holds the hook itself and returns only `allow` or `deny`.

**Silence is deny.** If the hook times out, crashes, or you walk away from the card, the call does not run.

**No cloud, no telemetry, no dollar amount in the bar.** Spend belongs to `omarchy.agents`. Vigil will not draw a meter. `todayUsd` stays null until a real ledger exists, and even then this plugin is not the place for it.

**No language model in the yes-path.** Classification is regex. Letting a model grant models is how you get captured.

**Local constitution.** Tickets and the black box live under `~/.config/vigil` and `~/.local/state/vigil`, mode `0700` / `0600`, hash-chained, secrets redacted.

**Agents cannot mint their own tickets.** `vigil decide` from an agent pid is refused. The overlay’s IPC has `open` and `close` only — no `allow()` verb a script could call.

**Vigil does not replace** Herdr (panes), `omarchy.agents` (billing), `omarchy.polkit` (sudo), `omarchy.lock` (the lock screen), or omaharness (desktop hands). Vigil is the lid on those hands, not the hands themselves.

**Omarchy chrome only.** `Color.polkit`, `BorderSurface`, `notify-send --app-name=Vigil`, bar widget, exclusive-focus overlay. No homemade toast, no mascot, no second design language.

**The name is Vigil.** The job is still watch. The expansion is *what the watchman sees*.

## What seatbelt blocks outright

These wait for you in seatbelt (and are denied if you do not answer):

- `rm -rf /` and `$HOME`
- `curl | sh` / `wget | bash`
- fork bombs
- `mkfs`, `dd` to `/dev`
- `chmod 777 /`
- `git push --force` to `main` / `master`
- `hyprctl dispatch exit` / `killwindow` / `exec`
- `omarchy plugin add|enable|remove|update`
- `reboot` / `shutdown` / `poweroff`
- `vigil decide` and writes under Vigil’s own state

Everything else that looks risky waits in **ask** mode, and passes in **seatbelt**. Envelope `project` also holds writes outside that repo. Envelope `hermit` holds network and MCP. Envelope `read` holds writes.

## Cost

Vigil does not start a second daemon. The bar, overlay, and panel are QML inside `omarchy-shell` (`keepLoaded`). The extra always-on work is one short-lived `python3 bin/vigil snapshot` every `refreshIntervalSec` (default **2 s**). Each hooked tool call also spawns `python3 bin/vigil gate`, which then exits.

Those spawns are the cost. Classification itself is a regex. There is no language model on the yes-path.

Measured 2026-09-02 on this machine: ThinkPad E14 Gen 4, 12th Gen Intel Core i7-1255U (12 threads), 16 GB RAM, Python 3.14.7, Linux 7.1.9-arch1-2. Re-run with `python3 scripts/bench.py` (`n=40` spawns, `n=200` in-process; median and p95).

| Path | Median | p95 | Peak RSS | Lives |
| --- | --- | --- | --- | --- |
| `vigil snapshot` (one spawn) | 109 ms | 115 ms | 62 MiB | ~0.1 s, then exits |
| `vigil gate` allow (one spawn, `pytest`) | 62 ms | 74 ms | 23 MiB | ~0.06 s, then exits |
| `gate` in-process (same allow path) | 0.10 ms | 0.25 ms | (caller) | n/a |

At the default 2 s poll that is about **5% of one core** for snapshot (`109 ms / 2 s`). At 1 s it would be about 11%. The Python process is not resident: it peaks, then goes away. Raise the interval in the widget settings (1–30 s) if you want it quieter.

Same machine, other processes that *stay* in RAM (RSS at the same moment):

| Process | RSS | Notes |
| --- | --- | --- |
| Grok | 621 MiB | the agent Vigil is seating |
| quickshell / omarchy-shell | 410 MiB | whole bar + notifications + **all** plugins, including Vigil’s QML |
| Hyprland | 184 MiB | compositor |
| proton.vpn.daemon | 107 MiB | Python, always on |
| OpenTabletDrive | 65 MiB | always on |
| udiskie | 62 MiB | Python, always on |
| foot | 33 MiB | one terminal |
| Vigil snapshot (peak) | 62 MiB | not always on; matches udiskie’s *size* for a tenth of a second |
| Vigil gate (peak) | 23 MiB | per tool call, then gone |

In general: a Python 3 cold start is tens of milliseconds and tens of MiB. That is normal for a stdlib CLI, and cheap next to Grok or the shell. It is heavier than a tiny Rust hook would be (planned; not measured here). It is lighter than keeping another 60–100 MiB Python daemon resident all day.

quickshell’s own CPU while Vigil was polling was **0.7% of one core** over 3 s. The snapshot child is the burst.

## Tests

```
bash scripts/test.sh
```

The hot path is `bin/vigil gate` on every tool call. The next compile target is **Rust** (lowest RSS, no garbage collector). The QML skin stays QML, because that is what Omarchy paints.

Plugin id: `xyz.brwsk.vigil`.
