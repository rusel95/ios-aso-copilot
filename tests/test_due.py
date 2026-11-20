"""The reads calendar: which sweeps a live rank hypothesis still needs at the end of its window."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import SAMPLE, run  # noqa: E402

from aso.ledger_state import reads_due  # noqa: E402
from aso.store import read_hypotheses, read_ranks  # noqa: E402


def due(as_of, hyps=None, rows=None):
    hyps = read_hypotheses(SAMPLE, kinds=("H", "C")) if hyps is None else hyps
    return reads_due(hyps, read_ranks(SAMPLE) if rows is None else rows, dt.date.fromisoformat(as_of))


class ReadsDue(unittest.TestCase):
    def test_the_last_three_days_of_the_window_without_a_read(self):
        # H005 went live 2026-10-20 for 14 days: its window ends 2026-11-03, and the sample swept on 2026-11-02
        mine = [d for d in due("2026-11-03") if d["id"] == "H005"]
        self.assertEqual([d["day"] for d in mine], ["2026-11-01", "2026-11-03"])
        self.assertEqual(mine[0], {"id": "H005", "market": "ua", "queries": ["приплив", "графік припливів"], "day": "2026-11-01"})

    def test_a_day_still_ahead_is_not_due(self):
        self.assertEqual([d["day"] for d in due("2026-11-01") if d["id"] == "H005"], ["2026-11-01"])
        self.assertEqual([d for d in due("2026-10-31") if d["id"] == "H005"], [])

    def test_only_live_unjudged_rank_hypotheses_are_asked_for(self):
        ids = {d["id"] for d in due("2026-12-31")}
        self.assertIn("H005", ids)
        self.assertNotIn("H001", ids)      # judged
        self.assertNotIn("H007", ids)      # never shipped
        self.assertNotIn("C001", ids)      # a channel experiment is not read by rank
        funnel = [{"id": "H900", "markets": "us", "queries": "tide times", "went_live": "2026-10-20", "window_days": "14",
                   "primary_signal": "funnel"}]
        self.assertEqual(due("2026-11-03", hyps=funnel), [])

    def test_a_hypothesis_with_no_basket_asks_for_nothing(self):
        hyp = [{"id": "H902", "markets": "us", "queries": "", "went_live": "2026-10-20", "window_days": "14"}]
        self.assertEqual(due("2026-11-03", hyps=hyp), [])

    def test_one_entry_per_storefront_and_a_failed_request_is_not_a_read(self):
        hyp = [{"id": "H901", "markets": "us, ua", "queries": "tide times", "went_live": "2026-10-20", "window_days": "14"}]
        rows = [{"date": "2026-11-03", "market": "us", "keyword": "tide times", "position": 9, "status": "ok"},
                {"date": "2026-11-03", "market": "ua", "keyword": "tide times", "position": None, "status": "error"},
                {"date": "2026-11-02", "market": "ua", "keyword": "tide times", "position": None, "status": "beyond-depth"}]
        self.assertEqual([(d["market"], d["day"]) for d in due("2026-11-03", hyps=hyp, rows=rows)],
                         [("us", "2026-11-01"), ("us", "2026-11-02"), ("ua", "2026-11-01"), ("ua", "2026-11-03")])


class DueCommand(unittest.TestCase):
    def test_it_prints_one_line_a_read_and_marks_the_days_gone_by(self):
        code, out, err = run("copilot.py", "due", "--store", str(SAMPLE), "--as-of", "2026-11-03")
        self.assertEqual(code, 0, out + err)
        lines = [line for line in out.splitlines() if "H005" in line]
        self.assertEqual(lines, ["2026-11-01  H005  ua  приплив; графік припливів  (missed)",
                                 "2026-11-03  H005  ua  приплив; графік припливів"])

    def test_nothing_due(self):
        code, out, _ = run("copilot.py", "due", "--store", str(SAMPLE), "--as-of", "2026-10-01")
        self.assertEqual((code, out.strip()), (0, "Nothing due."))


if __name__ == "__main__":
    unittest.main()
