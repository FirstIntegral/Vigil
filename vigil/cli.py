"""CLI: hook gate, overlay decide, snapshot, panic. Stdout is JSON."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from vigil import PLUGIN_ID, __version__
from vigil.envelope import ENVELOPES, normalize as normalize_envelope
from vigil.gate import gate_payload
from vigil.install import install as install_hooks
from vigil.install import uninstall as uninstall_hooks
from vigil.kill import KillRefused, kill_agent
from vigil.dossier import read_last_denied
from vigil.lid import sync as lid_sync
from vigil.passport import cycle_envelope, set_envelope
from vigil.pending import ACTIONS, cleanup, list_pending, request_path, write_decision
from vigil.principal import caller_is_agent
from vigil.notify import ALERTS
from vigil.policy import MODES, load_policy, save_policy
from vigil.rewind import rewind
from vigil.snapshot import collect, default_state_path, dumps, write_snapshot
from vigil.prove import dumps as dumps_prove
from vigil.prove import prove as run_prove
from vigil.validate import PluginInvalid, assert_valid


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _helper(root: Path | None = None) -> str:
    return str((root or _plugin_root()) / "bin" / "vigil")


def _home(args: argparse.Namespace) -> Path:
    return Path(args.home) if args.home else Path.home()


def _refuse_agent() -> int | None:
    if not caller_is_agent():
        return None
    sys.stderr.write("vigil: refuse this command from an agent process\n")
    sys.stdout.write(
        json.dumps({"ok": False, "error": "agents cannot run this vigil command"}) + "\n"
    )
    return 2


def cmd_snapshot(args: argparse.Namespace) -> int:
    snap = collect(home=_home(args))
    if args.write:
        write_snapshot(snap, Path(args.write))
    elif args.state:
        write_snapshot(snap, default_state_path(_home(args)))
    sys.stdout.write(dumps(snap, pretty=args.pretty))
    return 0


def cmd_kill(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    try:
        result = kill_agent(args.pid, sig=args.signal)
    except KillRefused as exc:
        sys.stderr.write(f"vigil: {exc}\n")
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}) + "\n")
        return 2
    payload = {
        "ok": True,
        "pid": result.pid,
        "agent": result.agent,
        "signal": result.signal,
        "comm": result.comm,
    }
    sys.stdout.write(json.dumps(payload) + "\n")
    return 0


def cmd_kill_all(args: argparse.Namespace) -> int:
    if not args.yes:
        sys.stderr.write("vigil: refuse kill-all without --yes\n")
        return 2
    refused = _refuse_agent()
    if refused is not None:
        return refused
    snap = collect(home=_home(args))
    results = []
    failed = False
    for session in snap["sessions"]:
        pid = int(session["pid"])
        try:
            result = kill_agent(pid, sig=args.signal)
        except KillRefused as exc:
            failed = True
            results.append({"ok": False, "pid": pid, "error": str(exc)})
            continue
        results.append(
            {
                "ok": True,
                "pid": result.pid,
                "agent": result.agent,
                "signal": result.signal,
            }
        )
    sys.stdout.write(json.dumps({"ok": not failed, "results": results}) + "\n")
    return 1 if failed else 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = Path(args.path) if args.path else _plugin_root()
    try:
        assert_valid(root)
    except PluginInvalid as exc:
        for err in exc.errors:
            sys.stderr.write(f"vigil: {err}\n")
        return 1
    sys.stdout.write(json.dumps({"ok": True, "id": PLUGIN_ID, "root": str(root)}) + "\n")
    return 0


def cmd_prove(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    helper = args.helper or _helper()
    report = run_prove(home, helper=helper, mint=not args.check)
    sys.stdout.write(dumps_prove(report))
    return 0 if report.get("ok") else 1


def cmd_version(_: argparse.Namespace) -> int:
    sys.stdout.write(f"{PLUGIN_ID} {__version__}\n")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    raw = sys.stdin.read()
    try:
        result = gate_payload(raw, home=_home(args))
    except Exception as exc:  # last-resort: still speak hook JSON
        payload = {
            "decision": "deny",
            "reason": f"Vigil crashed: {exc}",
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"Vigil crashed: {exc}",
            },
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        return 0
    sys.stdout.write(json.dumps(result.response) + "\n")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    action = args.action
    if action not in ACTIONS:
        sys.stderr.write(f"vigil: unknown action {action!r}\n")
        return 2
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    try:
        req = request_path(home, args.id)
    except ValueError:
        sys.stderr.write("vigil: invalid pending id\n")
        sys.stdout.write(json.dumps({"ok": False, "error": "invalid pending id"}) + "\n")
        return 2
    kind = "tool"
    try:
        data = json.loads(req.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            kind = str(data.get("kind") or "tool")
    except (OSError, json.JSONDecodeError):
        data = {}
    if kind in {"away", "surprise"}:
        policy = load_policy(home)
        if action in {"allow", "session", "always", "unfreeze"}:
            policy.unfreeze()
            save_policy(home, policy)
        elif action == "rewind":
            project = str((data or {}).get("cwd") or "")
            result = rewind(home, project_root=project)
            policy.unfreeze()
            save_policy(home, policy)
            cleanup(home, args.id)
            sys.stdout.write(json.dumps({"ok": True, "id": args.id, "action": "rewind", "rewind": result}) + "\n")
            return 0
        # deny: stay frozen, dismiss the card
        cleanup(home, args.id)
        sys.stdout.write(
            json.dumps({"ok": True, "id": args.id, "action": action, "kind": kind, "frozen": policy.effective_mode() == "frozen"})
            + "\n"
        )
        return 0
    path = write_decision(home, args.id, action, source="cli")
    sys.stdout.write(json.dumps({"ok": True, "id": args.id, "action": action, "path": str(path)}) + "\n")
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    rows = list_pending(_home(args))
    sys.stdout.write(json.dumps({"ok": True, "pending": rows}) + "\n")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    policy.freeze()
    save_policy(home, policy)
    from vigil.pause import pause_all

    paused = pause_all(home)
    sys.stdout.write(
        json.dumps({"ok": True, "mode": policy.effective_mode(), "frozen": True, "paused": paused})
        + "\n"
    )
    return 0


def cmd_unfreeze(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    policy.unfreeze()
    save_policy(home, policy)
    from vigil.pause import resume_all

    resumed = resume_all(home)
    sys.stdout.write(
        json.dumps(
            {"ok": True, "mode": policy.effective_mode(), "frozen": False, "resumed": resumed}
        )
        + "\n"
    )
    return 0


def cmd_mode(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    if args.mode is None:
        sys.stdout.write(json.dumps({"ok": True, "mode": policy.effective_mode()}) + "\n")
        return 0
    if args.mode == "cycle":
        policy.cycle_mode()
    else:
        policy.set_mode(args.mode)
    save_policy(home, policy)
    sys.stdout.write(json.dumps({"ok": True, "mode": policy.effective_mode()}) + "\n")
    return 0


def cmd_alert(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    if args.channel is None:
        sys.stdout.write(json.dumps({"ok": True, "alert": policy.alert}) + "\n")
        return 0
    if args.channel == "cycle":
        policy.cycle_alert()
    else:
        policy.set_alert(args.channel)
    save_policy(home, policy)
    sys.stdout.write(json.dumps({"ok": True, "alert": policy.alert}) + "\n")
    return 0


def cmd_trust(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    if args.clear:
        policy.clear_trust()
        save_policy(home, policy)
        sys.stdout.write(json.dumps({"ok": True, "trusted": False}) + "\n")
        return 0
    root = args.root
    if not root:
        snap = collect(home=home)
        sessions = snap.get("sessions") or []
        root = str(sessions[0]["cwd"]) if sessions and sessions[0].get("cwd") else str(home)
    if getattr(args, "until_lock", False):
        policy.trust_until_lid(root)
    else:
        policy.trust_for(args.minutes, root)
    save_policy(home, policy)
    sys.stdout.write(
        json.dumps(
            {
                "ok": True,
                "trustRoot": policy.trust_root,
                "trustUntil": policy.trust_until,
                "trustUntilLock": policy.trust_until_lock,
            }
        )
        + "\n"
    )
    return 0


def cmd_last_denied(args: argparse.Namespace) -> int:
    row = read_last_denied(_home(args))
    if not row:
        sys.stdout.write(json.dumps({"ok": False, "error": "nothing denied yet"}) + "\n")
        return 1
    sys.stdout.write(json.dumps({"ok": True, "denied": row}) + "\n")
    return 0


def cmd_panic(args: argparse.Namespace) -> int:
    if not args.yes:
        sys.stderr.write("vigil: refuse panic without --yes\n")
        return 2
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    policy.freeze()
    save_policy(home, policy)
    snap = collect(home=home)
    results = []
    failed = False
    sig = getattr(args, "signal", "term")
    for session in snap["sessions"]:
        pid = int(session["pid"])
        try:
            result = kill_agent(pid, sig=sig)
        except KillRefused as exc:
            failed = True
            results.append({"ok": False, "pid": pid, "error": str(exc)})
            continue
        results.append({"ok": True, "pid": result.pid, "agent": result.agent})
    sys.stdout.write(
        json.dumps({"ok": not failed, "frozen": True, "results": results}) + "\n"
    )
    return 1 if failed else 0


def cmd_install(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    helper = args.helper or _helper()
    written = install_hooks(_home(args), helper)
    sys.stdout.write(json.dumps({"ok": True, "written": written}) + "\n")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    helper = args.helper or _helper()
    removed = uninstall_hooks(_home(args), helper)
    sys.stdout.write(json.dumps({"ok": True, "removed": removed}) + "\n")
    return 0


def cmd_envelope(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    if not args.id:
        sys.stdout.write(json.dumps({"ok": False, "error": "passport id required"}) + "\n")
        return 2
    if args.envelope == "cycle" or args.envelope is None:
        row = cycle_envelope(home, args.id)
    else:
        row = set_envelope(home, args.id, args.envelope)
    sys.stdout.write(json.dumps({"ok": True, "passport": row}) + "\n")
    return 0


def cmd_rewind(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    result = rewind(
        home,
        project_root=args.root or "",
        session_id=getattr(args, "session", "") or "",
    )
    sys.stdout.write(json.dumps(result) + "\n")
    return 0


def cmd_lid(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    if args.action == "off":
        policy.set_lid(False)
        save_policy(home, policy)
    elif args.action == "on":
        policy.set_lid(True)
        save_policy(home, policy)
    elif args.action == "cycle":
        policy.set_lid(not policy.lid)
        save_policy(home, policy)
    elif args.action == "sync":
        state = lid_sync(home)
        sys.stdout.write(json.dumps({"ok": True, **state}) + "\n")
        return 0
    sys.stdout.write(json.dumps({"ok": True, "lid": load_policy(home).lid}) + "\n")
    return 0


def cmd_spawn(args: argparse.Namespace) -> int:
    """Record an envelope for a launch. Exec only with --exec."""
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    agent = args.agent
    project = args.project or str(Path.cwd())
    env = normalize_envelope(args.envelope)
    from vigil.passport import upsert

    paper = upsert(
        home,
        agent=agent,
        cwd=project,
        envelope=env,
        parent=getattr(args, "parent", "") or "",
        inherit_tickets=False if getattr(args, "parent", "") else None,
    )
    command = [agent]
    plan = {
        "ok": True,
        "passport": paper,
        "command": command,
        "cwd": project,
        "envelope": env,
        "exec": bool(args.exec),
        "cage": bool(getattr(args, "cage", False)),
        "note": "Filesystem is not jailed. --cage drops the network namespace only.",
    }
    if getattr(args, "cage", False):
        from vigil.cage import CageRefused, plan as cage_plan

        try:
            spec = cage_plan(command, cwd=project, net=False)
        except CageRefused as exc:
            sys.stderr.write(f"vigil: {exc}\n")
            sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}) + "\n")
            return 2
        plan["command"] = spec["argv"]
        plan["note"] = spec["note"]
        if not args.exec:
            sys.stdout.write(json.dumps(plan) + "\n")
            return 0
        from vigil.cage import exec_caged

        exec_caged(command, cwd=project, net=False)
        return 1  # pragma: no cover
    if not args.exec:
        sys.stdout.write(json.dumps(plan) + "\n")
        return 0
    os.chdir(project)
    os.execvp(agent, [agent])
    return 1  # pragma: no cover


def cmd_tickets(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    home = _home(args)
    policy = load_policy(home)
    if args.action == "revoke":
        if not args.key:
            sys.stderr.write("vigil: ticket key required\n")
            return 2
        hit = policy.revoke(args.key)
        save_policy(home, policy)
        sys.stdout.write(json.dumps({"ok": True, "revoked": hit, "key": args.key}) + "\n")
        return 0
    sys.stdout.write(
        json.dumps({"ok": True, "allow": sorted(policy.allow_keys), "deny": sorted(policy.deny_keys)})
        + "\n"
    )
    return 0


def cmd_folder(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    from vigil.folders import drop, list_folders, upsert

    home = _home(args)
    if args.drop:
        if not args.path:
            sys.stderr.write("vigil: folder path required\n")
            return 2
        sys.stdout.write(json.dumps({"ok": True, "dropped": drop(home, args.path)}) + "\n")
        return 0
    if not args.path:
        sys.stdout.write(json.dumps({"ok": True, "folders": list_folders(home)}) + "\n")
        return 0
    env = args.envelope or "project"
    row = upsert(
        home,
        args.path,
        env,
        exclusive=True if args.exclusive else (False if args.shared else None),
        cage=True if args.cage else None,
    )
    sys.stdout.write(json.dumps({"ok": True, "folder": row}) + "\n")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    from vigil.audit import tail as audit_tail

    rows = audit_tail(_home(args), limit=max(1, min(500, int(args.limit))))
    sys.stdout.write(json.dumps({"ok": True, "rows": rows}) + "\n")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    refused = _refuse_agent()
    if refused is not None:
        return refused
    from vigil.dossier import summarize

    sys.stdout.write(json.dumps({"ok": True, "brief": summarize(_home(args))}) + "\n")
    return 0


def cmd_machine(args: argparse.Namespace) -> int:
    from vigil.machine import read, write

    home = _home(args)
    if args.write:
        refused = _refuse_agent()
        if refused is not None:
            return refused
        path = write(home)
        sys.stdout.write(json.dumps({"ok": True, "path": str(path)}) + "\n")
        return 0
    text = read(home)
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vigil",
        description="Permission broker for coding agents on Omarchy.",
    )
    parser.add_argument("--home", default=None, help="Override $HOME (tests).")
    sub = parser.add_subparsers(dest="cmd", required=True)

    snap = sub.add_parser("snapshot", help="Live agents + pending approvals.")
    snap.add_argument("--pretty", action="store_true")
    snap.add_argument("--write", metavar="PATH")
    snap.add_argument("--state", action="store_true")
    snap.set_defaults(func=cmd_snapshot)

    kill_p = sub.add_parser("kill", help="SIGTERM one classified agent pid.")
    kill_p.add_argument("pid", type=int)
    kill_p.add_argument("--signal", default="term")
    kill_p.set_defaults(func=cmd_kill)

    kill_all = sub.add_parser("kill-all", help="SIGTERM every classified agent.")
    kill_all.add_argument("--yes", action="store_true")
    kill_all.add_argument("--signal", default="term")
    kill_all.set_defaults(func=cmd_kill_all)

    val = sub.add_parser("validate", help="Validate this plugin tree.")
    val.add_argument("path", nargs="?", default=None)
    val.set_defaults(func=cmd_validate)

    ver = sub.add_parser("version")
    ver.set_defaults(func=cmd_version)

    prove = sub.add_parser(
        "prove",
        help="Safe glass proof. Mints a drill card. Never deletes anything.",
    )
    prove.add_argument(
        "--check",
        action="store_true",
        help="Only classify and check hooks. Do not mint a card.",
    )
    prove.add_argument("--helper", default=None)
    prove.set_defaults(func=cmd_prove)

    gate = sub.add_parser("gate", help="PreToolUse hook. Reads JSON on stdin.")
    gate.set_defaults(func=cmd_gate)

    decide = sub.add_parser("decide", help="Answer a pending approval.")
    decide.add_argument("id")
    decide.add_argument("action", choices=sorted(ACTIONS))
    decide.set_defaults(func=cmd_decide)

    pending = sub.add_parser("pending", help="List waiting approvals.")
    pending.set_defaults(func=cmd_pending)

    freeze = sub.add_parser("freeze", help="Deny every tool call until unfreeze.")
    freeze.set_defaults(func=cmd_freeze)
    unfreeze = sub.add_parser("unfreeze")
    unfreeze.set_defaults(func=cmd_unfreeze)

    mode = sub.add_parser("mode", help="off | seatbelt | ask | frozen | cycle")
    mode.add_argument("mode", nargs="?", choices=list(MODES) + ["cycle"])
    mode.set_defaults(func=cmd_mode)

    last = sub.add_parser("last-denied", help="Last command Vigil blocked.")
    last.set_defaults(func=cmd_last_denied)

    alert = sub.add_parser("alert", help="bar | toast | both | cycle")
    alert.add_argument("channel", nargs="?", choices=list(ALERTS) + ["cycle"])
    alert.set_defaults(func=cmd_alert)

    trust = sub.add_parser("trust", help="Seatbelt-only for this project for N minutes.")
    trust.add_argument("minutes", nargs="?", type=int, default=60)
    trust.add_argument("--root", default=None)
    trust.add_argument("--clear", action="store_true")
    trust.add_argument("--until-lock", action="store_true", help="Trust until the screen locks.")
    trust.set_defaults(func=cmd_trust)

    panic = sub.add_parser("panic", help="Freeze + kill every agent.")
    panic.add_argument("--yes", action="store_true")
    panic.add_argument("--signal", default="term")
    panic.set_defaults(func=cmd_panic)

    inst = sub.add_parser("install", help="Install Grok/Claude PreToolUse hooks.")
    inst.add_argument("--helper", default=None, help="Absolute path to bin/vigil.")
    inst.set_defaults(func=cmd_install)

    uninst = sub.add_parser("uninstall", help="Remove Vigil hooks.")
    uninst.add_argument("--helper", default=None)
    uninst.set_defaults(func=cmd_uninstall)

    env_p = sub.add_parser("envelope", help="seatbelt | project | hermit | desktop | read | cycle")
    env_p.add_argument("id", help="Passport id")
    env_p.add_argument("envelope", nargs="?", default="cycle", choices=list(ENVELOPES) + ["cycle"])
    env_p.set_defaults(func=cmd_envelope)

    rew = sub.add_parser("rewind", help="Restore git-tracked files this session touched.")
    rew.add_argument("--root", default=None)
    rew.add_argument("--session", default="", help="Only files this session id touched.")
    rew.set_defaults(func=cmd_rewind)

    lid = sub.add_parser("lid", help="on | off | cycle | sync")
    lid.add_argument("action", nargs="?", default="sync", choices=["on", "off", "cycle", "sync"])
    lid.set_defaults(func=cmd_lid)

    spawn = sub.add_parser("spawn", help="Stamp an envelope for a launch. --exec to exec.")
    spawn.add_argument("agent")
    spawn.add_argument("--project", default=None)
    spawn.add_argument("--envelope", default="project")
    spawn.add_argument("--parent", default="", help="Parent passport id for a helper.")
    spawn.add_argument("--exec", action="store_true")
    spawn.add_argument("--cage", action="store_true", help="Drop network (bwrap unshare-net). Fail closed.")
    spawn.set_defaults(func=cmd_spawn)

    tickets = sub.add_parser("tickets", help="List or revoke Always / deny-always tickets.")
    tickets.add_argument("action", nargs="?", default="list", choices=["list", "revoke"])
    tickets.add_argument("key", nargs="?", default="")
    tickets.set_defaults(func=cmd_tickets)

    folder = sub.add_parser("folder", help="Per-folder lease. Human only.")
    folder.add_argument("path", nargs="?", default=None)
    folder.add_argument("envelope", nargs="?", default=None, choices=list(ENVELOPES))
    folder.add_argument("--drop", action="store_true")
    folder.add_argument("--exclusive", action="store_true", help="One writer for this folder.")
    folder.add_argument("--shared", action="store_true")
    folder.add_argument("--cage", action="store_true")
    folder.set_defaults(func=cmd_folder)

    log_p = sub.add_parser("log", help="Read the local black box (already redacted).")
    log_p.add_argument("--limit", type=int, default=50)
    log_p.set_defaults(func=cmd_log)

    brief = sub.add_parser("brief", help="Today's counts. Not a blocking card.")
    brief.set_defaults(func=cmd_brief)

    machine = sub.add_parser("machine", help="Print the machine card agents may read.")
    machine.add_argument("--write", action="store_true")
    machine.set_defaults(func=cmd_machine)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
