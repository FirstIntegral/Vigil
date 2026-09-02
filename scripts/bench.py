#!/usr/bin/env python3
"""Measure Vigil's cost on this machine. Prints JSON. No invented numbers."""

from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "bin" / "vigil"
N_SPAWN = 40
N_INPROC = 200
WARMUP = 5

ALLOW_PAYLOAD = json.dumps(
    {
        "hookEventName": "pre_tool_use",
        "sessionId": "bench",
        "cwd": str(ROOT),
        "workspaceRoot": str(ROOT),
        "permissionMode": "always-approve",
        "toolName": "run_terminal_command",
        "toolInput": {"command": "pytest"},
    }
).encode()


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return s[lo]
    return s[lo] * (hi - k) + s[hi] * (k - lo)


def summarize(xs: list[float]) -> dict[str, float]:
    if not xs:
        return {"n": 0, "min": 0, "median": 0, "p95": 0, "max": 0, "mean": 0}
    return {
        "n": len(xs),
        "min": min(xs),
        "median": statistics.median(xs),
        "p95": _pct(xs, 0.95),
        "max": max(xs),
        "mean": statistics.fmean(xs),
    }


def read_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def hardware() -> dict[str, object]:
    cpu = read_kv(Path("/proc/cpuinfo"))
    mem = read_kv(Path("/proc/meminfo"))
    product = ""
    for p in (
        Path("/sys/class/dmi/id/product_version"),
        Path("/sys/class/dmi/id/product_name"),
        Path("/sys/devices/virtual/dmi/id/product_version"),
    ):
        try:
            product = p.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if product:
            break
    nproc = os.cpu_count() or 0
    mem_kb = int(mem.get("MemTotal", "0").split()[0] or 0)
    return {
        "host": os.uname().nodename,
        "kernel": os.uname().release,
        "product": product,
        "cpu": cpu.get("model name") or cpu.get("Hardware") or "",
        "cpus": nproc,
        "ramMiB": round(mem_kb / 1024),
        "python": sys.version.split()[0],
        "helper": str(HELPER),
    }


def rss_kib(pid: int) -> int:
    kv = read_kv(Path(f"/proc/{pid}/status"))
    raw = kv.get("VmRSS", "0 kB").split()[0]
    try:
        return int(raw)
    except ValueError:
        return 0


def comm(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode("utf-8", "replace").strip()


def live_processes(limit: int = 12) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    proc = Path("/proc")
    for ent in proc.iterdir():
        if not ent.name.isdigit():
            continue
        pid = int(ent.name)
        kib = rss_kib(pid)
        if kib <= 0:
            continue
        name = comm(pid)
        line = cmdline(pid)
        rows.append(
            {
                "pid": pid,
                "comm": name,
                "rssMiB": round(kib / 1024, 1),
                "rssKiB": kib,
                "cmd": line[:120],
            }
        )
    rows.sort(key=lambda r: int(r["rssKiB"]), reverse=True)
    return rows[:limit]


def find_procs(needle: str) -> list[dict[str, object]]:
    hits = []
    for ent in Path("/proc").iterdir():
        if not ent.name.isdigit():
            continue
        pid = int(ent.name)
        line = cmdline(pid).lower()
        name = comm(pid).lower()
        if needle.lower() in line or needle.lower() in name:
            kib = rss_kib(pid)
            hits.append(
                {
                    "pid": pid,
                    "comm": comm(pid),
                    "rssMiB": round(kib / 1024, 1),
                    "cmd": cmdline(pid)[:140],
                }
            )
    hits.sort(key=lambda r: r["rssMiB"], reverse=True)
    return hits


def spawn_timed(argv: list[str], stdin: bytes | None, n: int, env: dict[str, str] | None = None) -> dict[str, object]:
    times: list[float] = []
    code = 0
    for i in range(WARMUP + n):
        t0 = time.perf_counter()
        proc = subprocess.run(
            argv,
            input=stdin,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            check=False,
        )
        dt = time.perf_counter() - t0
        if i >= WARMUP:
            times.append(dt)
        code = proc.returncode
    rss_kib_max = max_rss_kib(argv, stdin, env)
    stats = summarize([x * 1000 for x in times])  # ms
    return {"ms": stats, "maxRssKiB": rss_kib_max, "exit": code, "argv": argv}


def max_rss_kib(argv: list[str], stdin: bytes | None, env: dict[str, str] | None) -> int:
    """Child peak RSS in KiB via RUSAGE_CHILDREN, isolated in a helper process."""
    probe = (
        "import resource, subprocess, sys\n"
        "argv = sys.argv[1:]\n"
        "data = sys.stdin.buffer.read()\n"
        "subprocess.run(argv, input=data or None, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL)\n"
        "print(resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe, *argv],
        input=stdin or b"",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
        check=False,
    )
    try:
        return int((proc.stdout or b"0").decode().strip().splitlines()[-1])
    except (ValueError, IndexError):
        return 0


def inproc_gate(n: int) -> dict[str, object]:
    sys.path.insert(0, str(ROOT))
    from vigil.gate import gate_payload  # noqa: WPS433

    times: list[float] = []
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        payload = json.loads(ALLOW_PAYLOAD)
        for i in range(WARMUP + n):
            t0 = time.perf_counter()
            gate_payload(payload, home=home, wait_fn=lambda *_: None, audit=False)
            dt = time.perf_counter() - t0
            if i >= WARMUP:
                times.append(dt)
    return {"ms": summarize([x * 1000 for x in times])}


def cpu_sample(pid: int, seconds: float = 3.0) -> dict[str, object]:
    """Percent of one core over `seconds`, from /proc pid stat + /proc/stat."""
    def tick(path: Path, field: int) -> int:
        try:
            parts = path.read_text(encoding="utf-8").split()
            return int(parts[field])
        except (OSError, IndexError, ValueError):
            return 0

    hz = os.sysconf("SC_CLK_TCK")
    p = Path(f"/proc/{pid}/stat")
    t0 = time.perf_counter()
    u0 = tick(p, 13) + tick(p, 14)
    time.sleep(seconds)
    t1 = time.perf_counter()
    u1 = tick(p, 13) + tick(p, 14)
    dt = t1 - t0
    if dt <= 0:
        return {"pid": pid, "cpuPctOneCore": 0.0, "seconds": seconds}
    pct = ((u1 - u0) / hz) / dt * 100.0
    return {"pid": pid, "comm": comm(pid), "cpuPctOneCore": round(pct, 2), "seconds": seconds}


def main() -> int:
    os.environ.setdefault("VIGIL_SILENT", "1")
    env = os.environ.copy()
    env["VIGIL_SILENT"] = "1"
    helper = str(HELPER)
    with tempfile.TemporaryDirectory() as tmp:
        home = tmp
        snap = spawn_timed([helper, "--home", home, "snapshot"], None, N_SPAWN, env)
        gate = spawn_timed([helper, "--home", home, "gate"], ALLOW_PAYLOAD, N_SPAWN, env)
    inproc = inproc_gate(N_INPROC)
    top = live_processes(12)
    qs = find_procs("omarchy-shell") or find_procs("/usr/bin/qs") or find_procs("quickshell")
    grok = find_procs("grok")
    hypr = find_procs("Hyprland")
    cpu_qs = cpu_sample(int(qs[0]["pid"]), 3.0) if qs else {}
    report = {
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hardware": hardware(),
        "alwaysOn": {
            "daemon": False,
            "ui": "QML plugin inside omarchy-shell (keepLoaded)",
            "poll": "python3 bin/vigil snapshot once per refreshIntervalSec (default 2s)",
            "gate": "python3 bin/vigil gate spawned per hooked tool call, then exits",
        },
        "snapshotSpawn": snap,
        "gateAllowSpawn": gate,
        "gateAllowInProcess": inproc,
        "omarchyShell": qs[:3],
        "omarchyShellCpu": cpu_qs,
        "grok": grok[:5],
        "hyprland": hypr[:2],
        "topRss": top,
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
