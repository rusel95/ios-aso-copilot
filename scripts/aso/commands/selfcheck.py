"""The copilot's own self-check: run with `copilot.py --self-check`."""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from aso.commands.base import DEFAULT_STORE, compact_asc_output, resolve_app_identity
from aso.commands.charts import fetch_category_chart, find_app_in_chart
from aso.commands.collect import cmd_ga, cmd_reviews, prepare_funnel_pull
from aso.commands.cycle import cmd_cycle, cycle_stage_table
from aso.commands.google import cmd_google_batch, google_ratio
from aso.commands.keywords import probe_localization_vacuum
from aso.commands.status import cmd_info

import contextlib

from aso.commands import ads_actions, ads_read, base, campaign, charts, collect, cycle, google, keywords, status

COMMAND_MODULES = (base, charts, status, keywords, ads_read, ads_actions, collect, google, cycle, campaign)


@contextlib.contextmanager
def everywhere(name, **mock_args):
    """Replace a shared helper in every command module that imported it, with one mock, as when they were one file."""
    from unittest.mock import Mock, patch
    mock = Mock(**mock_args)
    with contextlib.ExitStack() as stack:
        for module in COMMAND_MODULES:
            if hasattr(module, name):
                stack.enter_context(patch.object(module, name, mock))
        yield mock


def self_check():
    import contextlib
    import io
    from unittest.mock import patch
    from copilot import build_parser

    with tempfile.TemporaryDirectory() as tmp:
        store = Path(tmp) / "marketing"
        store.mkdir()
        try:
            resolve_app_identity(store)
            raise AssertionError("missing config must fail")
        except SystemExit as exc:
            assert "config.md" in str(exc)

        config = store / "config.md"
        config.write_text("**App ID**: TODO\n**Version**: TODO\n", encoding="utf-8")
        try:
            resolve_app_identity(store)
            raise AssertionError("template identity must fail")
        except SystemExit as exc:
            assert "refusing to guess" in str(exc)

        config.write_text("**App ID**: 1234567890\n**Version**: 1.2.3\n", encoding="utf-8")
        app = resolve_app_identity(store)
        assert app == {"app_id": "1234567890", "version": "1.2.3", "brand": Path(tmp).name,
                       "ga4_property_id": None, "rc_project_id": None, "ads_profile": None, "ads_account": None,
                       "ads_genres": [], "ads_topics": []}
        config.write_text("**App ID**: 1234567890\n**Version**: 1.2.3\n**GA4 Property ID**: 234567890\n**RevenueCat Project ID**: proj123\n**Apple Ads profile**: def\n**Apple Ads account**: 999\n",
                          encoding="utf-8")
        app = resolve_app_identity(store)
        assert app["ga4_property_id"] == "234567890" and app["rc_project_id"] == "proj123" and app["ads_profile"] == "def" and app["ads_account"] == "999"
        config.write_text("**App ID**: 1234567890\n**Version**: 1.2.3\n**GA4 Property ID**: 234567890\n**Apple Ads profile**: def\n**Apple Ads account**: 999\n",
                          encoding="utf-8")
        app = resolve_app_identity(store)
        review_payload = json.dumps({"data": [{"attributes": {"body": "do not emit this text"}}],
                                     "meta": {"paging": {"total": 1}}})
        review_summary = compact_asc_output(review_payload, "unreplied")
        assert review_summary == "1 unresponded reviews (ASC total; review text omitted)."
        assert "do not emit this text" not in review_summary

        pull_script = Path(tmp) / "pull_funnel.py"
        pull_script.write_text('APP_ID = "1234567890"\n', encoding="utf-8")
        with everywhere("run_cmd", return_value=(0, "--out DIR --raw-dir DIR", "")):
            pull1, raw1, err1 = prepare_funnel_pull(pull_script, store, app["app_id"])
            pull2, raw2, err2 = prepare_funnel_pull(pull_script, store, app["app_id"])
        assert pull1 and pull2 and not err1 and not err2
        temp_root = Path(tempfile.gettempdir()).resolve() / "ios-aso-copilot" / "funnel"
        assert raw1 != raw2 and raw1.parent == raw2.parent == temp_root
        assert raw1.name.startswith(f"{app['app_id']}-cycle-")
        assert pull1[-2:] == ["--raw-dir", str(raw1)]
        raw1.rmdir()
        raw2.rmdir()
        pull_script.write_text('APP_ID = "9876543210"\n', encoding="utf-8")
        with everywhere("run_cmd", side_effect=AssertionError("identity mismatch must stop before helper")):
            mismatch, _, reason = prepare_funnel_pull(pull_script, store, app["app_id"])
        assert mismatch is None and "does not match configured App ID" in reason
        pull_script.write_text('APP_ID = "1234567890"\n', encoding="utf-8")
        with everywhere("run_cmd", return_value=(0, "--out DIR", "")):
            unsafe, _, reason = prepare_funnel_pull(pull_script, store, app["app_id"])
        assert unsafe is None and "refusing its default path" in reason

        # one job: the stages run in order, so the canned answers below are handed out in the order written
        args = argparse.Namespace(store=str(store), skip_pull=True, skip_ga=False, jobs=1)

        def cycle_result(responses):
            # the pass also asks the public store lookup for the live release, and Apple Ads for its results by week
            # (this store names an Apple Ads account and no RevenueCat project); a self-check reaches no network
            import pull_revenuecat
            from unittest.mock import patch
            # the reviews stage reads the listing once more, for its total: its answer follows the unresponded one
            responses = responses[:3] + [(0, json.dumps({"data": [], "meta": {"paging": {"total": 0}}}), "")] + responses[3:]
            with everywhere("run_cmd", side_effect=responses), everywhere("fetch_lookup", return_value=None), \
                    patch.object(pull_revenuecat, "collect_ads", return_value=([], None)):
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    code = cmd_cycle(args)
            return code, output.getvalue()

        version_output = json.dumps({"data": [{"attributes": {"versionString": "1.2.3",
                                                                  "appStoreState": "READY_FOR_SALE",
                                                                  "appVersionState": "READY_FOR_DISTRIBUTION"}}]})
        ratings_output = json.dumps({"averageRating": 4.5, "totalCount": 12, "countryCount": 2,
                                     "histogram": {"5": 10, "4": 2}})
        ratings_by_country = json.dumps({"appId": "1234567890", "averageRating": 5,
                                         "totalCount": 4, "countryCount": 2,
                                         "byCountry": [{"country": "UA", "averageRating": 5,
                                                        "ratingCount": 3},
                                                       {"country": "PL", "averageRating": 5,
                                                        "ratingCount": 1}]})
        summary = compact_asc_output(ratings_by_country, "ratings")
        assert "UA:3 @5/5" in summary and "PL:1 @5/5" in summary
        assert "star histogram unavailable" in summary
        reviews_output = json.dumps({"data": [], "meta": {"paging": {"total": 0}}})
        complete = [(0, version_output, ""), (0, ratings_output, ""),
                    (0, reviews_output, ""), (0, "GA metrics\n", ""), (0, "radar\n", ""), (0, "ledger\n", "")]
        assert cycle_result(complete)[0] == 0
        ga_partial, out_ga = cycle_result([(0, version_output, ""), (0, ratings_output, ""), (0, reviews_output, ""),
                                           (2, "GA table\n⚠️ Збір частковий: Firebase CLI\n", ""),
                                           (0, "radar\n", ""), (0, "ledger\n", "")])
        assert ga_partial == 2 and "GA table" in out_ga and "GA4 pull partial (exit 2)" in out_ga
        assert any(l.startswith("4 ") and " partial " in l for l in out_ga.rstrip().splitlines()[-8:])
        partial, output = cycle_result([(0, version_output, ""), (0, ratings_output, ""),
                                        (0, "", ""), (0, "GA metrics\n", ""), (0, "radar\n", ""), (0, "ledger\n", "")])
        assert partial == 2 and "whether there are zero rows is unknown" in output
        # the stage table is the LAST thing printed, one row per stage, and names the partial one
        tail = output.rstrip().splitlines()
        assert "STAGE SUMMARY" in output and len([l for l in tail[-8:] if l[:1] in "12345678"]) == 8, tail[-10:]
        assert any(l.startswith("2 ") and " partial " in l for l in tail[-8:]), tail[-8:]
        sample = "\n▶ [1/7] A\n  fine\n\n▶ [3/7] Funnel\n  ⚠️ pull_funnel.py exited with code 1; Cause: 429\n\n▶ [4/7] GA\n  (GA4 pull explicitly skipped)\n"
        assert [r[2] for r in cycle_stage_table(sample)] == ["ok", "failed", "skipped"]
        empty_ga, output = cycle_result([(0, version_output, ""), (0, ratings_output, ""),
                                         (0, reviews_output, ""), (0, "", ""), (0, "radar\n", ""), (0, "ledger\n", "")])
        assert empty_ga == 2 and "GA4 returned no output" in output
        failed, _ = cycle_result([(1, "", "ASC unavailable"), (0, ratings_output, ""),
                                  (0, reviews_output, ""), (0, "GA metrics\n", ""), (0, "radar\n", ""), (0, "ledger\n", "")])
        assert failed == 2
        radar_failed, output = cycle_result([(0, version_output, ""), (0, ratings_output, ""),
                                             (0, reviews_output, ""), (0, "GA metrics\n", ""),
                                             (2, "⚠️ jp: exit 1: boom\n", ""), (0, "ledger\n", "")])
        assert radar_failed == 2 and "Radar pull incomplete" in output and "jp: exit 1: boom" in output

        ga_args = argparse.Namespace(store=str(store), property_id=None, days=14, credentials=None,
                                     realtime=False, include_debug=False, export_csv=False)
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            assert cmd_ga(ga_args) == 0
            command = run.call_args.args[0]
            assert command[command.index("--property-id") + 1] == "234567890"

        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 7)):
            assert cmd_reviews(argparse.Namespace(store=str(store), action="ratings")) == 7

        # Test probe_localization_vacuum with mocked iTunes search response
        mock_itunes_resp = json.dumps({
            "results": [
                {"trackName": "Video Compressor", "artistName": "Developer A", "userRatingCount": 50, "averageUserRating": 4.5, "price": 0.0, "bundleId": "com.a"},
                {"trackName": "Photo Cleaner", "artistName": "Developer B", "userRatingCount": 10, "averageUserRating": 4.0, "price": 0.0, "bundleId": "com.b"}
            ]
        }).encode("utf-8")
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.return_value.__enter__.return_value.read.return_value = mock_itunes_resp
            vdata, verr = probe_localization_vacuum("kompresor wideo", "pl", limit=5)
            assert not verr and vdata["verdict"] == "VACUUM_HIGH"
            assert vdata["localized_in_top5"] == 0
            assert vdata["results_count"] == 2

        # Test category charts parser & functions
        mock_chart_resp = json.dumps({
            "feed": {
                "entry": [
                    {"id": {"attributes": {"im:id": "111"}}, "im:name": {"label": "Other App"}, "im:artist": {"label": "Dev A"}, "category": {"attributes": {"label": "Utilities"}}},
                    {"id": {"attributes": {"im:id": "1234567890"}}, "im:name": {"label": "Compresso"}, "im:artist": {"label": "Dev B"}, "category": {"attributes": {"label": "Utilities"}}}
                ]
            }
        }).encode("utf-8")
        with patch("urllib.request.urlopen") as mock_url:
            mock_url.return_value.__enter__.return_value.read.return_value = mock_chart_resp
            c_apps, c_err = fetch_category_chart("ua", 6002, limit=10)
            assert not c_err and len(c_apps) == 2
            c_match = find_app_in_chart(c_apps, "1234567890", "Compresso")
            assert c_match and c_match["rank"] == 2

        # Test cmd_info with mock store and mock run_cmd
        info_args = argparse.Namespace(store=str(store), json=True, debug=False, info=False, quiet=False)
        with everywhere("run_cmd", return_value=(0, "mock", "")):
            assert cmd_info(info_args) == 0

        parser = build_parser()
        assert parser.parse_args(["--store", "/a", "cycle"]).store == "/a"
        assert parser.parse_args(["cycle", "--store", "/b"]).store == "/b"
        assert parser.parse_args(["radar", "--store", "/c", "pull"]).store == "/c"
        assert parser.parse_args(["status"]).store == str(DEFAULT_STORE)
        assert parser.parse_args(["info", "--debug"]).debug is True
        assert parser.parse_args(["--json", "info"]).json is True
        assert parser.parse_args(["keywords", "vacuum", "-c", "pl", "-t", "kompresor"]).keywords_action == "vacuum"
        assert parser.parse_args(["ads", "campaigns", "--status", "ENABLED"]).ads_action == "campaigns"
        assert parser.parse_args(["charts", "--country", "ua"]).command == "charts"

        # google batch: unsupported numbers are n/a, not invented or zero
        assert google_ratio(40.0, 8.0) == 500.0 and google_ratio(0.0, 8.0) == 0.0
        assert google_ratio(40.0, 0.0) is None and google_ratio(40.0, None) is None

        class _Series:
            def __init__(self, values):
                self.values = values

            def mean(self):
                return sum(self.values) / len(self.values)

        class _Frame(dict):  # just enough of a DataFrame for the batch loop
            @property
            def empty(self):
                return not self

            def __getitem__(self, col):
                return _Series(dict.__getitem__(self, col))

        def batch_json(frames, anchor="a", terms="b,c"):
            class FakeReq:
                def __init__(self, **kwargs):
                    pass

                def build_payload(self, *a, **kw):
                    pass

                def interest_over_time(self):
                    return frames.pop(0)

            batch_args = argparse.Namespace(anchor=anchor, terms=terms, file=None, country="US",
                                            timeframe="today 12-m", delay=0, json=True)
            with patch("aso.commands.google._trend_req", return_value=(FakeReq, None)):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    assert cmd_google_batch(batch_args) == 0
            return json.loads(out.getvalue())

        solid = batch_json([_Frame({"a": [20, 20], "b": [40, 40], "c": [0, 0]})])
        assert solid["scores"] == {"a": 100.0, "b": 200.0, "c": 0.0} and not solid["warnings"]
        assert solid["notes"] == {"c": "below Trends' floor"}
        weak = batch_json([_Frame({"a": [4, 4], "b": [100, 100], "c": [8, 8]})])
        assert weak["scores"]["b"] == 2500.0 and "ORDER" in weak["warnings"][0] and "'c'" in weak["warnings"][0]
        throttled = batch_json([_Frame()])
        assert throttled["scores"] == {"a": 100.0} and throttled["unavailable"] == ["b", "c"]
        dead_anchor = batch_json([_Frame({"a": [0, 0], "b": [5, 5], "c": [5, 5]})])
        assert dead_anchor["unavailable"] == ["b", "c"] and dead_anchor["notes"]["b"] == "anchor read 0"
    print("OK: app identity, safe funnel paths, CLI complete/partial/failure semantics, google batch honesty")
