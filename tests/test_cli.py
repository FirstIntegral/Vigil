from __future__ import annotations

import json
import unittest
from io import StringIO
from unittest.mock import patch

from vigil.cli import main


class CliTests(unittest.TestCase):
    def test_version(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            rc = main(["version"])
        self.assertEqual(rc, 0)
        self.assertIn("xyz.brwsk.vigil", buf.getvalue())

    def test_kill_all_requires_yes(self) -> None:
        err = StringIO()
        with patch("sys.stderr", err):
            rc = main(["kill-all"])
        self.assertEqual(rc, 2)
        self.assertIn("--yes", err.getvalue())

    def test_snapshot_schema(self) -> None:
        buf = StringIO()
        with patch("sys.stdout", buf):
            rc = main(["snapshot"])
        self.assertEqual(rc, 0)
        data = json.loads(buf.getvalue())
        self.assertEqual(data["schemaVersion"], 1)
        self.assertEqual(data["pluginId"], "xyz.brwsk.vigil")
        self.assertIsInstance(data["sessions"], list)
        self.assertIn("agents", data["totals"])


if __name__ == "__main__":
    unittest.main()
