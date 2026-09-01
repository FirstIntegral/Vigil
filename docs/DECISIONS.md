# Decisions & Rationale (ADRs)

## 2026-09-01 Product is Vigil, not another usage meter
- Omarchy Quattro (~1000 community plugins, Quickshell `omarchy-shell`, kinds: bar-widget / panel / overlay / menu / service / bar) already ships `omarchy.agents` for subscription usage and rate limits. Community clones (claudebar, ai-usagebar) do the same. The gap that can actually be worth money is **operations + consent**: which agents are alive, what they sit on, a kill switch, later a Little-Snitch-style allow/deny overlay for tool calls.
- Rejected: another clock/theme/dock; a Time Machine wrapper (Timeshift/snapper exist); a plugin sandbox (third-party plugins share the shell process, cannot confine each other); an `Oma*` name (overused, sounds like a weekend widget).
- Name **Vigil**. Plugin id `xyz.brwsk.vigil` (brwsk.xyz). `$10k` path: $49 × ~200 or $8/mo × ~100, or a Foundation/enterprise license. v1 is the live map + kill; v2 is PreToolUse intercept.

## 2026-09-01 Python collector + QML skin, one git tree
- Omarchy installs `omarchy plugin add <git-url>` by cloning a repo whose **root** is `manifest.json`. Tests, docs, and the collector therefore live in the same tree. QML execs `bin/vigil snapshot` / `kill`.
- Rejected: a QML-only `/proc` parser (untestable on this Ubuntu box, policy would rot in the shell process); a separate daemon requiring systemd (Omarchy plugins have no install hooks and must not ask for sudo).

## 2026-09-01 Classify by argv0, re-check at kill time
- Match `comm`, exe basename, and argv0 only. Later argv is ignored so `pgrep -af claude` is not an agent. Shells, python, and `systemd-inhibit` are never agents.
- `kill` re-reads `/proc` and refuses pid ≤ 1, other uids, protected comms, and anything that no longer classifies. `kill-all` requires `--yes`.
- Rejected: `pkill -f`, matching `$GROK_AGENT` on child bash (would list every tool subprocess), signalling `SIGKILL` by default.

## 2026-09-01 No git remote at create_project
- `create_project` never inits a repo and never adds a remote. Publishing is a later explicit human choice. `AGENTS.md` `## Repo` is `none (local only)`.

## 2026-09-01 Vigil is the permission broker, not a process list
- User asked for an idea *worth* $10k, then to think big and build it. Process-list v1 was not that. The $10k primitive: **polkit for coding agents**. Omarchy is agentic Linux; YOLO/always-approve is the default; one bad tool call is more expensive than $10k.
- Hold the PreToolUse hook, show our overlay, return allow or deny. Never emit harness `ask` — Grok YOLO auto-approves it. Silence / timeout = deny (Grok hooks fail-open on timeout, so install sets timeout 120s and we deny before that).
- Hard-deny only for machine-killing calls (`rm -rf /`, `curl|sh`, mkfs, dd to /dev, force-push main). Everything else risky asks. Reads and in-project writes pass.
- Rejected: returning `decision: ask` to the harness; a kernel sandbox this turn (hooks are where coding agents actually stop); auto-installing hooks into the live session that is building this.

## 2026-09-01 Seatbelt default, YOLO is not the enemy
- User: if someone wants to bypass everything, holding every command is wrong; some commands should still stop. Default mode is **seatbelt**: YOLO/`git push`/`sudo`/`pytest` pass. Only DENY-class (rm-root, curl\|sh, mkfs, dd-to-dev, force-push main) is held as a polkit card, timeout deny. **off** holds nothing. **ask** is Little Snitch. **frozen** is panic.
- Overlay restyled to first-party polkit: `Color.polkit.*`, `Border.surfaceSpec("polkit", ...)`, `Color.polkit.scrim`, justification pill, lock glyph, `Style.font.menuFamily`. No homemade accent-border rectangle. Denies also fire `notify-send --app-name=Vigil` so Omarchy toasts render them.
- Extra muscle: PostToolUse black box, today's counts, last-denied, mode cycle (`m`).
- Rejected: nannying YOLO by default; custom notification chrome (Omarchy already owns toasts).

## 2026-09-02 Alerts: bar and toast, Omarchy-first
- User asked for both the bar warning and the toast, and to ignore other distros. **Default `alert=both`**: Omarchy bar glyph + summary, and `notify-send --app-name=Vigil` which Omarchy's notification daemon paints. `t` cycles bar / toast / both. Tests and `VIGIL_SILENT=1` still never toast (that was the Ubuntu spam). Product target is Omarchy only.
- Bar warning: severity glyph (`Color.urgent` for deadly) plus `"{Agent} is trying to {command}"`. `t` cycles bar/toast/both.
- **Trust 1h** (`h`): treat this project as seatbelt even in ask mode. Deadly still stops.
- Language for the hot path: `vigil gate` is spawned on every tool call. Python cold-start is tens of ms. **Rust** is the right next binary (lowest RSS, no GC, ~5–15ms). Go is the runner-up (faster to write, ~8MB RSS). QML stays QML (Omarchy). No rustc/go on this box, so the gate stays Python until a machine that can compile. Rejected: rewriting QML in something else; a daemon this turn (right idea, extra moving part before Omarchy install).

## 2026-09-02 Private GitHub remote
- User asked for a private GitHub repo and a push. Remote is `git@github.com:FirstIntegral/vigil.git`. `AGENTS.md` `## Repo` updated the same turn. Checkpoint still never creates remotes; this one is an explicit human request.

## 2026-09-02 Vigil is the constitution, not a second product
- User: do it all — tickets, passports, envelopes, ghosts, lid, rewind, claims, MCP classes — Omarchy style, security and privacy, then push with a README that states capabilities, limits, and by-design.
- **Same loop, stretched.** Hold the hook, polkit card, seatbelt default. Always now mints `t:agent:project:class` (and `mcp:server` / host extras), not the argv. Envelope is a per-passport cage the gate honours. Lid binds freeze to the lock screen (does not clone `omarchy.lock`). Ghosts are Hyprland client outlines on the existing overlay. Rewind is git + config CoW, not Timeshift.
- **Security basics:** pending/policy/audit `0700`/`0600`; audit hash-chained and redacted; `vigil decide` refused from an agent pid; overlay IPC has no `allow()`; writes to Vigil state and `vigil decide` are DENY-class `self-approve`; desktop-kill (`hyprctl dispatch exit|exec`) and `omarchy plugin add|enable|remove` are deadly; reboot/shutdown deadly. No cloud, no `$` in the bar, no LLM classifier.
- **Rejected:** becoming herdr / omarchy.agents / omaharness; Landlock as v1 (plugin has no sudo); a bar pet; kernel LSM as the product; auto-unfreeze on unlock (lid holds until a human key); Always inheriting as a command regex (that was a lie).
- Landlock / Rust gate stay later. OpenCode/Codex install still unwired. Cooperative hooks stay the honest limitation.

## 2026-09-02 Omarchy handoff lives in tracked files
- User continues from an Omarchy machine. `session_compact.md` / `session_transcript.md` are gitignored on purpose, so a clone will not have them.
- **Decision:** the resume steps live in `AGENTS.md` (`## Continue here (Omarchy)`) and the README first-run checklist. A fresh session on Omarchy reads those plus `docs/DECISIONS.md`.
- **Rejected:** committing session files (privacy rule); a separate CONTINUE.md (two files already cover human + AI).

## 2026-09-02 README and card copy in full sentences
- User: compact lines like "Everything. Panic, or the lid." are hard to read. Make the writing a bit longer, simple, easy to understand — not only that line, everything else.
- **Decision:** GitHub README, plugin description, house-law skill, overlay/panel status lines, and away/incident card copy use complete sentences. Keyboard legends on the card stay one line (Omarchy polkit density). ADR log stays terse (it is for tools, not strangers).
- **Rejected:** leaving the README in telegram fragments; turning the overlay key row into paragraphs (it would overflow the card).
