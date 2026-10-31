import unittest
from unittest.mock import Mock
from session_activity import SessionActivity

XML = '<node><interface name="org.freedesktop.ScreenSaver"><method name="GetActive"><arg type="b" direction="out"/></method></interface></node>'


class SessionActivityTests(unittest.TestCase):
    def test_initial_locked_missing_bus_reconnect_and_duplicates(self):
        query = Mock(side_effect=[XML, 'true', XML, 'false', XML, 'false', OSError('no bus'), XML, 'false'])
        adapter = SessionActivity(query=query)
        self.assertIs(adapter.poll(), False)
        self.assertIs(adapter.poll(), True)
        self.assertIs(adapter.poll(), True)
        self.assertIsNone(adapter.poll())
        self.assertIs(adapter.poll(), True)

    def test_unknown_contract_or_non_boolean_is_closed(self):
        for responses in [ ['<node/>'], [XML, 'no'], [XML, ''] ]:
            self.assertIsNone(SessionActivity(query=Mock(side_effect=responses)).poll())
