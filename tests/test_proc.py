from __future__ import annotations

import unittest

from vigil.proc import parse_stat, parse_status_rss_uid


class ParseStatTests(unittest.TestCase):
    def test_simple_comm(self) -> None:
        # pid 10931 (grok) S ... starttime field 22
        fields_after_comm = ["S"] + ["0"] * 18 + ["12345"]
        text = "10931 (grok) " + " ".join(fields_after_comm)
        self.assertEqual(parse_stat(text), ("grok", "S", 12345))

    def test_comm_with_spaces(self) -> None:
        fields_after_comm = ["R"] + ["0"] * 18 + ["9"]
        text = "42 (not an agent) " + " ".join(fields_after_comm)
        self.assertEqual(parse_stat(text), ("not an agent", "R", 9))

    def test_garbage(self) -> None:
        self.assertIsNone(parse_stat("no parens here"))
        self.assertIsNone(parse_stat("1 (short)"))


class ParseStatusTests(unittest.TestCase):
    def test_rss_and_uid(self) -> None:
        text = "Name:\tgrok\nUid:\t1000\t1000\t1000\t1000\nVmRSS:\t  42100 kB\n"
        rss, uid = parse_status_rss_uid(text)
        self.assertEqual(uid, 1000)
        self.assertEqual(rss, 42100 * 1024)

    def test_missing(self) -> None:
        rss, uid = parse_status_rss_uid("")
        self.assertEqual((rss, uid), (0, 0))


if __name__ == "__main__":
    unittest.main()
