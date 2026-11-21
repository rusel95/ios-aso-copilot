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
        # the command line too: a typed default there overrides the collector's own, and no pass reaches the first release
        for path in (Path(pull_revenuecat.__file__), Path(pull_revenuecat.__file__).with_name("copilot.py")):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r'(start_date|default)\s*(:\s*str\s*)?=\s*"20\d\d-\d\d-\d\d"', path.name)

    def test_a_pull_holds_whole_weeks_only_from_its_first_monday(self):
        today = dt.date(2026, 11, 14)
        released = {"results": [{"releaseDate": "2025-09-27T07:00:00Z"}]}               # a Saturday: nothing existed before it
        with mock.patch("aso.commands.collect.fetch_lookup", return_value=released):
            self.assertEqual(pull_revenuecat.pull_window({"app_id": "1"}, today), ("2025-09-27", None))
            # a start the caller names begins mid-week: the week it begins in is partial and is not written
            self.assertEqual(pull_revenuecat.pull_window({"app_id": "1"}, today, "2026-09-01"), ("2026-09-01", dt.date(2026, 9, 7)))
            self.assertEqual(pull_revenuecat.pull_window({"app_id": "1"}, today, "2026-09-07"), ("2026-09-07", dt.date(2026, 9, 7)))
        with mock.patch("aso.commands.collect.fetch_lookup", return_value=None):     # silent lookup: a year back is not a release
            self.assertEqual(pull_revenuecat.pull_window({"app_id": "1"}, today), ("2025-11-14", dt.date(2025, 11, 17)))


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

    def test_spend_of_a_campaign_in_several_storefronts_is_not_given_to_one_of_them(self):
        def answer(cmd, input_text=None):
            payload = json.loads(input_text or "{}")
            if "campaigns" in cmd and "find" in cmd:
                return {"result": [{"id": 7, "name": "both", "targeting": {"countryOrRegion": {"include": ["US", "CA"]}}},
                                   {"id": 8, "name": "one", "targeting": {"countryOrRegion": {"include": ["UA"]}}}]}, None
            if payload.get("timeRange", {}).get("granularity") != "DAILY":
                return {"result": {"rows": [{"metadata": {"id": 7, "countryOrRegion": country}, "totalMetrics": {}} for country in ("US", "CA")]
                                   + [{"metadata": {"id": 8, "countryOrRegion": "UA"}, "totalMetrics": {}}]}}, None
            day = {"date": "2026-11-02", "impressions": 10, "taps": 1, "localSpend": {"amount": "1.00"}}
            return {"result": {"rows": [{"metadata": {"id": 7}, "granularMetrics": [day]},
                                        {"metadata": {"id": 8}, "granularMetrics": [day]}]}}, None
        with mock.patch.object(fetch, "run_json_cmd", side_effect=answer):
            _, _, daily = fetch.fetch_apple_ads_spend("asc", "123", "", "2026-11-01", "2026-11-14")
        self.assertEqual(sorted(daily), [("2026-11-02", 7, "??"), ("2026-11-02", 8, "UA")])


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

    def test_an_old_week_Apple_has_nothing_for_is_asked_once_and_a_late_week_is_asked_again(self):
        import argparse
        import radar
        asked = []

        def nothing(cfg, resource, payload):
            if resource[1] == "search-term-popularity":
                asked.append(payload["timeRange"]["start"])
            return {"result": {"rows": []}}
        with tempfile.TemporaryDirectory() as tmp:
            store = self.store(tmp)
            args = argparse.Namespace(store=str(store), markets=None, if_configured=False, since="2026-10-13")
            passes = []
            for _ in range(2):
                asked.clear()
                with contextlib.redirect_stdout(io.StringIO()):
                    radar.cmd_pull(args, run=nothing, today=dt.date(2026, 11, 14))
                passes.append(set(asked))
            kept = {r["week"] for r in read_csv(store / "metrics" / "popularity_cut.csv")}
        self.assertEqual(kept, {"2026-10-11", "2026-10-18"})            # the two oldest weeks: Apple has published, and has none
        self.assertEqual(passes[1], {"2026-10-25", "2026-11-01"})      # the two newest may only be late: asked again

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

    def home_store(self, tmp, config="**App ID**: 1000000001\n"):
        """A store whose basket is widest in the US and whose downloads come from UA."""
        store = Path(tmp)
        (store / "metrics").mkdir()
        (store / "config.md").write_text(config, encoding="utf-8")
        (store / "metrics" / "ranks.csv").write_text(
            "date,market,keyword,group,position,popularity,difficulty,source,depth,status\n"
            "2026-11-02,ua,a,target,3,,,itunes-search-api,200,ok\n"
            "2026-11-02,us,a,target,3,,,itunes-search-api,200,ok\n2026-11-02,us,b,target,9,,,itunes-search-api,200,ok\n", encoding="utf-8")
        (store / "metrics" / "weekly.csv").write_text(
            "week_start,segment,impressions,product_page_views,downloads,cvr_pct,trial_starts,source,recorded,note\n"
            "2026-11-02,all,563,65,33,,,s,2026-11-10,\n2026-11-02,ua,459,60,31,,,s,2026-11-10,\n"
            "2026-11-02,us,104,5,2,,,s,2026-11-10,\n2026-11-02,us,104,5,50,,,s,2026-11-03,\n"           # an older reading of the same week
            "2026-11-02,search,300,40,20,,,s,2026-11-10,\n"
            # a second week the other way round: by the newest week alone US would win (40 v 20); over both weeks UA does (51 v 42)
            "2026-11-09,ua,200,20,20,,,s,2026-11-16,\n2026-11-09,us,300,30,40,,,s,2026-11-16,\n", encoding="utf-8")
        return store

    def test_the_home_storefront_is_where_the_downloads_come_from_not_where_the_basket_is_widest(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = self.home_store(tmp)
            self.assertEqual(cycle.home_storefront(store, {}), "ua")                         # not "us", which has more keys
            self.assertEqual(cycle.home_storefront(store, {"Charts storefronts": "DE, fr"}), "de")      # config.md decides
            (store / "metrics" / "weekly.csv").unlink()
            self.assertEqual(cycle.home_storefront(store, {}), "us")                         # no funnel: where the keys are
            (store / "metrics" / "ranks.csv").unlink()
            self.assertIsNone(cycle.home_storefront(store, {}))

    def test_the_status_chart_follows_the_home_storefront_and_names_what_it_cannot_do(self):
        from aso.commands import status
        app = {"app_id": "1000000001", "brand": "tidepool", "ads_genres": []}
        chart = [{"app_id": "7", "name": "Other", "developer": "d", "rank": 99}]
        with tempfile.TemporaryDirectory() as tmp:
            store = self.home_store(tmp)
            with contextlib.redirect_stdout(io.StringIO()) as said, mock.patch.object(status, "fetch_category_chart", return_value=(chart, "")) as fetched:
                status.chart_line(store, app)
            self.assertEqual(fetched.call_args.args[:2], ("ua", 6002))
            self.assertIn("Not in Top Free Utilities [UA]", said.getvalue())
            (store / "config.md").write_text("**App ID**: 1000000001\n**Charts genres**: nonsense\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as said, mock.patch.object(status, "fetch_category_chart") as fetched:
                status.chart_line(store, app)                                                   # no IndexError, no query
            fetched.assert_not_called()
            self.assertIn("name no genre this skill knows", said.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "config.md").write_text("**App ID**: 1000000001\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as said:
                status.chart_line(Path(tmp), app)
            self.assertIn("not set up", said.getvalue())

    def test_the_charts_are_read_first_where_the_store_tracks_most_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            (store / "metrics").mkdir()
            (store / "metrics" / "ranks.csv").write_text(
                "date,market,keyword,group,position,popularity,difficulty,source,depth,status\n"
                "2026-11-02,ua,a,target,3,,,itunes-search-api,200,ok\n"
                "2026-11-02,us,a,target,3,,,itunes-search-api,200,ok\n2026-11-02,us,b,target,9,,,itunes-search-api,200,ok\n"
                "2026-11-09,us,a,target,3,,,itunes-search-api,200,ok\n", encoding="utf-8")
            self.assertEqual(cycle.chart_storefronts(store, {}), ["us", "ua"])
            self.assertEqual(cycle.chart_storefronts(store, {"Charts storefronts": "DE, fr"}), ["de", "fr"])   # config.md decides

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


class OnlyThisAppsAds(unittest.TestCase):
    """One Apple Ads account can advertise several apps. A store gets the results of its own app and no other's."""

    def answer(self, asked):
        def reply(cmd, input_text=None):
            payload = json.loads(input_text or "{}")
            if "find" in cmd:
                return {"result": [{"id": 7, "name": "ours", "promotedObjectId": 1000000001, "targeting": {"countryOrRegion": {"include": ["US"]}}},
                                   {"id": 8, "name": "the other app", "promotedObjectId": 2000000002,
                                    "targeting": {"countryOrRegion": {"include": ["US"]}}}]}, None
            asked.append(payload.get("filters"))
            return {"result": {"rows": []}}, None
        return reply

    def test_campaigns_of_another_app_are_left_out_and_reports_are_asked_for_this_app(self):
        asked = []
        with mock.patch.object(fetch, "run_json_cmd", side_effect=self.answer(asked)):
            campaigns, _, _ = fetch.fetch_apple_ads_spend("asc", "123", "", "2026-11-01", "2026-11-14", app_id="1000000001")
        self.assertEqual(sorted(campaigns), [7])
        self.assertTrue(asked)
        for filters in asked:
            self.assertIn({"field": "promotedObjectId", "operator": "IN", "value": ["1000000001"]}, filters)

    def test_an_app_that_ran_no_ads_has_nothing_to_store_and_that_is_not_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "config.md").open("a", encoding="utf-8") as fh:
                fh.write("**Apple Ads account**: 123\n**Apple Ads profile**: Test\n")
            with mock.patch.object(pull_revenuecat, "fetch_apple_ads_spend", return_value=({}, [], {})) as called, \
                    mock.patch.object(pull_revenuecat, "find_bin", return_value="asc"):
                rows, err = pull_revenuecat.collect_ads(store, start_date="2026-11-01", end_date="2026-11-14")
            self.assertEqual((rows, err), ([], None))
            self.assertEqual(called.call_args.kwargs.get("app_id"), "1000000001")


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



class WhoseChartPositionItIs(unittest.TestCase):
    """A chart position belongs to the app with this App ID. Another app whose name holds the brand word is another app."""

    def chart(self):
        return [{"rank": 1, "app_id": "111", "name": "Tidepool Pro Widgets", "developer": "Someone Else"},
                {"rank": 2, "app_id": "222", "name": "Weather", "developer": "Third"},
                {"rank": 3, "app_id": "1000000001", "name": "Tidepool", "developer": "Us"}]

    def test_the_app_id_decides_even_when_a_namesake_ranks_higher(self):
        from aso.commands.charts import find_app_in_chart
        self.assertEqual(find_app_in_chart(self.chart(), "1000000001", "tidepool")["rank"], 3)

    def test_a_namesake_alone_is_not_the_app(self):
        from aso.commands.charts import find_app_in_chart, read_charts
        others = self.chart()[:2]
        self.assertIsNone(find_app_in_chart(others, "1000000001", "tidepool"))
        result = read_charts({"app_id": "1000000001", "brand": "tidepool"}, ["us"], [6001], fetch=lambda *a, **k: (others, ""))[0]
        self.assertEqual((result["found"], result["rank"]), (False, None))

    def test_without_an_app_id_the_name_is_all_there_is(self):
        from aso.commands.charts import find_app_in_chart
        self.assertEqual(find_app_in_chart(self.chart(), "", "tidepool")["rank"], 1)

if __name__ == "__main__":
    unittest.main()
