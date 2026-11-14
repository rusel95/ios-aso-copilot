"""The three entity files: hypotheses, tracked keys, dated events."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import SAMPLE, copy_store  # noqa: E402

from aso import store as store_module  # noqa: E402
from aso.dashboard import contract, export  # noqa: E402

DAY = date(2026, 11, 14)


class Hypotheses(unittest.TestCase):
    def by_id(self, as_of=DAY):
        return {x["id"]: x for x in export.hypotheses(SAMPLE, as_of)["hypotheses"]}

    def test_hypotheses(self):
        h = self.by_id()
        self.assertEqual(sorted(h), ["C001", "H001", "H002", "H003", "H004", "H005", "H006", "H007"])
        self.assertEqual((h["H005"]["state"], h["H005"]["window_end"], h["H005"]["days_past_window"]),
                         ("due", "2026-11-03", 11))
        self.assertEqual(h["H005"]["reads_in_window"], 1)
        self.assertEqual(h["C001"]["kind"], "C")

    def test_what_a_card_shows(self):
        h = self.by_id()["H005"]
        self.assertEqual((h["title"], h["markets"], h["queries"]),
                         ("ua tide phrases", ["ua"], ["приплив", "графік припливів"]))
        self.assertEqual((h["signal"], h["went_live"], h["window_days"], h["status"], h["verdict"]),
                         ("rank", "2026-10-20", 14, "live", None))
        self.assertEqual(h["basket"], {"up": 1, "down": 0, "flat": 0, "unpaired": 1, "unmeasurable": 0})
        self.assertEqual(h["confounds"], [])
        self.assertEqual(h["basket_keys"], [["ua", "графік припливів"], ["ua", "приплив"]])
        self.assertTrue(h["prediction"] and h["kill_criterion"])

    def test_a_channel_hypothesis_has_a_state_and_no_basket(self):
        c = self.by_id()["C001"]
        self.assertEqual((c["state"], c["signal"], c["basket"], c["reads_in_window"]), ("due", "channel", None, None))
        self.assertEqual((c["window_end"], c["days_past_window"]), ("2026-11-08", 6))
        self.assertEqual(c["basket_keys"], [])

    def test_states_that_are_not_due_have_no_days_past(self):
        h = self.by_id()
        self.assertEqual([h[i]["days_past_window"] for i in ("H001", "H006", "H007")], [None, None, None])
        self.assertEqual((h["H007"]["went_live"], h["H007"]["window_end"], h["H007"]["age_days"]), (None, None, None))
        self.assertEqual(h["H001"]["verdict"], "worked")

    def test_due_is_counted_against_as_of(self):
        self.assertEqual(self.by_id(date(2026, 11, 5))["H005"]["days_past_window"], 2)
        self.assertEqual(self.by_id(date(2026, 11, 1))["H005"]["state"], "open")
        self.assertEqual(self.by_id(date(2026, 11, 1))["H005"]["reads_in_window"], 0)   # the 11-02 sweep is ahead

    def test_confounds_written_as_a_list_come_out_as_a_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            path = store / "hypotheses" / "H005-ua-tide-phrases.md"
            text = path.read_text(encoding="utf-8").replace(
                "confounds: []", 'confounds:\n  - "A release landed in the window."\n  - Ads ran in ua to 2026-10-24.')
            path.write_text(text, encoding="utf-8")
            found = {x["id"]: x for x in export.hypotheses(store, DAY)["hypotheses"]}["H005"]["confounds"]
        self.assertEqual(found, ["A release landed in the window.", "Ads ran in ua to 2026-10-24."])

    def test_the_file_is_valid(self):
        text = contract.canonical(export.hypotheses(SAMPLE, DAY))
        self.assertEqual(contract.validate("hypotheses.json", text, contract.load_catalog()), [])


class Keys(unittest.TestCase):
    def test_keys(self):
        k = export.keys(SAMPLE, DAY)
        self.assertEqual(k["dates"], ["2026-10-05", "2026-10-19", "2026-11-02", "2026-11-09"])
        row = next(x for x in k["keys"] if x["keyword"] == "sea level")
        self.assertEqual(row["positions"], ["e", 180, "b", None])
        self.assertTrue(next(x for x in k["keys"] if x["market"] == "us" and x["keyword"] == "tidepool")["brand"])

    def find(self, market, keyword, as_of=DAY):
        return next(x for x in export.keys(SAMPLE, as_of)["keys"] if (x["market"], x["keyword"]) == (market, keyword))

    def test_every_tracked_key_is_there_once(self):
        keys = export.keys(SAMPLE, DAY)["keys"]
        self.assertEqual(len(keys), 12)
        self.assertEqual(len({(x["market"], x["keyword"]) for x in keys}), 12)
        self.assertEqual(self.find("ua", "фаза місяця")["positions"], ["z", "z", "z", None])

    def test_movement_comes_from_the_ledger(self):
        self.assertEqual(self.find("us", "tide times")["movement"],
                         {"first_date": "2026-10-05", "first": 120, "last_date": "2026-11-02", "last": 60,
                          "delta": 60, "label": "improved"})
        entered = self.find("us", "surf forecast")["movement"]
        self.assertEqual((entered["delta"], entered["label"][:7]), (None, "ENTERED"))
        self.assertIsNone(self.find("ua", "фаза місяця")["movement"])       # never answered: nothing to compare

    def test_priority_is_the_ledgers_row(self):
        p = self.find("us", "moon phase")["priority"]
        self.assertEqual((p["score"], p["band"], p["proceeds"], p["status"], p["demand"]),
                         (14.0, "top30", 25.0, "open hypothesis, not yet dominant", "below 38"))
        self.assertEqual(self.find("us", "tide times")["priority"]["demand"], "head 41")
        self.assertIsNone(self.find("us", "tidepool")["priority"])           # a brand key is not a target

    def test_as_of_hides_later_sweeps(self):
        self.assertEqual(export.keys(SAMPLE, date(2026, 10, 20))["dates"], ["2026-10-05", "2026-10-19"])
        self.assertEqual(self.find("us", "tide times", date(2026, 10, 20))["movement"]["last"], 95)

    def test_as_of_hides_later_demand(self):
        # popularity was captured 2026-11-03; a day before that the store had no demand to show
        self.assertIsNone(self.find("us", "tide times", date(2026, 11, 2))["priority"]["demand"])

    def test_the_file_is_valid(self):
        text = contract.canonical(export.keys(SAMPLE, DAY))
        self.assertEqual(contract.validate("keys.json", text, contract.load_catalog()), [])


class Events(unittest.TestCase):
    def test_queue_from_headings(self):
        events = export.events(SAMPLE, DAY)
        self.assertEqual(events["queue"][0],
                         {"id": "Q001", "date": "2026-10-30", "title": "needs a go — create the us penny flight"})
        self.assertEqual([q["id"] for q in events["queue"]], ["Q001", "Q002"])
        self.assertEqual(events["releases"], [])

    def test_as_of_hides_later_entries(self):
        self.assertEqual([q["id"] for q in export.events(SAMPLE, date(2026, 11, 5))["queue"]], ["Q001"])

    def test_a_heading_that_cannot_be_read_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "queue.md").open("a", encoding="utf-8") as fh:
                fh.write("\n### Q003 something without a date\n")
            store_module.PROBLEMS.clear()
            events = export.events(store, DAY)
            self.assertEqual([q["id"] for q in events["queue"]], ["Q001", "Q002"])
            self.assertTrue(any("queue.md" in where and "Q003" in why for where, why in store_module.PROBLEMS))
            store_module.PROBLEMS.clear()

    def test_the_file_is_valid(self):
        text = contract.canonical(export.events(SAMPLE, DAY))
        self.assertEqual(contract.validate("events.json", text, contract.load_catalog()), [])


class EntityShapes(unittest.TestCase):
    def test_a_broken_entity_file_fails(self):
        catalog = contract.load_catalog()
        keys = export.keys(SAMPLE, DAY)
        keys["keys"][0]["positions"] = keys["keys"][0]["positions"][:-1]      # no longer aligned with dates
        self.assertTrue(contract.validate("keys.json", contract.canonical(keys), catalog))
        hyps = export.hypotheses(SAMPLE, DAY)
        hyps["hypotheses"][0]["state"] = "pending"
        self.assertTrue(contract.validate("hypotheses.json", contract.canonical(hyps), catalog))
        events = export.events(SAMPLE, DAY)
        events["queue"][0].pop("date")
        self.assertTrue(contract.validate("events.json", contract.canonical(events), catalog))


if __name__ == "__main__":
    unittest.main()
