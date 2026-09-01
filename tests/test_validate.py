from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from vigil.validate import validate_manifest_obj, validate_plugin_dir


MINIMAL = {
    "schemaVersion": 1,
    "id": "xyz.brwsk.vigil",
    "name": "Vigil",
    "version": "0.1.0",
    "kinds": ["service", "bar-widget"],
    "entryPoints": {"service": "Service.qml", "barWidget": "BarWidget.qml"},
    "barWidget": {"defaultSection": "right"},
}


class ValidateTests(unittest.TestCase):
    def test_rejects_reserved_id(self) -> None:
        manifest = dict(MINIMAL)
        manifest["id"] = "omarchy.vigil"
        errors = validate_manifest_obj(manifest, Path("/tmp"))
        self.assertTrue(any("reserved" in e or "invalid" in e for e in errors))

    def test_rejects_path_escape(self) -> None:
        manifest = dict(MINIMAL)
        manifest["entryPoints"] = {
            "service": "../Service.qml",
            "barWidget": "BarWidget.qml",
        }
        errors = validate_manifest_obj(manifest, Path("/tmp"))
        self.assertTrue(any("unsafe" in e for e in errors))

    def test_rejects_unknown_kind(self) -> None:
        manifest = dict(MINIMAL)
        manifest["kinds"] = ["service", "wizard"]
        errors = validate_manifest_obj(manifest, Path("/tmp"))
        self.assertTrue(any("unknown kind" in e for e in errors))

    def test_real_plugin_tree_is_valid(self) -> None:
        root = Path(__file__).resolve().parent.parent
        errors = validate_plugin_dir(root)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_missing_entry_file(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "manifest.json").write_text(json.dumps(MINIMAL), encoding="utf-8")
            errors = validate_plugin_dir(root)
            self.assertTrue(any("missing" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
