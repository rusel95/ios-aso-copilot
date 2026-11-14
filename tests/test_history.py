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
