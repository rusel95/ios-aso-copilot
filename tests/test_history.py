"""The whole history a source can give: from the app's first release, not from a date typed into the code."""
import contextlib
import datetime as dt
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import copy_store  # noqa: E402

import pull_revenuecat  # noqa: E402
from aso import pull_revenuecat_fetch as fetch  # noqa: E402
from aso.commands import cycle  # noqa: E402
from aso.store import read_csv  # noqa: E402


class WhereHistoryStarts(unittest.TestCase):
    def test_the_first_release_day_comes_from_the_public_lookup(self):
        lookup = {"results": [{"releaseDate": "2025-09-27T07:00:00Z", "currentVersionReleaseDate": "2026-11-01T10:00:00Z"}]}
        self.assertEqual(pull_revenuecat.first_release_day(lookup), "2025-09-27")
        for nothing in (None, {}, {"results": []}, {"results": [{"releaseDate": "soon"}]}):
            self.assertIsNone(pull_revenuecat.first_release_day(nothing))

    def test_a_pull_starts_there_and_a_year_back_when_the_lookup_is_silent(self):
        today = dt.date(2026, 11, 14)
        self.assertEqual(pull_revenuecat.history_start({"results": [{"releaseDate": "2025-09-27T07:00:00Z"}]}, today), "2025-09-27")
        self.assertEqual(pull_revenuecat.history_start(None, today), "2025-11-14")

    def test_no_date_is_typed_into_the_collector(self):
        source = Path(pull_revenuecat.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(source, r'(start_date|default)\s*(:\s*str\s*)?=\s*"20\d\d-\d\d-\d\d"')


class LongRanges(unittest.TestCase):
    """Apple Ads gives day-by-day results for ninety days a request, so a long history is asked in pieces."""

    def test_the_pieces_cover_the_range_once(self):
        pieces = fetch.day_chunks("2025-09-27", "2026-11-14", 90)
        self.assertEqual((pieces[0][0], pieces[-1][1]), ("2025-09-27", "2026-11-14"))
        for (start, end), (following, _) in zip(pieces, pieces[1:]):
            self.assertLessEqual((dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days, 89)
            self.assertEqual(dt.date.fromisoformat(following) - dt.date.fromisoformat(end), dt.timedelta(days=1))
        self.assertEqual(fetch.day_chunks("2026-11-14", "2026-11-14", 90), [("2026-11-14", "2026-11-14")])
        self.assertEqual(fetch.day_chunks("2026-11-15", "2026-11-14", 90), [])

    def test_the_daily_report_is_asked_piece_by_piece_and_joined(self):
        asked = []

        def answer(cmd, input_text=None):
            payload = json.loads(input_text or "{}")
            if "campaigns" in cmd and "find" in cmd:
                return {"result": [{"id": 7, "name": "us", "targeting": {"countryOrRegion": {"include": ["US"]}}}]}, None
            time = payload.get("timeRange", {})
            if time.get("granularity") != "DAILY":
                return {"result": {"rows": [{"metadata": {"id": 7, "countryOrRegion": "US"}, "totalMetrics": {}}]}}, None
            asked.append((time["start"], time["end"]))
            return {"result": {"rows": [{"metadata": {"id": 7}, "granularMetrics": [
                {"date": time["start"], "impressions": 10, "taps": 1, "tapInstalls": 1, "localSpend": {"amount": "0.50"}}]}]}}, None
        with mock.patch.object(fetch, "run_json_cmd", side_effect=answer):
            _, _, daily = fetch.fetch_apple_ads_spend("asc", "123", "", "2026-05-01", "2026-11-14")
        self.assertEqual(asked, fetch.day_chunks("2026-05-01", "2026-11-14", 90))
        self.assertEqual(len(asked), 3)
        self.assertEqual(sorted(day for day, _, _ in daily), [start for start, _ in asked])       # one row a piece, all kept


class DemandForEveryWeek(unittest.TestCase):
    """Apple answers for past weeks too: the radar asks for every week since the start that the store does not hold."""

    def store(self, tmp):
        store = Path(tmp) / "marketing"
        (store / "metrics").mkdir(parents=True)
        (store / "config.md").write_text("**App ID**: 1000000001\n**Apple Ads profile**: Test\n**Apple Ads account**: 42\n"
                                         "**Apple Ads genres**: WEATHER\n", encoding="utf-8")
        (store / "metrics" / "ranks.csv").write_text(
            "date,market,keyword,group,position,popularity,difficulty,source,depth,status\n"
            "2026-11-02,us,tide times,target,60,,,itunes-search-api,200,ok\n"
            "2026-11-02,ua,приплив,target,,,,itunes-search-api,200,beyond-depth\n", encoding="utf-8")
        return store

    def pull(self, store, since, today=dt.date(2026, 11, 14)):
        import argparse
        import radar
        asked = {"popularity": [], "share": []}

        def fake(cfg, resource, payload):
            time = payload["timeRange"]
            if resource[1] == "search-term-popularity":
                market = payload["filters"][0]["value"]
                asked["popularity"].append((time["start"], market))
                return {"result": {"rows": [{"week": time["start"], "countryOrRegion": market, "genre": "WEATHER",
                                             "searchTerm": "tide times" if market == "US" else "приплив", "rankInGenre": 9,
                                             "searchPopularity1to100": 40, "searchPopularity1to5": 2}]}}
            asked["share"].append((time["start"], time["end"]))
            return {"result": {"rows": []}}
        args = argparse.Namespace(store=str(store), markets=None, if_configured=False, since=since)
        with contextlib.redirect_stdout(io.StringIO()) as said:
            code = radar.cmd_pull(args, run=fake, today=today)
        return code, asked, said.getvalue()

    def test_every_week_since_the_start_is_asked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(tmp)
            code, asked, _ = self.pull(store, "2026-10-13")          # a Tuesday: its week began on Sunday 10-11
            self.assertEqual(code, 0)
            self.assertEqual(sorted({week for week, _ in asked["popularity"]}), ["2026-10-11", "2026-10-18", "2026-10-25", "2026-11-01"])
            self.assertEqual(len(asked["popularity"]), 8)                                   # four weeks, two storefronts
            held = {(r["week"], r["market"]) for r in read_csv(store / "metrics" / "popularity_cut.csv")}
            self.assertEqual(len(held), 8)
            _, again, said = self.pull(store, "2026-10-13")
            self.assertEqual(again["popularity"], [])                                        # nothing is asked twice
            self.assertIn("already stored", said)

    def test_impression_share_is_asked_for_the_whole_span_four_weeks_a_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, asked, _ = self.pull(self.store(tmp), "2026-09-13")                           # eight weeks back
            spans = sorted(asked["share"])
            self.assertEqual(spans, [("2026-09-13", "2026-10-10"), ("2026-10-11", "2026-11-07")])

    def test_without_a_start_only_the_newest_week_is_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, asked, _ = self.pull(self.store(tmp), None)
            self.assertEqual({week for week, _ in asked["popularity"]}, {"2026-11-01"})
            self.assertEqual(len(asked["share"]), 1)


class ThePassAsksForTheWholeSpan(unittest.TestCase):
    def test_the_demand_radar_is_told_where_the_apps_history_starts(self):
        seen = []
        lookup = {"results": [{"releaseDate": "2025-09-27T07:00:00Z"}]}
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(cycle, "fetch_lookup", return_value=lookup), \
                mock.patch.object(cycle, "run_cmd", side_effect=lambda cmd, **_: seen.append(cmd) or (0, "radar\n", "")):
            self.assertTrue(cycle.stage_radar(copy_store(tmp), "1000000001"))
        self.assertEqual(seen[0][-2:], ["--since", "2025-09-27"])

    def test_a_silent_lookup_asks_for_the_newest_week_only(self):
        seen = []
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), \
                mock.patch.object(cycle, "fetch_lookup", return_value=None), \
                mock.patch.object(cycle, "run_cmd", side_effect=lambda cmd, **_: seen.append(cmd) or (0, "radar\n", "")):
            cycle.stage_radar(copy_store(tmp), "1000000001")
        self.assertNotIn("--since", seen[0])


class EverythingTheSourcesGive(unittest.TestCase):
    def test_the_count_of_written_reviews_is_stored(self):
        from aso.store_state import ratings_rows
        ratings = {"averageRating": 4.5, "totalCount": 12, "byCountry": [{"country": "US", "ratingCount": 9, "averageRating": 4.4}]}
        listing = {"data": [{"attributes": {"body": "not kept"}}], "meta": {"paging": {"total": 7, "limit": 1}}}
        rows = ratings_rows(ratings, {"meta": {"paging": {"total": 2}}}, "2026-11-14", listing)
        self.assertEqual((rows[0]["market"], rows[0]["reviews"], rows[0]["reviews_unanswered"]), ("all", 7, 2))
        self.assertEqual(rows[1]["reviews"], "")                             # the listing's total is for all storefronts
        self.assertEqual(ratings_rows(ratings, None, "2026-11-14")[0]["reviews"], "")       # not read: blank, not zero
        self.assertNotIn("not kept", str(rows))

    def test_chart_positions_are_read_for_every_storefront_the_store_tracks_when_none_is_named(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "metrics" / "charts.csv").unlink()
            seen = []

            def chart(country, genre, **_):
                seen.append(country)
                return [{"app_id": "1000000001", "name": "Tidepool", "developer": "", "rank": 1}], ""
            with contextlib.redirect_stdout(io.StringIO()) as said, mock.patch.object(cycle, "fetch_category_chart", side_effect=chart), \
                    mock.patch.object(cycle, "store_weeks", return_value=[]):
                cycle.collect_extras(store, {"app_id": "1000000001", "brand": "tidepool"})
            self.assertEqual(sorted(set(seen)), ["ua", "us"])                 # the storefronts of ranks.csv
            self.assertIn("chart positions: charts.csv +", said.getvalue())
            self.assertEqual({r["market"] for r in read_csv(store / "metrics" / "charts.csv")}, {"ua", "us"})


class AdsWithoutASubscriptionProvider(unittest.TestCase):
    """A store with Apple Ads and no RevenueCat still gets its ads results by week."""
    APP = {"app_id": "1000000001", "brand": "tidepool", "rc_project_id": None}

    def run_stage(self, store, **app):
        with contextlib.redirect_stdout(io.StringIO()) as said:
            clean = cycle.stage_revenue(store, dict(self.APP, **app), False)
        return clean, said.getvalue()

    def test_ads_weeks_are_stored_when_only_apple_ads_is_set_up(self):
        rows = [{"week_start": "2026-11-02", "campaign_id": "7", "market": "us", "spend_usd": "3.50", "impressions": 70, "taps": 7,
                 "installs": 2, "source": "apple-ads", "captured": "2026-11-14"}]
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "metrics" / "ads.csv").unlink()
            with mock.patch.object(pull_revenuecat, "collect_ads", return_value=(rows, None)) as collect:
                clean, said = self.run_stage(store, ads_account="123", ads_profile="default")
            self.assertTrue(clean, said)
            self.assertEqual(collect.call_args.args[0], store)
            self.assertIn("ads.csv +1", said)
            self.assertEqual([r["campaign_id"] for r in read_csv(store / "metrics" / "ads.csv")], ["7"])

    def test_neither_set_up_reads_nothing(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(pull_revenuecat, "collect_ads", side_effect=AssertionError("must not run")):
            clean, said = self.run_stage(copy_store(tmp), ads_account=None)
        self.assertTrue(clean)
        self.assertIn("not set up", said)

    def test_a_failed_ads_read_is_said(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(pull_revenuecat, "collect_ads", return_value=(None, "exit 1: no profile")):
            clean, said = self.run_stage(copy_store(tmp), ads_account="123")
        self.assertFalse(clean)
        self.assertIn("⚠️", said)
        self.assertIn("no profile", said)


if __name__ == "__main__":
    unittest.main()
