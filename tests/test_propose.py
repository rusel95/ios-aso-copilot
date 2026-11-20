"""Proposals: where the next rank hypothesis can start, generated from the store by money at stake."""
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import SAMPLE, copy_store, run  # noqa: E402

from aso.ledger_state import proposals  # noqa: E402


def row(market, keyword, score, status="UNCLAIMED", position=40):
    return {"score": score, "market": market, "keyword": keyword, "position": position, "band": "top100", "proceeds": 20.0,
            "gain": 0.5, "reach": 0.5, "status": status, "demand": None}


def state(hid, market, what):
    return {"id": hid, "markets": [market], "state": what}


class Proposals(unittest.TestCase):
    ROWS = [row("us", "a", 9.0), row("de", "x", 8.0), row("us", "b", 7.0), row("ua", "k", 6.0), row("us", "c", 5.0),
            row("us", "d", 4.0), row("us", "e", 3.0), row("ua", "l", 2.0), row("pl", "p", 1.0)]
    STATES = [state("H010", "de", "open"), state("H011", "pl", "due"), state("H012", "ua", "not-shipped"), state("H001", "us", "judged")]

    def test_one_proposal_a_storefront_with_nothing_in_flight_best_first(self):
        found = proposals(self.ROWS, self.STATES, basket=4, limit=5)
        self.assertEqual([p["market"] for p in found], ["us", "ua"])              # de and pl have a window in flight
        self.assertEqual([k["keyword"] for k in found[0]["keys"]], ["a", "b", "c", "d"])   # the basket is capped
        self.assertEqual((found[0]["score"], found[0]["proceeds"], found[0]["drafted"]), (9.0, 20.0, []))
        self.assertEqual(found[1]["keys"][0], {"keyword": "k", "position": 40, "band": "top100", "score": 6.0, "demand": None})

    def test_a_storefront_with_a_draft_that_never_shipped_names_it(self):
        self.assertEqual(proposals(self.ROWS, self.STATES, basket=4, limit=5)[1]["drafted"], ["H012"])

    def test_keys_apple_lists_demand_for_go_into_the_basket_first(self):
        """A target needs shown demand: a key Apple lists (`head N`) is taken before one below the storefront's cut."""
        rows = [row("us", "a", 9.0), row("us", "b", 7.0), row("us", "c", 5.0), row("us", "d", 4.0)]
        rows[0]["demand"], rows[2]["demand"], rows[3]["demand"] = "below 40", "head 62", "head 45"
        found = proposals(rows, [], basket=3, limit=5)[0]
        self.assertEqual([k["keyword"] for k in found["keys"]], ["c", "d", "a"])
        self.assertEqual(found["score"], 9.0)                                      # the storefront's place is unchanged

    def test_the_limit_counts_storefronts(self):
        self.assertEqual([p["market"] for p in proposals(self.ROWS, self.STATES, basket=4, limit=1)], ["us"])
        self.assertEqual(proposals([], self.STATES, basket=4, limit=5), [])


class ProposeCommand(unittest.TestCase):
    def test_what_is_due_comes_first_and_a_busy_store_gets_no_proposal(self):
        code, out, err = run("copilot.py", "propose", "--store", str(SAMPLE), "--as-of", "2026-11-14")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.splitlines()[0], "as of 2026-11-14")
        self.assertIn("2 hypotheses are due", out)                     # judged before anything new is proposed
        self.assertIn("Nothing to propose", out)                       # us and ua both have a window in flight

    def test_a_storefront_freed_by_a_verdict_is_proposed_with_its_draft_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            path = store / "hypotheses" / "H005-ua-tide-phrases.md"
            text = path.read_text(encoding="utf-8")
            self.assertIn("verdict:", text)
            path.write_text(re.sub(r"(?m)^verdict:.*$", "verdict: inconclusive", text, count=1), encoding="utf-8")
            code, out, _ = run("copilot.py", "propose", "--store", str(store), "--as-of", "2026-11-14")
            self.assertEqual(code, 0)
            self.assertRegex(out, r"(?m)^1\. ua ")
            self.assertRegex(out, r'ledger\.py --store \S+ draft --market ua --queries "[^"]+"')
            self.assertNotIn("tidepool", out.lower().split("1. ua", 1)[1])     # a brand key is never a target


if __name__ == "__main__":
    unittest.main()
