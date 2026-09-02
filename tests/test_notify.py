from __future__ import annotations

import os
import unittest

from vigil.notify import DEFAULT_ALERT, GLYPH_ALERT, GLYPH_EYE, silent, toast_command, wants_toast


class NotifyTests(unittest.TestCase):
    def test_unittest_is_silent(self) -> None:
        self.assertTrue(silent())
        self.assertFalse(wants_toast("toast"))
        self.assertFalse(wants_toast("both"))
        self.assertFalse(wants_toast("bar"))

    def test_default_alert_is_both(self) -> None:
        self.assertEqual(DEFAULT_ALERT, "both")


class ToastCommandTests(unittest.TestCase):
    def test_uses_eye_not_security_high(self) -> None:
        cmd = toast_command("Vigil", "held", urgency="normal")
        self.assertIsNotNone(cmd)
        joined = " ".join(cmd or [])
        self.assertNotIn("security-high", joined)
        self.assertIn(GLYPH_EYE, cmd or [])

    def test_critical_uses_alert_glyph(self) -> None:
        cmd = toast_command("Vigil", "frozen", urgency="critical")
        self.assertIn(GLYPH_ALERT, cmd or [])


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
