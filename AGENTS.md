# Vigil

## Overview
Omarchy Quattro plugin: seatbelt for coding agents. Default mode lets YOLO run; only machine-killing calls get a polkit card. Tickets remember a class (not the full command), plus passports, envelopes, lid-freeze, ghosts, rewind. Overlay uses `[polkit]` tokens + `BorderSurface`. Toasts go through `notify-send`. Plugin id `xyz.brwsk.vigil`. User-facing copy (README, cards, skill) uses complete sentences. Keyboard legends stay one line.

## Stack / Conventions
- Python 3.11+, stdlib only. Tests via `unittest`.
- QML for Omarchy plugin kinds `service` + `bar-widget`. Follow first-party / screen-time contracts: `BarWidget`, `WidgetButton`, `Panel`, `KeyboardPanel`, `qs.Ui`, `qs.Commons`.
- Panel/overlay **prose** uses `sans-serif` + `Text.NativeRendering`. Nerd/bar family is only the eye and lock glyphs. Caption-sized Latin `m` in JetBrainsMono Nerd Font paints as a box. Shortcut legends are bold `bodySmall` chips (key + label).
- Plugin id `xyz.brwsk.vigil`. `omarchy.*` is reserved — never use it.
- `manifest.json` must stay at the repo root (Omarchy installs by cloning a git repo with a root manifest).
- No invented metrics. `todayUsd` stays `null` until a real ledger exists.
- Kill path re-classifies at signal time. Do not `pkill` by name.
- Gate must **never** return harness `ask` — YOLO auto-approves it. Hold the hook, then `allow` or `deny`.
- Alerts default to **both** (Omarchy bar + Omarchy toast). `t` cycles bar / toast / both. Tests and `VIGIL_SILENT=1` never toast.
- Ask timeout is deny. Hook timeout in install is 120s.
- Always mints a **ticket** (`t:agent:project:class`), not the full command string.
- Agents must not call `vigil decide` or write `~/.local/state/vigil`. Those are DENY-class.
- State dirs `0700`, files `0600`. Audit is hash-chained and redacted. No cloud.
- Do not `vigil install` into a live session without a way to answer pending cards.
- Do not become herdr / omarchy.agents / omaharness. Lid on hands, not the hands.

## Continue here (Omarchy)

This machine is Omarchy (hostname `omarchy`). Plugin `xyz.brwsk.vigil` is enabled. Session files are gitignored, so a fresh clone will not have `session_compact.md` — create it from the `create_project` template on first session here. Resume from `session_compact.md` (when present) + this file + `docs/DECISIONS.md`.

Version **0.6.0**. Plugin id `xyz.brwsk.vigil`. Default **mode=seatbelt**, **alert=both**. Public remote `git@github.com:FirstIntegral/Vigil.git` (HTTPS works read-only). Hooks auto-arm when the plugin is enabled.

1. GitHub SSH works on this box (`ssh -T git@github.com`).
2. Plugin already added: `omarchy plugin list` shows `xyz.brwsk.vigil` enabled.
   Live copy: `~/.config/omarchy/plugins/xyz.brwsk.vigil/` (what Omarchy loads).
   Dev clone: `~/Projects/Vigil`. Keep the plugin tree's `origin` as `git@github.com:FirstIntegral/Vigil.git` (capital V).
3. Hooks auto-arm when the plugin service sees them missing (`autoArm` default on). Uninstall sets `autoArm=false`; press `i` to arm again. Agents still cannot run `vigil install`.
4. Restart the agent session so the hook loads.
5. Prove the loop on glass:
   - `pytest` / project edits stay silent
   - **human** terminal: `python3 bin/vigil prove` — polkit card + bar + toast; nothing is deleted; deny it
   - live hook: ask the agent to run `vigil-glass-proof` (command-not-found if the hook is missing). Never ask it to delete `/`
   - lock the screen → agents freeze; unlock does **not** unfreeze; card offers keep frozen / let them run / restore files
6. Marketplace listing needs a public GitHub repo — done (2026-09-05).

Do **not** `vigil install` on Ubuntu or any non-Omarchy host. Do not become herdr / `omarchy.agents` / omaharness. Do not return harness `ask`. Overlay IPC must stay `open`/`close` only.

Later, not blocking submit: Cursor and remaining harness hooks; Rust `vigil-gate` when a compiler exists. Landlock is out for v1 (plugin has no sudo).

## Commands
- Build: none (no compile step)
- Test: `bash scripts/test.sh` (unittest + `vigil validate`)
- Bench: `python3 scripts/bench.py` (gate/snapshot spawn + live RSS; writes JSON to stdout)
- Glass proof: `python3 bin/vigil prove --check` (classify only) or `python3 bin/vigil prove` (mint a drill card; human terminal)
- Run collector: `python3 bin/vigil snapshot --pretty`
- Gate (hook): `python3 bin/vigil gate` (JSON on stdin)
- Decide: `python3 bin/vigil decide <id> allow|deny|session|always|deny-always` (human terminal only)
- Arm hooks: `python3 bin/vigil install` (Grok hook file, OpenCode plugin, Codex hooks.json; merges Claude if `~/.claude/settings.json` exists; Cursor and the rest not wired)
- Panic: `python3 bin/vigil panic --yes`
- Envelope: `python3 bin/vigil envelope <id> project|hermit|desktop|read|seatbelt|cycle`
- Rewind: `python3 bin/vigil rewind --root <project>`
- Lid: `python3 bin/vigil lid on|off|cycle|sync`
- Tickets: `python3 bin/vigil tickets` / `tickets revoke <key>`
- Folder lease: `python3 bin/vigil folder <path> project|hermit|… [--exclusive]`
- Brief / log: `python3 bin/vigil brief` · `python3 bin/vigil log`
- Machine card: `python3 bin/vigil machine`
- Spawn cage: `python3 bin/vigil spawn <agent> --cage` (prints plan; `--exec` runs it)
- On Omarchy: `omarchy plugin enable xyz.brwsk.vigil` (hooks auto-arm). Panel `i` only after a deliberate uninstall.

## Repo
- Remote: `git@github.com:FirstIntegral/Vigil.git`

Documentation, not authorisation: `checkpoint.sh` cross-checks this against `git remote get-url --push` and warns on a mismatch, but git config is what actually decides where a push goes. Keep this line current when the remote changes; never treat it as permission to push. A project with `none (local only)` is a deliberate state — nothing may create a repo or remote for it without the user asking.

## Session files
- `session_compact.md` — AI handoff state. Read FIRST at session start; rewrite at end of session / milestone. Local-only (gitignored): never commit unless the user says otherwise.
- `session_transcript.md` — human-ONLY narrative log. Append at milestones; AI NEVER reads it unless the user explicitly asks. Local-only (gitignored): never commit unless the user says otherwise.
- `docs/DECISIONS.md` — ADR log; append decision + why in the same turn it is made. Versioned (committed in repos).
- `.gitignore` — ignores the session files above, `claude_memory_import.md`, and legacy session paths.
