"""The dashboard data contract: what a data file must look like before the page is allowed to read it."""
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.helpers import ROOT  # noqa: E402

from aso.dashboard import contract  # noqa: E402

WEEK = {
    "schema": "aso-copilot/dashboard-data@1",
    "as_of": "2026-11-14",
    "period": {"kind": "week", "id": "2026-11-02", "start": "2026-11-02", "end": "2026-11-08"},
    "families": {
        "store_funnel": {
            "source": "asc-analytics", "fetched_at": "2026-11-10",
            "figures": {
                "impressions": {"value": 1500, "by_market": {"ua": 600, "us": 900}},
                "page_cvr": {"value": 0.4, "numerator": 64, "denominator": 160},
                "first_downloads": {"unavailable": {"code": "no_data", "reason": "The report has no download rows."}},
            },
        },
        "in_app": {"unavailable": {"code": "no_source", "reason": "Nothing stores it yet."}},
    },
}
SNAPSHOT = {
    "schema": "aso-copilot/dashboard-data@1",
    "as_of": "2026-11-14",
    "period": {"kind": "snapshot", "id": "2026-11-03", "start": "2026-11-03", "end": "2026-11-03"},
    "families": {
        "demand": {
            "source": "asc-ads-insights", "fetched_at": "2026-11-03",
            "measured": {"start": "2026-10-25", "end": "2026-10-31"},
            "rows": [{"market": "us", "genre": "WEATHER", "term": "tide times", "popularity_100": 41}],
            "cuts": [{"market": "ua", "genre": "", "listed": 0, "min_popularity_100": None}],
        },
    },
}


def problems(obj, path="week/2026-11-02.json", text=None):
    return contract.validate(path, contract.canonical(obj) if text is None else text, contract.load_catalog())


def changed(base, edit):
    obj = copy.deepcopy(base)
    edit(obj)
    return obj


class Canonical(unittest.TestCase):
    def test_canonical_is_stable(self):
        a = contract.canonical({"b": 1, "a": {"y": "п’ятниця", "x": None}})
        b = contract.canonical({"a": {"x": None, "y": "п’ятниця"}, "b": 1})
        self.assertEqual(a, b)
        self.assertIn("п’ятниця", a)                     # readable, not \\u escapes
        self.assertTrue(a.endswith("}\n") and not a.endswith("\n\n"))

    def test_the_catalog_file_is_canonical(self):
        path = ROOT / "assets" / "dashboard" / "catalog.json"
        text = path.read_text(encoding="utf-8")
        self.assertEqual(text, contract.canonical(json.loads(text)))


class Catalog(unittest.TestCase):
    def test_every_family_and_figure_of_the_design_is_there(self):
        families = contract.load_catalog()["families"]
        expected = {
            "store_funnel": ("week", {"impressions", "page_views", "first_downloads", "view_rate", "page_cvr",
                                      "impression_cvr"}),
            "lifecycle": ("week", {"optin_installs", "optin_deletions", "deleted_within_1d", "deletions_per_100"}),
            "money": ("week", {"proceeds_usd", "ad_spend_usd", "net_cashflow_usd", "transactions", "new_trials"}),
            "ads": ("week", {"spend_usd", "impressions", "taps", "installs", "ttr", "cpi_usd"}),
            "in_app": ("week", set()),
            "ranks": ("snapshot", {"tracked_keys", "keys_read", "top10", "top30", "top100", "top200", "beyond",
                                   "no_results", "errors", "share_top10", "share_top30"}),
            "coverage": ("snapshot", {"paired_keys", "unmeasurable_keys", "failed_requests", "observations"}),
            "subscriptions": ("snapshot", {"active_subscriptions", "active_trials", "mrr_usd", "revenue_28d_usd",
                                           "new_customers_28d", "active_users_28d"}),
            "ratings": ("snapshot", {"ratings_count", "rating_average", "reviews", "reviews_unanswered"}),
            "demand": ("snapshot", set()),
            "impression_share": ("snapshot", set()),
            "charts": ("snapshot", set()),
        }
        self.assertEqual(set(families), set(expected))
        for name, (kind, figures) in expected.items():
            with self.subTest(family=name):
                self.assertEqual(families[name]["kind"], kind)
                self.assertEqual(set(families[name]["figures"]), figures)
        self.assertTrue(families["in_app"]["open"])
        self.assertEqual(families["demand"]["rows"], {"rows": ["market", "genre", "term", "popularity_100"],
                                                      "cuts": ["market", "genre", "listed", "min_popularity_100"]})

    def test_every_figure_says_what_it_is(self):
        for name, family in contract.load_catalog()["families"].items():
            self.assertTrue(family["title"], name)
            for key, figure in family["figures"].items():
                with self.subTest(figure=f"{name}.{key}"):
                    self.assertTrue(figure["title"] and figure["unit"] and len(figure["definition"]) > 20)


class Validate(unittest.TestCase):
    def test_valid_week_file_passes(self):
        self.assertEqual(problems(WEEK), [])

    def test_valid_snapshot_with_rows_passes(self):
        self.assertEqual(problems(SNAPSHOT, "snapshot/2026-11-03.json"), [])

    def test_unknown_figure_key_fails(self):
        bad = changed(WEEK, lambda o: o["families"]["store_funnel"]["figures"].update(taps={"value": 1}))
        self.assertTrue(any("store_funnel.taps" in p for p in problems(bad)), problems(bad))

    def test_unknown_family_fails(self):
        bad = changed(WEEK, lambda o: o["families"].update(weather={"unavailable": {"code": "no_data", "reason": "x"}}))
        self.assertTrue(any("weather" in p for p in problems(bad)))

    def test_a_family_of_the_other_kind_fails(self):
        bad = changed(WEEK, lambda o: o["families"].update(ranks={"unavailable": {"code": "no_data", "reason": "x"}}))
        self.assertTrue(any("ranks" in p and "snapshot" in p for p in problems(bad)), problems(bad))

    def test_non_canonical_bytes_fail(self):
        text = json.dumps(WEEK, ensure_ascii=False)        # valid JSON, one line, keys unsorted
        self.assertTrue(any("canonical" in p for p in problems(WEEK, text=text)))

    def test_unknown_code_fails(self):
        bad = changed(WEEK, lambda o: o["families"]["in_app"]["unavailable"].update(code="missing"))
        self.assertTrue(any("missing" in p for p in problems(bad)))

    def test_a_missing_figure_needs_a_reason(self):
        bad = changed(WEEK, lambda o: o["families"]["in_app"]["unavailable"].update(reason=""))
        self.assertTrue(any("reason" in p for p in problems(bad)))

    def test_a_figure_is_a_number_or_unavailable_never_both_never_neither(self):
        both = changed(WEEK, lambda o: o["families"]["store_funnel"]["figures"]["first_downloads"].update(value=3))
        neither = changed(WEEK, lambda o: o["families"]["store_funnel"]["figures"].update(page_views={}))
        text = changed(WEEK, lambda o: o["families"]["store_funnel"]["figures"]["impressions"].update(value="1500"))
        flag = changed(WEEK, lambda o: o["families"]["store_funnel"]["figures"]["impressions"].update(value=True))
        for name, bad in (("both", both), ("neither", neither), ("text", text), ("flag", flag)):
            with self.subTest(case=name):
                self.assertTrue(problems(bad), name)

    def test_path_must_match_period(self):
        self.assertTrue(any("path" in p for p in problems(WEEK, "week/2026-10-26.json")))
        self.assertTrue(any("path" in p for p in problems(WEEK, "snapshot/2026-11-02.json")))

    def test_week_must_start_on_monday(self):
        bad = changed(WEEK, lambda o: o["period"].update(id="2026-11-03", start="2026-11-03", end="2026-11-09"))
        self.assertTrue(any("Monday" in p for p in problems(bad, "week/2026-11-03.json")))

    def test_a_week_is_seven_days(self):
        bad = changed(WEEK, lambda o: o["period"].update(end="2026-11-14"))
        self.assertTrue(any("end" in p for p in problems(bad)))

    def test_open_family_accepts_any_key(self):
        ok = changed(WEEK, lambda o: o["families"].update(in_app={
            "source": "bigquery", "fetched_at": "2026-11-10",
            "figures": {"funnel.first_open": {"value": 40}, "compression.video_ok": {"value": 12}}}))
        self.assertEqual(problems(ok), [])
        bad = changed(ok, lambda o: o["families"]["in_app"]["figures"].update({"Not A Key": {"value": 1}}))
        self.assertTrue(problems(bad))

    def test_rows_hold_exactly_the_declared_columns(self):
        bad = changed(SNAPSHOT, lambda o: o["families"]["demand"]["rows"][0].update(extra=1))
        self.assertTrue(any("demand" in p for p in problems(bad, "snapshot/2026-11-03.json")))

    def test_a_family_names_its_source_once(self):
        bad = changed(WEEK, lambda o: o["families"]["store_funnel"].pop("source"))
        self.assertTrue(any("source" in p for p in problems(bad)))

    def test_not_json_and_not_a_data_path(self):
        self.assertTrue(problems(WEEK, text="{not json"))
        self.assertTrue(any("not a dashboard data file" in p for p in problems(WEEK, "notes/readme.json")))


if __name__ == "__main__":
    unittest.main()
