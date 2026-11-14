"""In-app telemetry as a stored series: one closed week per query, rows with both totals, and the in_app family."""
import contextlib
import datetime as dt
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import copy_store  # noqa: E402

import pull_bigquery_telemetry as telemetry  # noqa: E402
from aso.dashboard import contract, export  # noqa: E402
from aso.store import read_csv  # noqa: E402

WEEK = dt.date(2026, 11, 2)
# as `bq --format=json` gives it: numbers arrive as text
DATA = {
    "funnel": {"total_users": "50", "step1_first_open": "40", "step5_media_swiped": "22", "step6_cleanup_completed": "18"},
    "compression": [{"media_type": "video", "initiated": "20", "completed": "15", "failed": "5", "total_gb_saved": "1.5"},
                    {"media_type": "Live Photo", "initiated": "0", "completed": "0", "failed": "0", "total_gb_saved": None}],
    "monetization": [{"entry_point": "onboarding", "paywall_views": "30", "paywall_users": "25", "purchase_attempts": "4",
                      "purchases_completed": "3", "buyers": "3"}],
}


def rows_by_metric(rows):
    return {(r["section"], r["metric"]): (r["numerator"], r["denominator"]) for r in rows}


class Rows(unittest.TestCase):
    def test_one_row_per_number_with_both_totals_where_there_are_two(self):
        rows = telemetry.telemetry_rows(DATA, WEEK, "2026-11-10")
        found = rows_by_metric(rows)
        self.assertEqual(found[("funnel", "users")], (50, ""))
        self.assertEqual(found[("funnel", "first_open")], (40, ""))
        self.assertEqual(found[("funnel", "cleanup_completed")], (18, ""))
        self.assertEqual(found[("compression", "video_completed")], (15, ""))
        self.assertEqual(found[("compression", "video_completed_share")], (15, 20))
        self.assertEqual(found[("compression", "video_gb_saved")], (1.5, ""))
        self.assertEqual(found[("compression", "live_photo_completed_share")], (0, 0))
        self.assertNotIn(("compression", "live_photo_gb_saved"), found)          # the query gave none: no row, not a zero
        self.assertEqual(found[("monetization", "onboarding_buyers_share")], (3, 25))
        self.assertEqual({(r["week_start"], r["source"], r["captured"]) for r in rows}, {("2026-11-02", "bigquery", "2026-11-10")})
        self.assertEqual(set(rows[0]), set(telemetry.TELEMETRY_COLS))

    def test_an_empty_answer_gives_no_rows(self):
        self.assertEqual(telemetry.telemetry_rows({"funnel": {}, "compression": [], "monetization": []}, WEEK, "x"), [])


class Queries(unittest.TestCase):
    def run_with(self, **window):
        asked = []
        with mock.patch.object(telemetry, "run_bq_query", side_effect=lambda project, sql: asked.append(sql) or []):
            data = telemetry.analyze_telemetry("proj", "data", **window)
        return asked, data

    def test_a_week_is_asked_for_by_its_own_bounds(self):
        asked, data = self.run_with(start=WEEK, end=dt.date(2026, 11, 8))
        self.assertEqual(len(asked), 4)                                           # overview, funnel, compression, monetization
        for sql in asked:
            self.assertIn('_TABLE_SUFFIX BETWEEN "20261102" AND "20261108"', sql)
            self.assertNotIn("CURRENT_DATE", sql)
        self.assertEqual(sorted(data), ["activity", "compression", "funnel", "monetization", "overview", "retention"])

    def test_the_old_window_still_works(self):
        asked, _ = self.run_with(days=30)
        self.assertEqual(len(asked), 6)
        self.assertIn("CURRENT_DATE", asked[0])


class StoreWeeks(unittest.TestCase):
    def test_closed_weeks_not_yet_stored_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "metrics" / "telemetry.csv").unlink(missing_ok=True)
            asked = []

            def fake(project, dataset, days=0, start=None, end=None):
                asked.append((start.isoformat(), end.isoformat()))
                return DATA

            today = dt.date(2026, 11, 14)
            with contextlib.redirect_stdout(io.StringIO()):
                first = telemetry.store_weeks(store, "proj", "data", today, limit=2, run=fake)
                second = telemetry.store_weeks(store, "proj", "data", today, limit=2, run=fake)
            self.assertEqual(first, ["2026-11-02", "2026-10-26"])                  # the week of 11-09 is still open
            self.assertEqual(second, ["2026-10-19", "2026-10-12"])
            self.assertEqual(asked[0], ("2026-11-02", "2026-11-08"))
            self.assertEqual(len({r["week_start"] for r in read_csv(store / "metrics" / "telemetry.csv")}), 4)

    def test_a_failed_week_stops_the_run_and_keeps_what_was_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            (store / "metrics" / "telemetry.csv").unlink(missing_ok=True)
            calls = []

            def fake(project, dataset, days=0, start=None, end=None):
                calls.append(start)
                if len(calls) == 2:
                    raise RuntimeError("quota")
                return DATA

            with contextlib.redirect_stdout(io.StringIO()) as said:
                stored = telemetry.store_weeks(store, "proj", "data", dt.date(2026, 11, 14), limit=5, run=fake)
            self.assertEqual(stored, ["2026-11-02"])
            self.assertIn("2026-10-26", said.getvalue())
            self.assertIn("quota", said.getvalue())


class Family(unittest.TestCase):
    def test_in_app_family(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = copy_store(tmp)
            path = store / "metrics" / "telemetry.csv"
            path.unlink(missing_ok=True)
            self.assertEqual(self.in_app(store)["unavailable"]["code"], "no_source")
            telemetry.append_week(path, telemetry.telemetry_rows(DATA, WEEK, "2026-11-10"))
            family = self.in_app(store)
            self.assertEqual((family["source"], family["fetched_at"]), ("bigquery", "2026-11-10"))
            figures = family["figures"]
            self.assertEqual(figures["funnel.first_open"], {"value": 40})
            self.assertEqual(figures["compression.video_completed_share"], {"value": 0.75, "numerator": 15, "denominator": 20})
            self.assertEqual(figures["compression.video_gb_saved"], {"value": 1.5})
            self.assertEqual(figures["compression.live_photo_completed_share"]["unavailable"]["code"], "no_data")
            self.assertEqual(self.in_app(store, "2026-10-26")["unavailable"]["code"], "no_data")   # stored, not that week
            catalog = contract.load_catalog()
            for name, obj in export.build_all(store, dt.date(2026, 11, 14))[0].items():
                self.assertEqual(contract.validate(name, contract.canonical(obj), catalog), [])

    def in_app(self, store, week="2026-11-02"):
        return export.build_all(store, dt.date(2026, 11, 14))[0][f"week/{week}.json"]["families"]["in_app"]


if __name__ == "__main__":
    unittest.main()
