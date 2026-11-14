"""Period files: closed weeks of flows, snapshots of stocks; and writing and checking the data folder."""
import shutil
import datetime as dt
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import SAMPLE, SAMPLE_FILES, SAMPLE_SNAPSHOTS, copy_store  # noqa: E402

from aso.dashboard import contract, export  # noqa: E402
from aso.ranks import coverage  # noqa: E402
from aso.store import read_ranks  # noqa: E402

DAY = date(2026, 11, 14)
COLLECTOR = "live:asc analytics daily r14+r3@2026-11-12"


def built(store=SAMPLE, as_of=DAY):
    return export.build_all(store, as_of)


def funnel(files, week="2026-11-02"):
    return files[f"week/{week}.json"]["families"]["store_funnel"]["figures"]


class Weeks(unittest.TestCase):
    def test_closed_weeks_only(self):
        files, notes = built()
        self.assertEqual(sorted(p for p in files if p.startswith("week/")),
                         ["week/2026-10-19.json", "week/2026-10-26.json", "week/2026-11-02.json"])
        self.assertTrue(any("weekly.csv" in n and "left out" in n for n in notes), notes)

    def test_funnel_figures(self):
        f = funnel(built()[0])
        self.assertEqual(f["impressions"], {"value": 1500, "by_market": {"ua": 600, "us": 900}})
        self.assertEqual((f["page_cvr"]["value"], f["page_cvr"]["numerator"], f["page_cvr"]["denominator"]), (0.4, 64, 160))
        self.assertEqual((f["view_rate"]["numerator"], f["view_rate"]["denominator"]), (160, 1500))
        self.assertEqual(f["impression_cvr"]["by_market"], {"ua": 0.04, "us": 0.044444})

    def test_the_family_names_its_source_and_fetch_day_once(self):
        family = built()[0]["week/2026-11-02.json"]["families"]["store_funnel"]
        self.assertEqual((family["source"], family["fetched_at"]), ("asc-analytics", "2026-11-10"))

    def test_families_nothing_stores_yet_say_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            for name in ("cashflow_weekly.csv", "ads.csv", "telemetry.csv"):
                (store / "metrics" / name).unlink(missing_ok=True)
            lifecycle = store / "metrics" / "lifecycle.csv"            # only the hand-written row stays: no collector row
            lifecycle.write_text("\n".join(lifecycle.read_text(encoding="utf-8").splitlines()[:2]) + "\n", encoding="utf-8")
            families = built(store)[0]["week/2026-11-02.json"]["families"]
        for name in ("lifecycle", "money", "ads", "in_app"):
            with self.subTest(family=name):
                self.assertEqual(families[name]["unavailable"]["code"], "no_source")
                self.assertTrue(families[name]["unavailable"]["reason"])

    def test_bad_row_is_named_and_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            path = store / "metrics" / "weekly.csv"
            lines = path.read_text(encoding="utf-8").splitlines()
            at = next(n for n, line in enumerate(lines) if line.startswith("2026-11-02,ua,"))
            lines[at] = lines[at].replace("2026-11-02,ua,600,", "2026-11-02,ua,abc,")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            files, notes = built(store)
        self.assertTrue(any(f"metrics/weekly.csv:{at + 1}" in n and "abc" in n for n in notes), notes)
        self.assertEqual(funnel(files)["impressions"], {"value": 1500, "by_market": {"us": 900}})

    def test_correction_row_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "metrics" / "weekly.csv").open("a", encoding="utf-8") as fh:
                fh.write(f"2026-11-02,all,1600,160,64,40.00,,{COLLECTOR},2026-11-12,corrected\n")
            f = funnel(built(store)[0])
        self.assertEqual((f["impressions"]["value"], f["view_rate"]["denominator"]), (1600, 1600))

    def test_of_two_rows_recorded_the_same_day_the_later_line_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "metrics" / "weekly.csv").open("a", encoding="utf-8") as fh:
                fh.write("2026-11-02,all,1700,160,64,40.00,,live:asc analytics daily r14+r3@2026-11-10,2026-11-10,again\n")
            self.assertEqual(funnel(built(store)[0])["impressions"]["value"], 1700)

    def test_a_week_with_no_impressions_has_no_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "metrics" / "weekly.csv").open("a", encoding="utf-8") as fh:
                fh.write(f"2026-11-02,all,0,0,0,,,{COLLECTOR},2026-11-12,empty week\n")
            f = funnel(built(store)[0])
        self.assertEqual(f["impressions"]["value"], 0)                       # a measured zero stays a zero
        self.assertEqual(f["view_rate"]["unavailable"]["code"], "no_data")   # nothing to divide by


class Snapshots(unittest.TestCase):
    def test_one_snapshot_per_sweep_and_per_capture(self):
        files, _ = built()
        self.assertEqual(sorted(p for p in files if p.startswith("snapshot/")),
                         [f"snapshot/{day}.json" for day in SAMPLE_SNAPSHOTS])

    def test_rank_snapshot(self):
        r = built()[0]["snapshot/2026-11-02.json"]["families"]["ranks"]["figures"]
        self.assertEqual((r["keys_read"]["value"], r["share_top30"]["numerator"], r["share_top30"]["denominator"]), (9, 4, 9))
        self.assertEqual(r["share_top30"]["value"], 0.444444)
        self.assertEqual(r["top10"], {"value": 2, "by_market": {"ua": 1, "us": 1}})
        self.assertEqual(r["tracked_keys"]["value"], 10)

    def test_coverage_is_the_ledgers(self):
        self.assertEqual(coverage(read_ranks(SAMPLE)),
                         {"tracked": 12, "paired": 8, "unobserved": 1, "failed": 2, "unmeasurable": 1, "observations": 38})
        c = built()[0]["snapshot/2026-11-09.json"]["families"]["coverage"]["figures"]
        self.assertEqual([c[k]["value"] for k in ("paired_keys", "unmeasurable_keys", "failed_requests", "observations")],
                         [8, 1, 2, 38])
        early = built()[0]["snapshot/2026-10-05.json"]["families"]["coverage"]["figures"]
        self.assertEqual((early["observations"]["value"], early["paired_keys"]["value"]), (12, 0))

    def test_demand_and_share_on_the_last_day_of_the_week_they_measure(self):
        # the week of 2026-10-25 was read on 2026-11-03: it is a fact about that week, so it sits on the week's last day
        self.assertNotIn("demand", built()[0]["snapshot/2026-11-03.json"]["families"])
        families = built()[0]["snapshot/2026-10-31.json"]["families"]
        self.assertEqual((families["demand"]["fetched_at"], families["impression_share"]["fetched_at"]), ("2026-11-03", "2026-11-03"))
        self.assertEqual(families["demand"]["rows"], [{"market": "us", "genre": "WEATHER", "term": "tide times",
                                                       "popularity_100": 41}])
        self.assertEqual(families["demand"]["cuts"], [
            {"market": "ua", "genre": "", "listed": 0, "min_popularity_100": None},
            {"market": "us", "genre": "WEATHER", "listed": 500, "min_popularity_100": 38}])
        self.assertEqual(families["demand"]["measured"], {"start": "2026-10-25", "end": "2026-10-31"})
        self.assertEqual(families["impression_share"]["rows"], [{"market": "us", "term": "tide tracker", "rank": 2,
                                                                 "share_low": 0.31, "share_high": 0.4}])

    def test_weeks_read_on_one_day_stay_apart(self):
        """A history pull stores many weeks at once; each is its own snapshot, not one day holding the last of them."""
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "metrics" / "popularity.csv").open("a", encoding="utf-8") as fh:
                fh.write("2026-10-11,2026-11-14,us,WEATHER,tide times,150,33,2,basket,asc-ads-insights\n"
                         "2026-10-18,2026-11-14,us,WEATHER,tide times,140,36,2,basket,asc-ads-insights\n"
                         "2026-10-25,2026-11-14,us,WEATHER,tide times,118,42,2,basket,asc-ads-insights\n")    # a later read of a week already held
            files = export.build_all(store, dt.date(2026, 11, 14))[0]
            read = {day: files[f"snapshot/{day}.json"]["families"]["demand"] for day in ("2026-10-17", "2026-10-24", "2026-10-31")}
            self.assertEqual([read[d]["rows"][0]["popularity_100"] for d in sorted(read)], [33, 36, 42])
            self.assertEqual(read["2026-10-31"]["fetched_at"], "2026-11-14")              # the later read stands, and says when
            self.assertEqual(read["2026-10-17"]["measured"], {"start": "2026-10-11", "end": "2026-10-17"})
            before = export.build_all(store, dt.date(2026, 11, 10))[0]                    # a day before the history pull
            self.assertNotIn("snapshot/2026-10-17.json", before)
            self.assertEqual(before["snapshot/2026-10-31.json"]["families"]["demand"]["rows"][0]["popularity_100"], 41)

    def test_subscriptions_from_the_latest_read_when_the_store_has_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "metrics" / "revenue.csv").unlink()                 # a store that has not stored the series yet
            (store / "metrics" / "revenuecat_latest.json").write_text(
                '{"captured_at": "2026-11-04T10:39:35Z", "overview": {"active_subscriptions": {"value": 6}, '
                '"active_trials": {"value": 1}, "mrr": {"value": 15}, "revenue": {"value": 53}}}', encoding="utf-8")
            figures = built(store)[0]["snapshot/2026-11-04.json"]["families"]["subscriptions"]["figures"]
            self.assertEqual((figures["active_subscriptions"]["value"], figures["mrr_usd"]["value"]), (6, 15))
            self.assertEqual(figures["new_customers_28d"]["unavailable"]["code"], "no_data")
            self.assertNotIn("snapshot/2026-11-04.json", built(store, date(2026, 11, 3))[0])


class Whole(unittest.TestCase):
    def test_every_file_is_valid(self):
        catalog = contract.load_catalog()
        files, _ = built()
        self.assertEqual(len(files), SAMPLE_FILES)
        for path, obj in files.items():
            with self.subTest(path=path):
                self.assertEqual(contract.validate(path, contract.canonical(obj), catalog), [])

    def test_two_exports_are_identical(self):
        first, second = built()[0], built()[0]
        self.assertEqual({p: contract.canonical(o) for p, o in first.items()},
                         {p: contract.canonical(o) for p, o in second.items()})

    def test_fresh_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            shutil.rmtree(store / "hypotheses")
            (store / "queue.md").unlink()
            for path in (store / "metrics").glob("*.csv"):
                path.write_text(path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
            files, _ = built(store)
            self.assertEqual(sorted(files), ["events.json", "hypotheses.json", "keys.json"])
            self.assertEqual((files["hypotheses.json"]["hypotheses"], files["keys.json"]["keys"]), ([], []))
            catalog = contract.load_catalog()
            for path, obj in files.items():
                self.assertEqual(contract.validate(path, contract.canonical(obj), catalog), [])

    def test_as_of_in_the_past(self):
        files, notes = built(as_of=date(2026, 11, 5))
        self.assertEqual(sorted(p for p in files if p.startswith("week/")), ["week/2026-10-19.json", "week/2026-10-26.json"])
        self.assertNotIn("snapshot/2026-11-09.json", files)
        due = {h["id"]: h for h in files["hypotheses.json"]["hypotheses"]}["H005"]
        self.assertEqual((due["state"], due["days_past_window"]), ("due", 2))
        self.assertTrue(any("verdict" in n for n in notes), notes)

    def test_rows_recorded_after_as_of_are_not_known_yet(self):
        # the week of 10-26 closed on 11-01 but was recorded on 11-03: on 11-02 the store did not hold it
        files, _ = built(as_of=date(2026, 11, 2))
        self.assertEqual(sorted(p for p in files if p.startswith("week/")), ["week/2026-10-19.json"])


class WriteAndCheck(unittest.TestCase):
    def test_write_then_check_then_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            files, _ = built(store)
            done = export.write(store, files)
            self.assertEqual((len(done["written"]), done["unchanged"], done["removed"]), (SAMPLE_FILES, [], []))
            self.assertEqual(export.check(store, files), [])
            again = export.write(store, files)
            self.assertEqual((again["written"], len(again["unchanged"])), ([], SAMPLE_FILES))
            target = store / "data" / "week" / "2026-11-02.json"
            target.write_text(target.read_text(encoding="utf-8").replace("1500", "1501"), encoding="utf-8")
            (store / "data" / "keys.json").unlink()
            self.assertEqual(export.check(store, files), ["keys.json", "week/2026-11-02.json"])

    def test_write_removes_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            files, _ = built(store)
            stray = store / "data" / "week" / "2000-01-03.json"
            stray.parent.mkdir(parents=True)
            stray.write_text("{}\n", encoding="utf-8")
            keep = store / "data" / "notes.txt"                       # not a data file: never touched
            keep.write_text("mine\n", encoding="utf-8")
            self.assertIn("week/2000-01-03.json", export.check(store, files))
            done = export.write(store, files)
            self.assertEqual(done["removed"], ["week/2000-01-03.json"])
            self.assertFalse(stray.exists())
            self.assertTrue(keep.exists())


if __name__ == "__main__":
    unittest.main()
