"""Five house-law articles. Quoted on the polkit card. Not a policy compiler."""

from __future__ import annotations

ARTICLES = (
    ("I", "Never delete / or $HOME."),
    ("II", "Never pipe the internet into a shell."),
    ("III", "Never format a disk or write raw to /dev."),
    ("IV", "Never force-push main."),
    ("V", "Never inject a plugin or kill the compositor unsupervised."),
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
    lines = [
        "# Vigil",
        "",
        "You are on Omarchy. Vigil is the seatbelt for your tool calls.",
        "YOLO is fine inside the lease. Do not route around the card.",
        "",
        "House law:",
    ]
    for roman, text in ARTICLES:
        lines.append(f"- Article {roman}: {text}")
    lines.extend(
        [
            "",
            "Do not run `vigil decide`. Do not write `~/.local/state/vigil/**`.",
            "Do not `omarchy plugin add --yes` unless the human already allowed it.",
            "If a polkit card is up, wait. Silence is deny.",
            "",
        ]
    )
    return "\n".join(lines)
