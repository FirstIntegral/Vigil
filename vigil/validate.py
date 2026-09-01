"""Validate an Omarchy plugin tree the way PluginRegistry.qml does."""

from __future__ import annotations

import json
from pathlib import Path

KIND_TO_ENTRY = {
    "bar-widget": "barWidget",
    "bar": "bar",
    "panel": "panel",
    "overlay": "overlay",
    "menu": "menu",
    "service": "service",
}

REQUIRED_FIELDS = ("id", "name", "version", "kinds", "entryPoints")
RESERVED_PREFIX = "omarchy."


class PluginInvalid(Exception):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


def is_safe_entry_point(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if value.startswith("/"):
        return False
    if ".." in value:
        return False
    return True


def _id_ok(plugin_id: str) -> bool:
    if not plugin_id:
        return False
    if "/" in plugin_id or ".." in plugin_id or plugin_id.startswith("/"):
        return False
    if plugin_id.startswith(RESERVED_PREFIX):
        return False
    return True


def validate_manifest_obj(manifest: object, source_dir: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not an object"]
    if manifest.get("schemaVersion") != 1:
        errors.append("unsupported schemaVersion (want 1)")
    for field in REQUIRED_FIELDS:
        if field not in manifest:
            errors.append(f"missing required field {field!r}")
    plugin_id = str(manifest.get("id", ""))
    if not _id_ok(plugin_id):
        errors.append(f"invalid or reserved plugin id {plugin_id!r}")
    kinds = manifest.get("kinds")
    if not isinstance(kinds, list) or not kinds:
        errors.append("kinds must be a non-empty array")
        kinds = []
    entry_points = manifest.get("entryPoints")
    if not isinstance(entry_points, dict):
        errors.append("entryPoints must be an object")
        entry_points = {}
    bar_widget = manifest.get("barWidget")
    if bar_widget is not None:
        if not isinstance(bar_widget, dict):
            errors.append("barWidget must be an object")
        else:
            default_section = bar_widget.get("defaultSection")
            if default_section is not None and default_section not in {
                "left",
                "center",
                "right",
            }:
                errors.append("invalid barWidget.defaultSection")
    for key, value in entry_points.items():
        if not is_safe_entry_point(value):
            errors.append(f"unsafe entryPoint {key}={value!r}")
            continue
        path = source_dir / str(value)
        if not path.is_file():
            errors.append(f"entryPoint {key} file missing: {value}")
    for kind in kinds:
        if kind not in KIND_TO_ENTRY:
            errors.append(f"unknown kind {kind!r}")
            continue
        ep_key = KIND_TO_ENTRY[kind]
        if ep_key not in entry_points:
            errors.append(f"kind {kind!r} has no entryPoints.{ep_key}")
    return errors


def find_symlinks(root: Path) -> list[str]:
    """Omarchy refuses plugin trees that contain symlinks.

    `.git/` is skipped: a git checkout is how plugins are installed, and
    the official installer clones into the plugin dir. Runtime code paths
    (QML, bin, python) must still be real files.
    """
    found: list[str] = []
    for dirpath, dirnames, filenames in os_walk_skip_git(root):
        here = Path(dirpath)
        for name in list(dirnames) + list(filenames):
            path = here / name
            if path.is_symlink():
                found.append(str(path.relative_to(root)))
    return found


def os_walk_skip_git(root: Path):
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__", ".venv"}]
        yield dirpath, dirnames, filenames


def validate_plugin_dir(root: Path) -> list[str]:
    manifest_path = root / "manifest.json"
    errors: list[str] = []
    if not manifest_path.is_file():
        return ["manifest.json missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"manifest.json is not valid JSON: {exc}"]
    errors.extend(validate_manifest_obj(manifest, root))
    for rel in find_symlinks(root):
        errors.append(f"symlink not allowed: {rel}")
    helper = root / "bin" / "vigil"
    if not helper.is_file():
        errors.append("bin/vigil missing")
    elif not os_access_exec(helper):
        errors.append("bin/vigil is not executable")
    return errors


def os_access_exec(path: Path) -> bool:
    import os

    return os.access(path, os.X_OK)


def assert_valid(root: Path) -> None:
    errors = validate_plugin_dir(root)
    if errors:
        raise PluginInvalid(errors)
