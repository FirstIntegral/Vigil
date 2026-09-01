from __future__ import annotations

import os
import unittest

from vigil.notify import DEFAULT_ALERT, silent, wants_toast


class NotifyTests(unittest.TestCase):
    def test_unittest_is_silent(self) -> None:
        self.assertTrue(silent())
        self.assertFalse(wants_toast("toast"))
        self.assertFalse(wants_toast("both"))
        self.assertFalse(wants_toast("bar"))

    def test_default_alert_is_both(self) -> None:
        self.assertEqual(DEFAULT_ALERT, "both")


class EnvOverrideTests(unittest.TestCase):
    def test_silent_env(self) -> None:
        old = os.environ.get("VIGIL_SILENT")
        os.environ["VIGIL_SILENT"] = "1"
        try:
            self.assertTrue(silent())
        finally:
            if old is None:
                os.environ.pop("VIGIL_SILENT", None)
            else:
                os.environ["VIGIL_SILENT"] = old
