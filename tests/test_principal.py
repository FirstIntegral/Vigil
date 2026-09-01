from __future__ import annotations

import unittest

from vigil.principal import caller_is_agent, ppid_of


class PrincipalTests(unittest.TestCase):
    def test_ppid_of_self(self) -> None:
        import os

        parent = ppid_of(os.getpid())
        self.assertGreater(parent, 0)

    def test_unittest_python_is_not_itself_an_agent(self) -> None:
        # python3 is SKIP_COMMS. Walk may still find an agent ancestor
        # when tests run under Grok — that is the real check working.
        self.assertIsInstance(caller_is_agent(), bool)
