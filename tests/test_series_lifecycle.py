"""The install lifecycle by closed week (an opt-in sample), and the collection pass running every writer."""
import contextlib
import datetime as dt
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import SAMPLE, copy_store  # noqa: E402

import pull_funnel  # noqa: E402
from aso.commands import collect, cycle  # noqa: E402
from aso.dashboard import export  # noqa: E402
from aso.store import read_csv  # noqa: E402

TODAY = dt.date(2026, 11, 14)


def event(day, kind, territory, count, installed="", download="First-time download"):
    return {"Date": day, "Event": kind, "Download Type": download if kind == "Install" else "", "Territory": territory,
            "Counts": str(count), "App Download Date": installed}


ROWS = [
    event("2026-11-02", "Install", "US", 10), event("2026-11-05", "Install", "US", 5), event("2026-11-04", "Install", "UA", 4),
    event("2026-11-03", "Install", "US", 7, download="Redownload"),               # not a first install
    event("2026-11-03", "Delete", "US", 6, installed="2026-11-03"),              # the same day
    event("2026-11-06", "Delete", "US", 3, installed="2026-10-20"),              # weeks later
    event("2026-11-07", "Delete", "UA", 1, installed="2026-11-06"),              # the next day
    event("2026-11-08", "Delete", "UA", 1),                                      # no install day: counted, not timed
    event("2026-11-10", "Install", "US", 99),                                    # the week of 11-09 is still open
]


class Folding(unittest.TestCase):
    def test_closed_monday_weeks_per_segment(self):
        folded = pull_funnel.fold_lifecycle(ROWS, today=TODAY)
        self.assertEqual(sorted(folded), [("2026-11-02", "all"), ("2026-11-02", "ua"), ("2026-11-02", "us")])
        whole, us = folded[("2026-11-02", "all")], folded[("2026-11-02", "us")]
        self.assertEqual((whole["installs"], whole["deletions"], whole["within_1d"], whole["timed"]), (19, 11, 7, 10))
        self.assertEqual((us["installs"], us["deletions"], us["within_1d"], us["timed"]), (15, 9, 6, 9))

    def test_rows_are_written_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            folded = pull_funnel.fold_lifecycle(ROWS, today=TODAY)
            written, skipped = pull_funnel.write_lifecycle_weeks(out, folded, today=TODAY)
            self.assertEqual((written, skipped), (3, []))
            again, skipped = pull_funnel.write_lifecycle_weeks(out, folded, today=TODAY)
            self.assertEqual((again, len(skipped)), (0, 3))
            rows = read_csv(out / "lifecycle.csv")
            self.assertEqual({r["source"] for r in rows}, {"live:asc analytics daily lifecycle@2026-11-14"})
            whole = next(r for r in rows if r["segment"] == "all")
            self.assertEqual((whole["first_installs_optin"], whole["deletions_optin"], whole["deleted_within_1d"],
                              whole["deletions_per_100_installs"]), ("19", "11", "7", "57.9"))
            # the middle day of the timed deletions: six the same day, one the next, three after 17 days
            self.assertEqual([r["median_days_to_delete"] for r in rows], ["0", "1", "0"])


class Family(unittest.TestCase):
    def lifecycle(self, store, week="2026-11-02"):
        return export.build_all(store, TODAY)[0][f"week/{week}.json"]["families"]["lifecycle"]

    def test_the_family_carries_both_totals_and_the_storefronts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            path = store / "metrics" / "lifecycle.csv"
            path.write_text("\n".join(path.read_text(encoding="utf-8").splitlines()[:2]) + "\n", encoding="utf-8")   # legacy row only
            self.assertEqual(self.lifecycle(store)["unavailable"]["code"], "no_source")
            pull_funnel.write_lifecycle_weeks(store / "metrics", pull_funnel.fold_lifecycle(ROWS, today=TODAY), today=TODAY)
            family = self.lifecycle(store)
            self.assertEqual((family["source"], family["fetched_at"]), ("asc-analytics", "2026-11-14"))
            f = family["figures"]
            self.assertEqual(f["optin_installs"], {"value": 19, "by_market": {"ua": 4, "us": 15}})
            self.assertEqual((f["deletions_per_100"]["value"], f["deletions_per_100"]["numerator"], f["deletions_per_100"]["denominator"]),
                             (57.9, 11, 19))
            self.assertEqual(f["deletions_per_100"]["by_market"], {"ua": 50.0, "us": 60.0})
            self.assertEqual(f["deleted_within_1d"]["value"], 7)
            notes = export.build_all(store, TODAY)[1]
            self.assertTrue(any("lifecycle.csv" in n and "left out" in n for n in notes), notes)       # the hand-written row
            self.assertEqual(self.lifecycle(store, "2026-10-26")["unavailable"]["code"], "no_data")

    def test_the_sample_holds_three_weeks(self):
        figures = self.lifecycle(SAMPLE)["figures"]
        self.assertEqual((figures["optin_installs"]["value"], figures["optin_deletions"]["value"]), (20, 8))


class AWeekTheReportsHaveNotReachedYet(unittest.TestCase):
    """Apple publishes a day about two days late. On the Monday after a week its Sunday is not in any report yet, and
    a week is written once: so a week is folded only when the reports already hold a day after it."""
    DAY = {"Territory": "US", "Counts": "5", "Source Type": "App Store search"}

    def funnel(self, last_day):
        days = [f"2026-11-{n:02d}" for n in range(2, 16) if f"2026-11-{n:02d}" <= last_day]
        discovery = [dict(self.DAY, Date=d, Event="Impression") for d in days]
        downloads = [dict(self.DAY, Date=d, **{"Download Type": "First-time download"}) for d in days]
        return discovery, downloads

    def test_the_week_waits_until_both_reports_hold_a_later_day(self):
        monday = dt.date(2026, 11, 9)                   # the week of 11-02 closed yesterday, by the clock
        discovery, downloads = self.funnel("2026-11-07")        # ...but the reports reach Saturday only
        self.assertEqual(pull_funnel.fold_reports(discovery, downloads, today=monday), {})
        discovery, downloads = self.funnel("2026-11-09")
        self.assertEqual(sorted({week for week, _ in pull_funnel.fold_reports(discovery, downloads, today=dt.date(2026, 11, 11))}),
                         ["2026-11-02"])
        late, _ = self.funnel("2026-11-09")
        _, short = self.funnel("2026-11-08")                    # one report a day behind the other: still waiting
        self.assertEqual(pull_funnel.fold_reports(late, short, today=dt.date(2026, 11, 11)), {})

    def test_the_lifecycle_week_waits_the_same_way(self):
        rows = [event("2026-11-04", "Install", "US", 4), event("2026-11-08", "Install", "US", 1)]
        self.assertEqual(pull_funnel.fold_lifecycle(rows, today=dt.date(2026, 11, 11)), {})
        rows.append(event("2026-11-09", "Install", "US", 2))
        self.assertEqual(sorted(pull_funnel.fold_lifecycle(rows, today=dt.date(2026, 11, 11))), [("2026-11-02", "all"), ("2026-11-02", "us")])


class HalfAPull(unittest.TestCase):
    """A funnel week needs both reports. A week is written once, so a row holding only one of them would stay half
    empty for good: when one report cannot be read, no funnel week is written at all."""

    def pull(self, out, failing):
        def fetch(request_id, report, raw_dir, prefix, **_):
            if prefix == failing:
                raise RuntimeError("rate limited")
            day = {"Date": "2026-11-03", "Territory": "US", "Counts": "5", "Source Type": "App Store search"}
            later = dict(day, Date="2026-11-09")       # the reports have reached past the week of 11-02
            rows = {"r14": [dict(day, Event="Impression"), dict(later, Event="Impression")],
                    "r3": [dict(d, **{"Download Type": "First-time download"}) for d in (day, later)],
                    "lifecycle": [event("2026-11-03", "Install", "US", 4), event("2026-11-09", "Install", "US", 1)]}[prefix]
            return rows, 1, 1, "2026-10-01"
        argv = ["pull_funnel.py", "--app", "1000000001", "--out", str(out), "--raw-dir", str(out / "raw")]
        with mock.patch.object(pull_funnel, "request_and_reports", return_value=("req", {})), \
                mock.patch.object(pull_funnel, "snapshot_reports", return_value=None), \
                mock.patch.object(pull_funnel, "fetch_report", side_effect=fetch), mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as said:
            return pull_funnel.main(), said.getvalue()

    def test_one_report_missing_writes_no_funnel_week(self):
        for failing in ("r14", "r3"):
            with tempfile.TemporaryDirectory() as tmp:
                code, said = self.pull(Path(tmp), failing)
                self.assertEqual(code, 2)
                self.assertFalse((Path(tmp) / "weekly.csv").exists(), failing)
                self.assertIn("weekly.csv was not updated", said)
                self.assertTrue((Path(tmp) / "lifecycle.csv").is_file())          # its own report, its own file

    def test_both_reports_write_the_week_and_a_missing_lifecycle_does_not_stop_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, said = self.pull(Path(tmp), "lifecycle")
            self.assertEqual(len(read_csv(Path(tmp) / "weekly.csv")), 3)          # all, search, us
            self.assertFalse((Path(tmp) / "lifecycle.csv").exists())
            # but the pull is not clean: a report that could not be read is said in the exit code, not only in a line
            self.assertEqual(code, 2, said)
            self.assertIn("Partial funnel stage for lifecycle: rate limited", said)

    def test_a_clean_pull_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.pull(Path(tmp), None)[0], 0)

    def test_the_pass_names_the_report_that_failed(self):
        lines = ["App ID 1: 3 observed week/segment groups; appended 3 new rows to weekly.csv; skipped 0 existing week/segment keys.",
                 "Partial funnel stage for lifecycle: ASC command failed (asc analytics instances; exit 39).", ""]
        self.assertIn("lifecycle", cycle.funnel_failure(lines))
        self.assertEqual(cycle.funnel_failure(["", ""]), "no output")


class TheHistoryBeforeTheOngoingRequest(unittest.TestCase):
    """An ongoing request holds about a month of days. Apple gives the days before it through a one-time snapshot
    request; the collector reads both, and a day both hold is taken from the ongoing one."""
    DAY = {"Territory": "US", "Source Type": "App Store search"}

    def rows(self, days, count):
        return ([dict(self.DAY, Date=d, Counts=str(count), Event="Impression") for d in days],
                [dict(self.DAY, Date=d, Counts=str(count), **{"Download Type": "First-time download"}) for d in days])

    filled = {name: {"instances": [{"id": "i"}]} for name in (pull_funnel.DISCOVERY_REPORT, pull_funnel.DOWNLOADS_REPORT,
                                                             pull_funnel.INSTALLS_REPORT)}

    def test_a_snapshot_apple_has_not_filled_yet_is_not_a_failure(self):
        empty = {name: {"instances": []} for name in self.filled}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(type(self), "filled", empty):
            code, weekly, _ = self.pull(Path(tmp))
            self.assertEqual(code, 0)
            self.assertEqual(sorted({week for week, _ in weekly}), ["2026-11-02"])

    def test_a_day_both_hold_comes_from_the_newer_one(self):
        newer = [{"Date": "2026-11-03", "Counts": "5"}, {"Date": "2026-11-04", "Counts": "5"}]
        older = [{"Date": "2026-11-03", "Counts": "9"}, {"Date": "2026-10-28", "Counts": "9"}]
        self.assertEqual(pull_funnel.merge_days(newer, older),
                         newer + [{"Date": "2026-10-28", "Counts": "9"}])
        self.assertEqual(pull_funnel.merge_days([], older), older)

    def pull(self, out, snapshot_fails=None):
        recent = [f"2026-11-{n:02d}" for n in range(2, 11)]                    # the ongoing request: 11-02 .. 11-10
        early = [f"2026-10-{n:02d}" for n in range(19, 32)] + ["2026-11-01", "2026-11-02", "2026-11-03"]

        def fetch(request_id, report, raw_dir, prefix, **_):
            if request_id == "snap" and prefix == snapshot_fails:
                raise RuntimeError("rate limited")
            # the ongoing request's first daily report was processed on 10-26: the week of 11-02 is its first whole one
            days, count, first = (recent, 5, "2026-10-26") if request_id == "req" else (early, 9, "2026-11-13")
            if prefix == "lifecycle":
                return [event(d, "Install", "US", count) for d in days], 1, 1, first
            discovery, downloads = self.rows(days, count)
            return (discovery if prefix == "r14" else downloads), 1, 1, first
        argv = ["pull_funnel.py", "--app", "1000000001", "--out", str(out), "--raw-dir", str(out / "raw")]
        with mock.patch.object(pull_funnel, "request_and_reports", return_value=("req", {})), \
                mock.patch.object(pull_funnel, "snapshot_reports", return_value=("snap", self.filled)), \
                mock.patch.object(pull_funnel, "fetch_report", side_effect=fetch), mock.patch.object(sys, "argv", argv), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as said:
            code = pull_funnel.main()
        weekly = {(r["week_start"], r["segment"]): r for r in read_csv(out / "weekly.csv")}
        return code, weekly, said.getvalue()

    def test_earlier_weeks_come_from_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, weekly, said = self.pull(Path(tmp))
            self.assertEqual(code, 0, said)
            self.assertEqual(sorted({week for week, _ in weekly}), ["2026-10-19", "2026-10-26", "2026-11-02"])
            self.assertEqual(weekly[("2026-10-19", "all")]["impressions"], "63")       # seven days of nine, snapshot only
            # 10-26 .. 11-01 from the snapshot; in the week of 11-02 every day is in the ongoing request, so the
            # snapshot's 11-02 and 11-03 are not added on top
            self.assertEqual(weekly[("2026-10-26", "all")]["impressions"], "63")
            self.assertEqual(weekly[("2026-11-02", "all")]["impressions"], "35")
            self.assertEqual(sorted({r["week_start"] for r in read_csv(Path(tmp) / "lifecycle.csv")}),
                             ["2026-10-19", "2026-10-26", "2026-11-02"])

    def test_a_snapshot_read_by_half_adds_no_earlier_week(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, weekly, said = self.pull(Path(tmp), snapshot_fails="r3")
            self.assertEqual(code, 2)
            self.assertEqual(sorted({week for week, _ in weekly}), ["2026-11-02"])      # the ongoing weeks are still written
            self.assertIn("Partial funnel stage for snapshot r3", said)


class TheSkillsOwnCollector(unittest.TestCase):
    """Only the skill's pull_funnel.py writes closed Monday weeks the export can show. A store that carries a script
    of its own under the same name must not take its place, or its page never gets a funnel week."""

    def test_a_store_local_script_does_not_replace_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "scripts").mkdir()
            (store / "scripts" / "pull_funnel.py").write_text('APP_ID = "1000000001"\n', encoding="utf-8")
            self.assertEqual(collect.funnel_script(store), collect.SKILL_DIR / "scripts" / "pull_funnel.py")

    def test_the_pass_and_the_command_both_ask_for_it(self):
        for module in (collect, cycle):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertNotIn('store / "scripts" / "pull_funnel.py"', source.replace(collect_helper(source), ""), module.__name__)


def collect_helper(source: str) -> str:
    """The text of `funnel_script` itself, the one place allowed to name a store-local script."""
    start = source.find("def funnel_script(")
    return source[start:source.find("\n\n\n", start)] if start >= 0 else ""


class EveryWriter(unittest.TestCase):
    """The collection pass also stores the in-app weeks and the chart positions, when the store is set up for them."""

    def run_extras(self, store, **patches):
        with contextlib.ExitStack() as stack, contextlib.redirect_stdout(io.StringIO()) as said:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(cycle, name, value))
            cycle.collect_extras(store, {"app_id": "1000000001", "brand": "tidepool"})
        return said.getvalue()

    def test_a_store_not_set_up_for_them_says_so_and_reads_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            said = self.run_extras(copy_store(tmp), store_weeks=mock.Mock(side_effect=AssertionError("must not run")),
                                   fetch_category_chart=mock.Mock(side_effect=AssertionError("must not run")))
        self.assertIn("in-app weeks: not set up", said)
        self.assertIn("chart positions: not set up", said)

    def test_a_store_set_up_for_them_gets_both(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "config.md").open("a", encoding="utf-8") as fh:
                fh.write("**Firebase Project ID**: demo-project\n**GA4 Property ID**: 123\n"
                         "**Charts storefronts**: us, ua\n**Charts genres**: weather\n")
            (store / "metrics" / "charts.csv").unlink()
            weeks = mock.Mock(return_value=["2026-11-02"])
            # the feed numbers its entries from one: the app is the twelfth of twelve
            apps = [{"app_id": str(n), "name": f"App {n}", "developer": "", "rank": n} for n in range(1, 12)]
            chart = mock.Mock(return_value=(apps + [{"app_id": "1000000001", "name": "Tidepool", "developer": "", "rank": 12}], ""))
            said = self.run_extras(store, store_weeks=weeks, fetch_category_chart=chart)
            self.assertEqual(weeks.call_args.args[:3], (store, "demo-project", "analytics_123"))
            self.assertEqual(chart.call_count, 2)
            self.assertIn("in-app weeks: 1 stored", said)
            self.assertIn("chart positions: charts.csv +2", said)
            self.assertEqual([(r["market"], r["position"]) for r in read_csv(store / "metrics" / "charts.csv")], [("us", "12"), ("ua", "12")])

    def test_a_step_that_fails_says_why_and_the_next_still_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            with (store / "config.md").open("a", encoding="utf-8") as fh:
                fh.write("**Firebase Project ID**: demo-project\n**GA4 Property ID**: 123\n**Charts storefronts**: us\n")
            said = self.run_extras(store, store_weeks=mock.Mock(side_effect=RuntimeError("bq is not installed")),
                                   fetch_category_chart=mock.Mock(return_value=(None, "timeout")))
        self.assertIn("in-app weeks: failed (bq is not installed)", said)
        self.assertIn("chart positions: charts.csv +", said)


if __name__ == "__main__":
    unittest.main()
