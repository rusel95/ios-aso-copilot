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


class HalfAPull(unittest.TestCase):
    """A funnel week needs both reports. A week is written once, so a row holding only one of them would stay half
    empty for good: when one report cannot be read, no funnel week is written at all."""

    def pull(self, out, failing):
        def fetch(request_id, report, raw_dir, prefix, **_):
            if prefix == failing:
                raise RuntimeError("rate limited")
            day = {"Date": "2026-11-03", "Territory": "US", "Counts": "5", "Source Type": "App Store search"}
            rows = {"r14": [dict(day, Event="Impression")], "r3": [dict(day, **{"Download Type": "First-time download"})],
                    "lifecycle": [event("2026-11-03", "Install", "US", 4)]}[prefix]
            return rows, 1, 1, "2026-10-01"
        argv = ["pull_funnel.py", "--app", "1000000001", "--out", str(out), "--raw-dir", str(out / "raw")]
        with mock.patch.object(pull_funnel, "request_and_reports", return_value=("req", {})), \
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
