"""Hypothesis states and the priority order as data, on the sample store."""
import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import AS_OF, SAMPLE  # noqa: E402

from aso.ledger_state import hypothesis_states, priority  # noqa: E402
from aso.ranks import series, zero_result_keys  # noqa: E402
from aso.store import read_brand_tokens, read_hypotheses, read_markets, read_ranks  # noqa: E402


def states(as_of=AS_OF, extra=()):
    rows = read_ranks(SAMPLE)
    hyps = read_hypotheses(SAMPLE) + list(extra)
    found = hypothesis_states(hyps, series(rows), zero_result_keys(rows), dt.date.fromisoformat(as_of))
    return {h["id"]: h for h in found}


class States(unittest.TestCase):
    def test_states(self):
        s = states()
        self.assertEqual([s[i]["state"] for i in ("H001", "H005", "H006", "H007")],
                         ["judged", "due", "open", "not-shipped"])
        self.assertEqual(s["H001"]["basket"], {"up": 2, "down": 0, "flat": 0, "unpaired": 0, "unmeasurable": 0})
        self.assertEqual(s["H005"]["basket"]["up"], 1)
        self.assertEqual(s["H005"]["basket"]["unpaired"], 1)
        self.assertEqual(s["H006"]["window"], 21)
        self.assertIsNone(s["H004"]["basket"])

    def test_age_is_counted_against_as_of(self):
        self.assertEqual((states()["H005"]["age_days"], states("2026-10-25")["H005"]["age_days"]), (25, 5))
        self.assertEqual(states("2026-10-25")["H005"]["state"], "open")

    def test_default_reader_takes_only_h_files(self):
        self.assertEqual(sorted(states()), ["H001", "H002", "H003", "H004", "H005", "H006", "H007"])
        both = [h["id"] for h in read_hypotheses(SAMPLE, kinds=("H", "C"))]
        self.assertIn("C001", both)

    def test_apostrophe_forms_join(self):
        # ranks.csv spells the key with U+2019; this hypothesis types the keyboard apostrophe
        typed = {"id": "H900", "markets": "ua", "queries": "п'ятниця море", "went_live": "2026-10-06",
                 "window_days": "21", "verdict": "", "primary_signal": "rank"}
        basket = states(extra=[typed])["H900"]["basket"]
        self.assertEqual((basket["up"], basket["unpaired"]), (1, 0))


class TwoSpellingsTrackedApart(unittest.TestCase):
    """The store ranks `a'b` and `a’b` as two queries, and a store may track both. A hypothesis that names one
    of them must be paired with that one, never with its neighbour."""

    def obs(self, date, position):
        return {"date": date, "position": position, "provider": "itunes-search-api", "depth": "200",
                "legacy": False, "status": "ok"}

    def pairs(self):
        return {("ua", "a'b"): [self.obs("2026-10-01", 40), self.obs("2026-10-20", 10)],        # improved
                ("ua", "a\u2019b"): [self.obs("2026-10-01", 5), self.obs("2026-10-20", 50)]}   # regressed

    def basket(self, query, pairs=None, empty=frozenset()):
        hyp = {"id": "H901", "markets": "ua", "queries": query, "went_live": "2026-10-02", "window_days": "14",
               "verdict": "", "primary_signal": "rank"}
        return hypothesis_states([hyp], self.pairs() if pairs is None else pairs, empty, dt.date(2026, 11, 14))[0]["basket"]

    def test_the_exact_spelling_wins(self):
        self.assertEqual((self.basket("a'b")["up"], self.basket("a'b")["down"]), (1, 0))
        self.assertEqual((self.basket("a\u2019b")["up"], self.basket("a\u2019b")["down"]), (0, 1))

    def test_a_loose_match_between_two_keys_names_neither(self):
        # typed with a doubled space: no exact key, and two tracked keys share its loose form
        spaced = {("ua", "a'b c"): self.pairs()[("ua", "a'b")], ("ua", "a\u2019b c"): self.pairs()[("ua", "a\u2019b")]}
        found = self.basket("a'b  c", pairs=spaced)
        self.assertEqual((found["up"], found["down"], found["unpaired"]), (0, 0, 1))

    def test_a_loose_match_with_one_key_is_that_key(self):
        only = {("ua", "a\u2019b"): self.pairs()[("ua", "a\u2019b")]}
        self.assertEqual(self.basket("a'b", pairs=only)["down"], 1)

    def test_an_unmeasurable_key_is_found_by_its_loose_form_too(self):
        self.assertEqual(self.basket("a'b", pairs={}, empty=frozenset({("ua", "a\u2019b")}))["unmeasurable"], 1)


class Priority(unittest.TestCase):
    def rows(self):
        ranks = read_ranks(SAMPLE)
        return priority(series(ranks), read_markets(SAMPLE), read_hypotheses(SAMPLE), read_brand_tokens(SAMPLE), None)

    def test_priority_order(self):
        top = self.rows()[0]
        self.assertEqual((top["market"], top["keyword"], top["score"]), ("us", "moon phase", 14.0))
        self.assertEqual(top["status"], "open hypothesis, not yet dominant")
        self.assertEqual((top["position"], top["band"], top["proceeds"]), (30, "top30", 25.0))

    def test_brand_and_dominant_keys_are_not_targets(self):
        keys = {(r["market"], r["keyword"]) for r in self.rows()}
        self.assertNotIn(("us", "tidepool"), keys)
        self.assertNotIn(("ua", "tidepool"), keys)


if __name__ == "__main__":
    unittest.main()
