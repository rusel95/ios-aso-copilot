"""Ratings, chart positions and releases as stored series, and what the export and the page make of them."""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import copy_store  # noqa: E402

from aso import store_state  # noqa: E402
from aso.dashboard import contract, export  # noqa: E402
from aso.store import read_csv  # noqa: E402

AS_OF = dt.date(2026, 11, 14)
RATINGS = {"averageRating": 4.75, "totalCount": 12, "countryCount": 2, "histogram": {"5": 10, "4": 1, "3": 1},
           "byCountry": [{"country": "US", "ratingCount": 9, "averageRating": 4.67},
                         {"country": "UA", "ratingCount": 3, "averageRating": 5.0}]}
UNANSWERED = {"data": [{}, {}], "meta": {"paging": {"total": 2}}}
CHARTS = [{"country": "US", "genre": "Weather", "chart_type": "top-free", "chart_size": 100, "found": True, "rank": 87},
          {"country": "UA", "genre": "Weather", "chart_type": "top-free", "chart_size": 100, "found": False, "rank": None},
          {"country": "DE", "genre": "Weather", "chart_type": "top-free", "error": "timeout", "found": False, "rank": None}]
LOOKUP = {"resultCount": 1, "results": [{"version": "1.0.1", "currentVersionReleaseDate": "2026-11-09T08:12:00Z"}]}


class Rows(unittest.TestCase):
    def test_ratings_rows_one_for_all_and_one_per_storefront(self):
        rows = store_state.ratings_rows(RATINGS, UNANSWERED, "2026-11-10")
        self.assertEqual([(r["market"], r["ratings_count"], r["rating_average"], r["reviews_unanswered"]) for r in rows],
                         [("all", 12, 4.75, 2), ("ua", 3, 5.0, ""), ("us", 9, 4.67, "")])
        self.assertEqual(set(rows[0]), set(store_state.RATINGS_COLS))

    def test_ratings_without_the_unanswered_read_leave_that_cell_blank(self):
        self.assertEqual(store_state.ratings_rows(RATINGS, None, "2026-11-10")[0]["reviews_unanswered"], "")
        self.assertEqual(store_state.ratings_rows({"unexpected": True}, None, "2026-11-10"), [])

    def test_a_chart_miss_is_a_row_that_says_so(self):
        rows = store_state.chart_rows(CHARTS, "2026-11-10")
        self.assertEqual([(r["market"], r["position"], r["depth"], r["status"]) for r in rows],
                         [("us", 87, 100, "ok"), ("ua", "", 100, "beyond-depth"), ("de", "", "", "error")])
        self.assertEqual((rows[0]["genre"], rows[0]["chart_type"], rows[0]["source"]), ("Weather", "top-free", "itunes-rss"))

    def test_the_live_release_is_dated_by_the_store_itself(self):
        row = store_state.release_row(LOOKUP, "2026-11-10")
        self.assertEqual((row["version"], row["state"], row["state_date"], row["source"]),
                         ("1.0.1", "live", "2026-11-09", "itunes-lookup"))
        self.assertIsNone(store_state.release_row({"resultCount": 0, "results": []}, "2026-11-10"))


class Storing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = copy_store(self.tmp.name)
        for name in ("ratings.csv", "charts.csv", "releases.csv"):
            (self.store / "metrics" / name).unlink(missing_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_version_already_stored_as_live_adds_no_row(self):
        self.assertEqual(store_state.store_release(self.store, LOOKUP, "2026-11-10"), 1)
        self.assertEqual(store_state.store_release(self.store, LOOKUP, "2026-11-17"), 0)
        self.assertEqual(len(read_csv(self.store / "metrics" / "releases.csv")), 1)

    def test_a_second_read_on_the_same_day_adds_nothing_unless_it_differs(self):
        text = json.dumps(RATINGS)
        self.assertEqual(store_state.store_ratings(self.store, text, json.dumps(UNANSWERED), "2026-11-10"), 3)
        self.assertEqual(store_state.store_ratings(self.store, text, json.dumps(UNANSWERED), "2026-11-10"), 0)
        self.assertEqual(store_state.store_ratings(self.store, "not json", None, "2026-11-10"), 0)

    def families(self, day="2026-11-10"):
        return export.build_all(self.store, AS_OF)[0][f"snapshot/{day}.json"]["families"]

    def test_ratings_family_carries_the_storefronts(self):
        store_state.store_ratings(self.store, json.dumps(RATINGS), json.dumps(UNANSWERED), "2026-11-10")
        ratings = self.families()["ratings"]
        self.assertEqual((ratings["source"], ratings["fetched_at"]), ("itunes-ratings", "2026-11-10"))
        self.assertEqual(ratings["figures"]["ratings_count"], {"value": 12, "by_market": {"ua": 3, "us": 9}})
        self.assertEqual(ratings["figures"]["rating_average"], {"value": 4.75, "by_market": {"ua": 5.0, "us": 4.67}})
        self.assertEqual(ratings["figures"]["reviews_unanswered"], {"value": 2})
        self.assertEqual(ratings["figures"]["reviews"]["unavailable"]["code"], "no_data")

    def test_charts_family_is_rows(self):
        store_state.store_charts(self.store, CHARTS, "2026-11-10")
        self.assertEqual(self.families()["charts"]["rows"], [
            {"market": "de", "genre": "Weather", "chart_type": "top-free", "position": None, "status": "error"},
            {"market": "ua", "genre": "Weather", "chart_type": "top-free", "position": None, "status": "beyond-depth"},
            {"market": "us", "genre": "Weather", "chart_type": "top-free", "position": 87, "status": "ok"}])

    def test_events_list_the_live_releases(self):
        store_state.store_release(self.store, LOOKUP, "2026-11-10")
        self.assertEqual(export.events(self.store, AS_OF)["releases"], [{"version": "1.0.1", "date": "2026-11-09"}])
        self.assertEqual(export.events(self.store, dt.date(2026, 11, 8))["releases"], [])          # not live yet on that day

    def test_every_file_stays_valid(self):
        store_state.store_ratings(self.store, json.dumps(RATINGS), json.dumps(UNANSWERED), "2026-11-10")
        store_state.store_charts(self.store, CHARTS, "2026-11-10")
        store_state.store_release(self.store, LOOKUP, "2026-11-10")
        catalog = contract.load_catalog()
        for path, obj in export.build_all(self.store, AS_OF)[0].items():
            with self.subTest(path=path):
                self.assertEqual(contract.validate(path, contract.canonical(obj), catalog), [])


if __name__ == "__main__":
    unittest.main()
