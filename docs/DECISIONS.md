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

## 2026-09-02 GitHub SSH uses the xigmatic linux key
- This ThinkPad's `id_rsa` (`brwsk@thinkpad`) is not on GitHub. The account already has the desktop key `brwsk@xigmatic`.
- **Decision:** `~/.ssh/id_ed25519` is that key. `Host github.com` uses it with `IdentitiesOnly yes`. ThinkPad `id_rsa` stays only for `polygonrizz-vps`. Vigil `origin` is `git@github.com:FirstIntegral/vigil.git`.
- **Rejected:** uploading the ThinkPad rsa as a new GitHub user key; a vigil-only deploy key; rewriting `git@` to HTTPS.

## 2026-09-02 Omarchy test isolation
- First run of `scripts/test.sh` on this Omarchy box failed two fixtures written on Ubuntu: rewind's `git commit` inherited global `commit.gpgsign` and popped pinentry; `test_empty_without_hyprctl` did not stub `hyprctl` and listed the live foot window as a ghost.
- **Decision:** fixture repos set local `commit.gpgsign`/`tag.gpgsign` false (test isolation, not a signing bypass). Ghosts test patches `shutil.which` to `None`.
- **Rejected:** disabling global gpgsign; asserting empty ghosts on a live Hyprland session.

## 2026-09-02 README and card copy in full sentences
- User: compact lines like "Everything. Panic, or the lid." are hard to read. Make the writing a bit longer, simple, easy to understand — not only that line, everything else.
- **Decision:** GitHub README, plugin description, house-law skill, overlay/panel status lines, and away/incident card copy use complete sentences. Keyboard legends on the card stay one line (Omarchy polkit density). ADR log stays terse (it is for tools, not strangers).
- **Rejected:** leaving the README in telegram fragments; turning the overlay key row into paragraphs (it would overflow the card).

## 2026-09-02 Lid watches omarchy.lock IPC, not hyprlock
- Glass proof: `omarchy system lock` engaged Quickshell ext-session-lock (`omarchy-shell lock isLocked` → true, `sessionLocked`/`secure` true). `loginctl LockedHint` stayed no. No `hyprlock`/`swaylock`/`gtklock` process. Vigil never froze; unlock stamped no away card.
- **Decision:** `is_locked()` asks `omarchy-shell lock isLocked` first. Keep loginctl + hyprlock/swaylock/gtklock as fallbacks. Still do not clone `omarchy.lock`.
- **Rejected:** treating hyprlock as Omarchy's locker; writing our own lock screen; polling `/proc` for `qs`.

## 2026-09-02 Marketplace listing, not a live prize heat
- First Omarchy plugin competition closed 2026-08-24 09:00 CEST; winners posted 2026-08-28. News says they will run again, no second heat announced as of 2026-09-02.
- **Decision:** next public step is an Omarchy plugin marketplace listing (`omacom/omarchy-plugin-marketplace`). Repo stays private until the user says make it public. README now has install **and** remove, plus HTTPS clone for the public URL.
- **Rejected:** opening a marketplace issue against a private repo; flipping visibility without an explicit ask; waiting on an unannounced second competition before listing.

## 2026-09-02 Toast uses the Vigil eye, not security-high
- User liked the bar eye. The "purple box" on the top-right was the Omarchy toast: `notify-send --icon=security-high` paints Adwaita's shield in the 40px slot (a dark tile).
- **Decision:** keep the Nerd Font eye on the bar. Toasts go through `omarchy notification send --app-name Vigil -g <eye>` so the same glyph shows in the toast. Critical uses the alert glyph. No `security-high`.
- **Rejected:** replacing the bar eye with a lighthouse/lantern (misread); a custom mascot; leaving the shield icon.

## 2026-09-02 Cost is spawn, not a daemon — numbers from this ThinkPad
- User: Vigil runs always, must be light; put real metrics in the GitHub README vs other processes on this machine.
- Measured 2026-09-02, ThinkPad E14 Gen 4, i7-1255U, 16 GB, Python 3.14.7: `snapshot` spawn median 109 ms / 62 MiB peak (`n=40`); `gate` allow spawn median 62 ms / 23 MiB (`n=40`); in-process gate 0.10 ms (`n=200`). No second daemon. QML lives in quickshell (410 MiB for the whole shell). Snapshot poll default **2 s** (~5% of one core). Script: `python3 scripts/bench.py`.
- **Rejected:** inventing numbers; claiming the spawn is free; a daemon this turn; quoting unmeasured Rust times as facts.

## 2026-09-02 Glass proof is a drill, not rm of /
- User: README told people to ask an agent to run a recursive delete of `/`. If the hook is missing, Grok hooks fail open. GNU `rm --preserve-root` is not a product guarantee.
- **Decision:** `vigil prove` classifies deadly samples in-process (no exec) and mints a card for the sentinel `vigil-glass-proof`. That sentinel is DENY-class; if it ever reaches a shell it is command-not-found. First-run and AGENTS.md never tell anyone to delete `/` to test. License remains MIT (compatible with Omarchy and the marketplace).
- **Rejected:** keeping the deadly first-run step; relying on GNU preserve-root; a dry-run flag on `rm`.

## 2026-09-02 README documents harness census vs hook install
- User asked which AI tools Vigil supports, then to put harnesses and hook install on the GitHub README.
- **Decision:** README gets a **Harnesses** section with two tables: ten process binaries the bar lists and Panic can SIGTERM, and what `vigil install` actually writes (Grok always, Claude only if `~/.claude/settings.json` exists, OpenCode/Codex/Cursor/Copilot/Crush/Antigravity/Hermes/Ori not wired). Lid freeze is called out as gate-only. Limitations keeps one line and points at that section. First-run checklist says only Grok and Claude get hooks today.
- **Rejected:** implying every Omarchy agent is seated; calling the gate “generic envelopes” without naming the two JSON shapes; listing `pi`.

## 2026-09-02 GitHub repo display name is Vigil
- User renamed `FirstIntegral/vigil` → `FirstIntegral/Vigil` on GitHub (still private). Clone URLs are case-insensitive; GitHub's canonical SSH is now `git@github.com:FirstIntegral/Vigil.git`.
- **Decision:** `origin` and tracked clone lines (`AGENTS.md` `## Repo`, README install) use that casing. Local directory stays `~/projects/vigil`. Plugin id stays `xyz.brwsk.vigil`.
- **Rejected:** renaming the local folder or the plugin id; treating the GitHub title as a new product.
