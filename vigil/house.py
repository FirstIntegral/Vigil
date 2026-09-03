"""Five house-law articles. Quoted on the polkit card. Not a policy compiler."""

from __future__ import annotations

from pathlib import Path

ARTICLES = (
    ("I", "Never delete / or $HOME."),
    ("II", "Never pipe the internet into a shell."),
    ("III", "Never format a disk or write raw to /dev."),
    ("IV", "Never force-push main or master."),
    ("V", "Never inject a plugin or kill the compositor unless a human allowed it."),
)

_CLASS_ARTICLE = {
    "rm-root": 0,
    "pipe-shell": 1,
    "mkfs": 2,
    "dd-device": 2,
    "force-main": 3,
    "desktop-kill": 4,
    "plugin-inject": 4,
    "self-approve": 4,
    "glass-proof": 0,
    "run-tmp": 1,
    "power": 2,
    "chmod-root": 0,
    "fork-bomb": 0,
}


def article_for(class_id: str) -> str:
    idx = _CLASS_ARTICLE.get(class_id)
    if idx is None:
        return ""
    roman, text = ARTICLES[idx]
    return f"Article {roman} · {text}"


def skill_markdown() -> str:
    path = Path(__file__).resolve().parents[1] / "skill" / "SKILL.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    lines = [
        "# Vigil",
        "",
        "You are on Omarchy. Vigil is the seatbelt for your tool calls.",
        "YOLO is fine for ordinary work inside the lease. Do not route around the polkit card.",
        "",
        "## House law",
    ]
    for roman, text in ARTICLES:
        lines.append(f"- Article {roman}: {text}")
    lines.extend(
        [
            "",
            "## Do not",
            "",
            "- Do not run `vigil decide`. That is how a human answers a card.",
            "- Do not run `vigil mode`, `vigil unfreeze`, `vigil install`, or `vigil uninstall`.",
            "- Do not write under `~/.local/state/vigil/` or `~/.config/vigil/`.",
            "- Do not write under `~/.config/omarchy/plugins/` or hook files.",
            "- Do not run `omarchy plugin add` unless the human already allowed it.",
            "- Do not treat silence as permission. Silence is deny.",
            "",
        ]
    )
    return "\n".join(lines)
