"""Monday weeks, and when one has closed."""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import ROOT  # noqa: E402,F401

from aso.dashboard.weeks import closed, monday  # noqa: E402


class Weeks(unittest.TestCase):
    def test_monday(self):
        self.assertEqual(monday(date(2026, 11, 14)), date(2026, 11, 9))      # a Saturday
        self.assertEqual(monday(date(2026, 11, 9)), date(2026, 11, 9))       # a Monday is its own week start
        self.assertEqual(monday(date(2026, 11, 8)), date(2026, 11, 2))       # a Sunday closes the week before

    def test_closed(self):
        self.assertTrue(closed(date(2026, 11, 2), date(2026, 11, 14)))
        self.assertFalse(closed(date(2026, 11, 9), date(2026, 11, 14)))      # its Sunday is still ahead
        self.assertFalse(closed(date(2026, 11, 2), date(2026, 11, 8)))       # on its own Sunday the week is open
        self.assertTrue(closed(date(2026, 11, 2), date(2026, 11, 9)))        # closed from the Monday after


if __name__ == "__main__":
    unittest.main()
