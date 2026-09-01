# Vigil

## Overview
Omarchy Quattro plugin: **seatbelt for coding agents**. Default mode lets YOLO run; only machine-killers get a polkit card. `ask` / `off` / `frozen` are explicit. Overlay uses `[polkit]` tokens + `BorderSurface`. Toasts go through `notify-send` so Omarchy's notification daemon paints them. Plugin id `xyz.brwsk.vigil`.

## Stack / Conventions
- Python 3.11+, stdlib only. Tests via `unittest`.
- QML for Omarchy plugin kinds `service` + `bar-widget`. Follow first-party / screen-time contracts: `BarWidget`, `WidgetButton`, `Panel`, `KeyboardPanel`, `qs.Ui`, `qs.Commons`.
- Plugin id `xyz.brwsk.vigil`. `omarchy.*` is reserved — never use it.
- `manifest.json` must stay at the repo root (Omarchy installs by cloning a git repo with a root manifest).
- No invented metrics. `todayUsd` stays `null` until a real ledger exists.
- Kill path re-classifies at signal time. Do not `pkill` by name.
- Gate must **never** return harness `ask` — YOLO auto-approves it. Hold the hook, then `allow` or `deny`.
- Alerts default to **both** (Omarchy bar + Omarchy toast). `t` cycles bar / toast / both. Tests and `VIGIL_SILENT=1` never toast.
- Ask timeout is deny. Hook timeout in install is 120s.
- Do not `vigil install` into a live session without a way to answer pending cards.

## Commands
- Build: none (no compile step)
- Test: `bash scripts/test.sh` (unittest + `vigil validate`)
- Run collector: `python3 bin/vigil snapshot --pretty`
- Gate (hook): `python3 bin/vigil gate` (JSON on stdin)
- Decide: `python3 bin/vigil decide <id> allow|deny|session|always|deny-always`
- Arm hooks: `python3 bin/vigil install` (writes `~/.grok/hooks/vigil.json`)
- Panic: `python3 bin/vigil panic --yes`
- On Omarchy: `omarchy plugin enable xyz.brwsk.vigil` then panel `i` to arm

## Repo
- Remote: `git@github.com:FirstIntegral/vigil.git`

Documentation, not authorisation: `checkpoint.sh` cross-checks this against `git remote get-url --push` and warns on a mismatch, but git config is what actually decides where a push goes. Keep this line current when the remote changes; never treat it as permission to push. A project with `none (local only)` is a deliberate state — nothing may create a repo or remote for it without the user asking.

## Session files
- `session_compact.md` — AI handoff state. Read FIRST at session start; rewrite at end of session / milestone. Local-only (gitignored): never commit unless the user says otherwise.
- `session_transcript.md` — human-ONLY narrative log. Append at milestones; AI NEVER reads it unless the user explicitly asks. Local-only (gitignored): never commit unless the user says otherwise.
- `docs/DECISIONS.md` — ADR log; append decision + why in the same turn it is made. Versioned (committed in repos).
- `.gitignore` — ignores the session files above, `claude_memory_import.md`, and legacy session paths.
