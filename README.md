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

**frozen.** Every tool call is denied until you unfreeze. You get here by pressing Panic, or by locking the screen while the lid is on. Unlocking the screen does not leave this mode.

**Alerts** default to **both**: a bar glyph plus a short line like `Grok is trying to rm -rf /`, and a native Omarchy toast. Press `t` to cycle `bar` / `toast` / `both`.

**Trust.** Press `h` to treat this project as seatbelt for one hour, even if the global mode is ask. Deadly calls still stop.

## Install (Omarchy only)

```
omarchy plugin add git@github.com:FirstIntegral/vigil.git --enable
```

This repo is private, so GitHub SSH must work on that machine.

Then arm the hooks once. Either:

```
python3 ~/.config/omarchy/plugins/xyz.brwsk.vigil/bin/vigil install
```

or open the bar panel and press `i`.

Restart the agent session so the hook actually loads. Left-click the eye in the bar.

Do not arm hooks in a session you still need unblocked unless the overlay (or `vigil decide` from a **human** terminal) is ready to answer cards.

### First run checklist

Do this on Omarchy, not on Ubuntu.

1. Confirm GitHub SSH works: `ssh -T git@github.com`
2. Add and enable the plugin (command above).
3. Press `i` in the Vigil panel, or run the `install` command above.
4. Quit and restart Grok / Claude Code / whichever agent you use, so it picks up the hook.
5. Run something harmless (`pytest` in a project). Nothing should pop up.
6. Ask the agent to run `rm -rf /` (or any other deadly call). You should get the polkit card, a bar warning, and a toast. Deny it.
7. Lock the session. Agents should freeze. Unlock. They should stay frozen until you press `U`.

If step 6 never appears, the hook did not load — restart the agent and check that `~/.grok/hooks/vigil.json` (or Claude `settings.json`) exists.

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

## Tests

```
bash scripts/test.sh
```

The hot path is `bin/vigil gate` on every tool call. The next compile target is **Rust** (lowest RSS, no garbage collector). The QML skin stays QML, because that is what Omarchy paints.

Plugin id: `xyz.brwsk.vigil`.
