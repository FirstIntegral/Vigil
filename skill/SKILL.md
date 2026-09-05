# Vigil

You are on Omarchy. Vigil is the seatbelt for your tool calls.

YOLO is fine for ordinary work inside the lease: project edits, tests, in-repo git. Do not route around the polkit card. If a card is on screen, wait for the human. If nobody answers, the call is denied.

## House law

- Article I: Never delete `/` or `$HOME`.
- Article II: Never pipe the internet into a shell (`curl | sh`, `wget | bash`).
- Article III: Never format a disk or write raw to `/dev`.
- Article IV: Never force-push `main` or `master`.
- Article V: Never inject an Omarchy plugin or kill the compositor unless the human already allowed it.

A short card about this computer may exist at `~/.config/vigil/MACHINE.md`. Read it. Do not edit it.

## Do not

- Do not run `vigil decide`. That is how a human answers a card. An agent answering its own card is blocked.
- Do not run `vigil mode`, `vigil unfreeze`, `vigil install`, `vigil uninstall`, `vigil tickets`, `vigil folder`, or `vigil log`.
- Do not write under `~/.local/state/vigil/` or `~/.config/vigil/`.
- Do not write under `~/.config/omarchy/plugins/` or the Grok/Claude hook files.
- Do not run `omarchy plugin add` / `enable` / `remove` unless the human already allowed that ticket.
- Do not treat silence as permission. Silence is deny.
