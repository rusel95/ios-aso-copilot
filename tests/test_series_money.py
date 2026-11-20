"""Revenue, weekly cashflow and Apple Ads as stored series: folding what the collector fetched into rows, appending
them without rewriting, and the families the export builds from them."""
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import copy_store  # noqa: E402

from aso.dashboard import contract, export  # noqa: E402
from aso.pull_revenuecat_series import (ADS_COLS, ADS_KEEP, CASHFLOW_COLS, REVENUE_COLS, ads_weeks, append_changed,  # noqa: E402
                                        cashflow_weeks, revenue_row)
from aso.store import append_csv, read_csv  # noqa: E402

AS_OF = dt.date(2026, 11, 14)
# two closed weeks (Mon 2026-10-26, Mon 2026-11-02) and one still open on the as-of day (Mon 2026-11-09)
REVENUE = {
    ("2026-10-27", "US", "United States"): {"gross": 10.0, "net_tax": 9.0, "proceeds": 7.0, "tx": 1},
    ("2026-10-30", "US", "United States"): {"gross": 20.0, "net_tax": 18.0, "proceeds": 14.0, "tx": 2},
    ("2026-11-03", "US", "United States"): {"gross": 40.0, "net_tax": 36.0, "proceeds": 28.0, "tx": 4},
    ("2026-11-04", "UA", "Ukraine"): {"gross": 6.0, "net_tax": 5.0, "proceeds": 4.2, "tx": 2},
    ("2026-11-10", "US", "United States"): {"gross": 99.0, "net_tax": 90.0, "proceeds": 70.0, "tx": 9},
}
TRIALS = {("2026-11-02", "US", "United States"): 3, ("2026-11-08", "US", "United States"): 1, ("2026-11-05", "UA", "Ukraine"): 1,
          ("2026-11-11", "UA", "Ukraine"): 5}
SPEND = {
    ("2026-11-02", 9001, "US"): {"spend": 2.5, "impressions": 100, "taps": 10, "installs": 4},
    ("2026-11-06", 9001, "US"): {"spend": 3.5, "impressions": 200, "taps": 20, "installs": 6},
    ("2026-11-07", 9002, "UA"): {"spend": 2.0, "impressions": 100, "taps": 8, "installs": 0},
    ("2026-11-12", 9001, "US"): {"spend": 9.0, "impressions": 900, "taps": 90, "installs": 30},
}


class Folding(unittest.TestCase):
    def test_cashflow_is_folded_into_closed_monday_weeks_per_storefront(self):
        rows = cashflow_weeks(REVENUE, TRIALS, SPEND, AS_OF, "2026-11-14")
        self.assertEqual([(r["week_start"], r["country"]) for r in rows],
                         [("2026-10-26", "US"), ("2026-11-02", "UA"), ("2026-11-02", "US")])
        us = rows[2]
        self.assertEqual((us["transactions"], us["new_trials"], us["gross_revenue_usd"], us["proceeds_usd"], us["ad_spend_usd"]),
                         (4, 4, "40.00", "28.00", "6.00"))
        self.assertEqual((rows[1]["proceeds_usd"], rows[1]["ad_spend_usd"], rows[1]["new_trials"]), ("4.20", "2.00", 1))
        self.assertEqual(set(rows[0]), set(CASHFLOW_COLS))
        self.assertTrue(all(r["captured"] == "2026-11-14" for r in rows))

    def test_the_open_week_is_not_written(self):
        weeks = {r["week_start"] for r in cashflow_weeks(REVENUE, TRIALS, SPEND, AS_OF, "2026-11-14")}
        self.assertNotIn("2026-11-09", weeks)
        self.assertIn("2026-11-09", {r["week_start"] for r in cashflow_weeks(REVENUE, TRIALS, SPEND, dt.date(2026, 11, 16), "x")})

    def test_a_week_that_began_before_the_pull_is_not_written(self):
        # a pull that began on Wed 2026-10-28 holds only the end of the week of Mon 2026-10-26
        whole_from = dt.date(2026, 11, 2)
        rows = cashflow_weeks(REVENUE, TRIALS, SPEND, AS_OF, "2026-11-14", whole_from)
        self.assertEqual({r["week_start"] for r in rows}, {"2026-11-02"})
        spend = {("2026-10-28", 9001, "US"): {"spend": 1.0, "impressions": 1, "taps": 1, "installs": 1}, **SPEND}
        self.assertEqual({r["week_start"] for r in ads_weeks(spend, AS_OF, "2026-11-14", whole_from)}, {"2026-11-02"})
        self.assertIn("2026-10-26", {r["week_start"] for r in ads_weeks(spend, AS_OF, "2026-11-14")})     # no bound: every closed week

    def test_ads_are_folded_per_closed_week_and_campaign(self):
        rows = ads_weeks(SPEND, AS_OF, "2026-11-14")
        self.assertEqual([(r["week_start"], r["campaign_id"], r["market"]) for r in rows],
                         [("2026-11-02", "9001", "us"), ("2026-11-02", "9002", "ua")])
        self.assertEqual((rows[0]["spend_usd"], rows[0]["impressions"], rows[0]["taps"], rows[0]["installs"]), ("6.00", 300, 30, 10))
        self.assertEqual(set(rows[0]), set(ADS_COLS))

    def test_a_report_with_no_install_count_leaves_the_cell_blank(self):
        spend = {("2026-11-02", 9001, "US"): {"spend": 2.5, "impressions": 100, "taps": 10}}
        self.assertEqual(ads_weeks(spend, AS_OF, "2026-11-14")[0]["installs"], "")

    def test_revenue_row_takes_the_overview(self):
        data = {"period": {"end": "2026-11-10"}, "overview": {
            "active_subscriptions": {"value": 4}, "active_trials": {"value": 1}, "mrr": {"value": 16.0},
            "revenue": {"value": 52.0}, "new_customers": {"value": 41}}}
        row = revenue_row(data)
        self.assertEqual(set(row), set(REVENUE_COLS))
        self.assertEqual((row["captured"], row["active_subscriptions"], row["mrr_usd"], row["active_users_28d"], row["source"]),
                         ("2026-11-10", 4, 16.0, "", "revenuecat"))

    def test_the_overview_is_dated_by_the_day_it_was_read_not_by_the_span_asked_for(self):
        data = {"captured_at": "2026-11-14T08:00:00Z", "period": {"start": "2025-09-27", "end": "2026-09-30"},
                "overview": {"mrr": {"value": 16.0}}}
        self.assertEqual(revenue_row(data)["captured"], "2026-11-14")


class DailyReport(unittest.TestCase):
    """The Apple Ads daily report as the collector reads it, with and without an install count."""

    REPORT = {"result": {"rows": [{"metadata": {"id": 9001}, "granularMetrics": [
        {"date": "2026-11-02", "impressions": 100, "taps": 10, "tapInstalls": 4, "localSpend": {"amount": "2.5"}},
        {"date": "2026-11-03", "impressions": 0, "taps": 0, "localSpend": {"amount": "0"}},
        {"date": "2026-11-06", "impressions": 200, "taps": 20, "localSpend": {"amount": "3.5"}}]}]}}

    def test_rows_keep_the_install_count_when_the_report_has_one(self):
        from aso.pull_revenuecat_fetch import daily_rows
        rows = daily_rows(self.REPORT, {9001: "US"}, {})
        self.assertEqual(rows[("2026-11-02", 9001, "US")], {"spend": 2.5, "impressions": 100, "taps": 10, "installs": 4})
        self.assertIsNone(rows[("2026-11-06", 9001, "US")]["installs"])        # the report gave none that day: unknown
        self.assertNotIn(("2026-11-03", 9001, "US"), rows)                     # a day with nothing is no row

    def test_a_campaign_with_no_known_storefront_is_kept_under_question_marks(self):
        from aso.pull_revenuecat_fetch import daily_rows
        self.assertIn(("2026-11-02", 9001, "??"), daily_rows(self.REPORT, {}, {}))

    def test_a_reply_that_is_not_a_report_gives_no_rows(self):
        from aso.pull_revenuecat_fetch import daily_rows
        self.assertEqual(daily_rows(None, {}, {}), {})
        self.assertEqual(daily_rows({"error": "bad field"}, {}, {}), {})


class Appending(unittest.TestCase):
    def test_a_row_is_appended_once_and_a_correction_is_a_new_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.csv"
            rows = ads_weeks(SPEND, AS_OF, "2026-11-14")
            self.assertEqual(append_changed(path, ADS_COLS, rows, ("week_start", "campaign_id")), 2)
            self.assertEqual(append_changed(path, ADS_COLS, rows, ("week_start", "campaign_id")), 0)      # nothing new
            later = [dict(rows[0], spend_usd="6.40", captured="2026-11-20")]                               # the source restated it
            self.assertEqual(append_changed(path, ADS_COLS, later, ("week_start", "campaign_id")), 1)
            stored = read_csv(path)
            self.assertEqual([r["spend_usd"] for r in stored], ["6.00", "2.00", "6.40"])                  # nothing rewritten
            same_again = [dict(later[0], captured="2026-11-21")]                                           # same values, later day
            self.assertEqual(append_changed(path, ADS_COLS, same_again, ("week_start", "campaign_id")), 0)


    def test_a_blank_install_count_never_replaces_a_known_one(self):
        key = ("week_start", "campaign_id")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.csv"
            rows = ads_weeks(SPEND, AS_OF, "2026-11-14")                              # 9001 holds 10 installs, 9002 holds 0
            append_changed(path, ADS_COLS, rows, key, keep=ADS_KEEP)
            blank = [dict(r, installs="", captured="2026-11-20") for r in rows]       # a later report gave no count at all
            self.assertEqual(append_changed(path, ADS_COLS, blank, key, keep=ADS_KEEP), 0)
            restated = [dict(rows[0], spend_usd="6.40", installs="", captured="2026-11-20")]
            self.assertEqual(append_changed(path, ADS_COLS, restated, key, keep=ADS_KEEP), 1)
            self.assertEqual([(r["spend_usd"], r["installs"]) for r in read_csv(path)][-1], ("6.40", "10"))    # the count carried over
            new_campaign = [dict(rows[0], campaign_id="9999", installs="")]
            self.assertEqual(append_changed(path, ADS_COLS, new_campaign, key, keep=ADS_KEEP), 1)
            self.assertEqual(read_csv(path)[-1]["installs"], "")                      # nothing known yet: stays unknown, not zero


    def test_a_file_of_an_older_version_keeps_its_rows_and_gains_the_new_column(self):
        key = ("week_start", "campaign_id")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.csv"
            older = [c for c in ADS_COLS if c != "installs"]
            path.write_text(",".join(older) + "\n2026-10-26,9001,us,6.00,300,30,apple-ads,2026-11-01\n", encoding="utf-8")
            rows = ads_weeks(SPEND, AS_OF, "2026-11-14")
            self.assertEqual(append_changed(path, ADS_COLS, rows, key, keep=ADS_KEEP), 2)            # no KeyError, no shifted cells
            stored = read_csv(path)
            self.assertEqual(list(stored[0]), ADS_COLS)
            self.assertEqual((stored[0]["spend_usd"], stored[0]["installs"], stored[1]["installs"]), ("6.00", "", "10"))
            path.write_text("week_start,campaign_id,mystery\n2026-10-26,9001,x\n", encoding="utf-8")
            with self.assertRaises(ValueError):                                                      # not ours: never guessed at
                append_changed(path, ADS_COLS, rows, key)

    def test_a_migration_that_fails_leaves_the_file_as_it_was(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ads.csv"
            older = [c for c in ADS_COLS if c != "installs"]
            text = (",".join(older) + "\n2026-10-26,9001,us,6.00,300,30,apple-ads,2026-11-01\n"
                    "2026-11-02,9001,us,2.50,100,10,apple-ads,2026-11-08,an,extra,cell\n"            # more cells than the header
                    "2026-11-09,9001,us,3.00,100,10,apple-ads,2026-11-14\n")
            path.write_bytes(text.encode("utf-8"))
            with self.assertRaises(ValueError):
                append_changed(path, ADS_COLS, ads_weeks(SPEND, AS_OF, "2026-11-14"), ("week_start", "campaign_id"), keep=ADS_KEEP)
            self.assertEqual(path.read_bytes(), text.encode("utf-8"))                              # not a row lost
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ["ads.csv"])                   # no half-written copy left


class Collector(unittest.TestCase):
    def test_a_second_pass_that_gets_no_install_count_leaves_the_ads_series_and_the_page_as_they_were(self):
        import contextlib
        import io

        import pull_revenuecat
        data = {"period": {"start": "2026-09-01", "end": "2026-11-14"}, "overview": {"mrr": {"value": 16.0}}, "country_cashflow": [],
                "weekly_cashflow": cashflow_weeks(REVENUE, TRIALS, SPEND, AS_OF, "2026-11-14"),
                "weekly_ads": ads_weeks(SPEND, AS_OF, "2026-11-14")}
        again = dict(data, weekly_ads=[dict(r, installs="", captured="2026-11-20") for r in data["weekly_ads"]])
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "metrics" / "ads.csv").unlink()
            for pass_ in (data, again):
                with contextlib.redirect_stdout(io.StringIO()):
                    pull_revenuecat.export_snapshots(store, pass_)
            self.assertEqual(len(read_csv(store / "metrics" / "ads.csv")), 2)
            ads = export.build_all(store, AS_OF)[0]["week/2026-11-02.json"]["families"]["ads"]["figures"]
            self.assertEqual(ads["cpi_usd"]["value"], 0.8)                              # not "nothing to measure"

    def test_export_snapshots_appends_the_series_and_keeps_the_old_files(self):
        import contextlib
        import io

        import pull_revenuecat
        data = {"period": {"start": "2026-09-01", "end": "2026-11-14"}, "overview": {"mrr": {"value": 16.0}}, "country_cashflow": [],
                "weekly_cashflow": cashflow_weeks(REVENUE, TRIALS, SPEND, AS_OF, "2026-11-14"),
                "weekly_ads": ads_weeks(SPEND, AS_OF, "2026-11-14")}
        with tempfile.TemporaryDirectory() as tmp:
            metrics = copy_store(tmp) / "metrics"
            for name in ("revenue.csv", "cashflow_weekly.csv", "ads.csv"):
                (metrics / name).unlink()
            for _ in range(2):                                          # a second run on the same day adds nothing
                with contextlib.redirect_stdout(io.StringIO()) as said:
                    pull_revenuecat.export_snapshots(metrics.parent, data)
            self.assertEqual([len(read_csv(metrics / n)) for n in ("revenue.csv", "cashflow_weekly.csv", "ads.csv")], [1, 3, 2])
            self.assertIn("revenue.csv +0, cashflow_weekly.csv +0, ads.csv +0", said.getvalue())
            self.assertTrue((metrics / "revenuecat_latest.json").is_file() and (metrics / "cashflow.csv").is_file())


class Families(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = copy_store(self.tmp.name)
        for name in ("revenue.csv", "cashflow_weekly.csv", "ads.csv"):
            (self.store / "metrics" / name).unlink(missing_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def families(self, week="2026-11-02", as_of=AS_OF):
        return export.build_all(self.store, as_of)[0][f"week/{week}.json"]["families"]

    def store_rows(self):
        metrics = self.store / "metrics"
        append_changed(metrics / "cashflow_weekly.csv", CASHFLOW_COLS, cashflow_weeks(REVENUE, TRIALS, SPEND, AS_OF, "2026-11-10"),
                       ("week_start", "country"))
        append_changed(metrics / "ads.csv", ADS_COLS, ads_weeks(SPEND, AS_OF, "2026-11-10"), ("week_start", "campaign_id"))

    def test_before_anything_is_stored_the_families_say_so(self):
        families = self.families()
        self.assertEqual((families["money"]["unavailable"]["code"], families["ads"]["unavailable"]["code"]), ("no_source", "no_source"))

    def test_money_family(self):
        self.store_rows()
        money = self.families()["money"]
        self.assertEqual((money["source"], money["fetched_at"]), ("revenuecat+apple-ads", "2026-11-10"))
        f = money["figures"]
        self.assertEqual(f["proceeds_usd"], {"value": 32.2, "by_market": {"ua": 4.2, "us": 28.0}})
        self.assertEqual(f["ad_spend_usd"], {"value": 8.0, "by_market": {"ua": 2.0, "us": 6.0}})
        self.assertEqual(f["net_cashflow_usd"], {"value": 24.2, "by_market": {"ua": 2.2, "us": 22.0}})
        self.assertEqual((f["transactions"]["value"], f["new_trials"]["value"]), (6, 5))

    def test_ads_family(self):
        self.store_rows()
        ads = self.families()["ads"]["figures"]
        self.assertEqual(ads["spend_usd"], {"value": 8.0, "by_market": {"ua": 2.0, "us": 6.0}, "by_campaign": {"9001": 6.0, "9002": 2.0}})
        self.assertEqual((ads["ttr"]["value"], ads["ttr"]["numerator"], ads["ttr"]["denominator"]), (0.095, 38, 400))
        self.assertEqual((ads["cpi_usd"]["value"], ads["cpi_usd"]["numerator"], ads["cpi_usd"]["denominator"]), (0.8, 8.0, 10))
        self.assertEqual(ads["cpi_usd"]["by_campaign"], {"9001": 0.6, "9002": None})          # no install: nothing to divide by

    def test_a_blank_install_row_already_in_the_store_does_not_erase_the_count(self):
        self.store_rows()
        blank = [dict(r, installs="", captured="2026-11-20") for r in ads_weeks(SPEND, AS_OF, "2026-11-10")]
        append_changed(self.store / "metrics" / "ads.csv", ADS_COLS, blank, ("week_start", "campaign_id"))   # as an older version wrote it
        ads = self.families(as_of=dt.date(2026, 11, 21))["ads"]["figures"]
        self.assertEqual(ads["cpi_usd"]["value"], 0.8)
        self.assertEqual(ads["installs"]["value"], 10)

    def test_a_blank_row_captured_later_wins_whatever_its_place_in_the_file(self):
        path = self.store / "metrics" / "ads.csv"
        known = ads_weeks(SPEND, AS_OF, "2026-11-10")
        blank = [dict(r, installs="", captured="2026-11-20") for r in known]
        append_csv(path, ADS_COLS, blank + known)                         # the later capture is the earlier line
        ads = self.families(as_of=dt.date(2026, 11, 21))["ads"]["figures"]
        self.assertEqual((ads["installs"]["value"], ads["cpi_usd"]["value"]), (10, 0.8))

    def test_a_week_only_money_knows_still_gets_a_file(self):
        self.store_rows()
        families = self.families("2026-10-26")
        self.assertEqual(families["money"]["figures"]["proceeds_usd"]["value"], 21.0)
        self.assertEqual(families["ads"]["unavailable"]["code"], "no_data")                   # stored, but nothing that week

    def test_a_correction_row_wins(self):
        self.store_rows()
        fixed = [{"week_start": "2026-11-02", "country": "US", "transactions": 5, "new_trials": 4, "gross_revenue_usd": "50.00",
                  "proceeds_usd": "35.00", "ad_spend_usd": "6.00", "source": "revenuecat+apple-ads", "captured": "2026-11-13"}]
        append_changed(self.store / "metrics" / "cashflow_weekly.csv", CASHFLOW_COLS, fixed, ("week_start", "country"))
        money = self.families()["money"]
        self.assertEqual((money["figures"]["proceeds_usd"]["value"], money["fetched_at"]), (39.2, "2026-11-13"))
        self.assertEqual(self.families(as_of=dt.date(2026, 11, 12))["money"]["figures"]["proceeds_usd"]["value"], 32.2)

    def test_subscriptions_come_from_the_stored_reads(self):
        rows = [{"captured": "2026-11-03", "active_subscriptions": 3, "active_trials": 2, "mrr_usd": 12.5, "revenue_28d_usd": 40.0,
                 "new_customers_28d": 30, "active_users_28d": 55, "source": "revenuecat"},
                {"captured": "2026-11-10", "active_subscriptions": 4, "active_trials": 1, "mrr_usd": 16.0, "revenue_28d_usd": 52.0,
                 "new_customers_28d": 41, "active_users_28d": "", "source": "revenuecat"}]
        append_changed(self.store / "metrics" / "revenue.csv", REVENUE_COLS, rows, ("captured",))
        (self.store / "metrics" / "revenuecat_latest.json").write_text(
            '{"captured_at": "2026-11-12T00:00:00Z", "overview": {"mrr": {"value": 99}}}', encoding="utf-8")
        files = export.build_all(self.store, AS_OF)[0]
        self.assertNotIn("snapshot/2026-11-12.json", files)            # the series is the source once it has a row
        figures = files["snapshot/2026-11-10.json"]["families"]["subscriptions"]["figures"]
        self.assertEqual((figures["mrr_usd"]["value"], figures["active_subscriptions"]["value"]), (16.0, 4))
        self.assertEqual(figures["active_users_28d"]["unavailable"]["code"], "no_data")
        self.assertEqual(files["snapshot/2026-11-03.json"]["families"]["subscriptions"]["figures"]["mrr_usd"]["value"], 12.5)

    def test_every_file_stays_valid(self):
        self.store_rows()
        catalog = contract.load_catalog()
        for path, obj in export.build_all(self.store, AS_OF)[0].items():
            with self.subTest(path=path):
                self.assertEqual(contract.validate(path, contract.canonical(obj), catalog), [])


if __name__ == "__main__":
    unittest.main()
