#!/usr/bin/env python3
"""Unified CLI for iOS ASO Copilot (ios-marketing-ops).

Consolidates multi-step marketing operations into a single entrypoint:
  - copilot cycle: consolidated read/pull pass (versions, reviews, funnel, GA4, ledger)
  - copilot status: quick snapshot of active versions, hypotheses and ratings
  - copilot reviews: check rating histograms and unreplied customer reviews
  - copilot funnel: pull and summarize ASC analytics
  - copilot ga: pull in-app GA4 / Firebase telemetry
  - copilot ledger: delegate to ledger.py (report, refresh, draft, ingest)
  - copilot radar: delegate to radar.py (Apple search popularity, impression share, keyword report join)
"""

import argparse
import ast
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STORE = Path.cwd() / "marketing"

# Ensure scripts dir is on sys.path for internal imports
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

# Logging configuration
LOG_LEVEL = 1  # 0=DEBUG, 1=INFO, 2=WARN, 3=ERROR

def set_log_level(debug=False, info=False, quiet=False):
    global LOG_LEVEL
    if debug:
        LOG_LEVEL = 0
    elif quiet:
        LOG_LEVEL = 2
    elif info:
        LOG_LEVEL = 1
    else:
        LOG_LEVEL = 1

def log_debug(msg):
    if LOG_LEVEL <= 0:
        print(f"[DEBUG] {msg}", file=sys.stderr)

def log_info(msg):
    if LOG_LEVEL <= 1:
        print(f"[INFO] {msg}", file=sys.stderr)

def log_warn(msg):
    if LOG_LEVEL <= 2:
        print(f"[WARN] ⚠️ {msg}", file=sys.stderr)

def log_error(msg):
    if LOG_LEVEL <= 3:
        print(f"[ERROR] 🛑 {msg}", file=sys.stderr)



def resolve_app_identity(store: Path):
    """Read App ID, version, brand tokens, and Apple Ads settings from config.md."""
    config_file = store / "config.md"
    if not config_file.is_file():
        raise SystemExit(f"Missing app identity: create {config_file} from assets/store-template/config.md.")

    values = {}
    for line in config_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        for label, key in (("**App ID**:", "app_id"), ("**Version**:", "version"),
                           ("**Brand tokens**:", "brand"), ("**GA4 Property ID**:", "ga4_property_id"),
                           ("**Firebase Property ID**:", "ga4_property_id"),
                           ("**Apple Ads profile**:", "ads_profile"),
                           ("**Apple Ads account**:", "ads_account"),
                           ("**Apple Ads genres**:", "ads_genres"),
                           ("**Apple Ads topic words**:", "ads_topics")):
            if line.startswith(label):
                values[key] = line.split(":", 1)[1].strip()

    app_id = (values.get("app_id") or "").split(maxsplit=1)[0] if values.get("app_id") else ""
    version = (values.get("version") or "").split(maxsplit=1)[0] if values.get("version") else ""
    if not app_id.isdigit() or not version or version.upper() == "TODO":
        raise SystemExit(f"Set a numeric **App ID** and working **Version** in {config_file}; refusing to guess.")
    property_parts = (values.get("ga4_property_id") or "").split(maxsplit=1)
    property_value = property_parts[0] if property_parts else ""
    if property_value and property_value.upper() != "TODO" and not property_value.isdigit():
        raise SystemExit(f"Set a numeric **GA4 Property ID** in {config_file}; refusing to guess.")

    ads_profile = values.get("ads_profile")
    if ads_profile and (ads_profile.upper() == "TODO" or ads_profile.upper().startswith("TODO")):
        ads_profile = None
    ads_account = values.get("ads_account")
    if ads_account and (ads_account.upper() == "TODO" or ads_account.upper().startswith("TODO")):
        ads_account = None

    genres = [g.strip().upper() for g in (values.get("ads_genres") or "").split(",") if g.strip() and not g.strip().upper().startswith("TODO")]
    topics = [t.strip().casefold() for t in (values.get("ads_topics") or "").split(",") if t.strip() and not t.strip().upper().startswith("TODO")]

    return {
        "app_id": app_id,
        "version": version,
        "brand": values.get("brand") or store.parent.name,
        "ga4_property_id": property_value if property_value.isdigit() else None,
        "ads_profile": ads_profile,
        "ads_account": ads_account,
        "ads_genres": genres,
        "ads_topics": topics,
    }


def declared_funnel_app_id(pull_script):
    """Read the helper's literal APP_ID without executing it; unknown identity fails closed."""
    try:
        tree = ast.parse(Path(pull_script).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return None
    values = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "APP_ID" for target in node.targets
        ):
            try:
                values.append(ast.literal_eval(node.value))
            except (ValueError, TypeError):
                values.append(None)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "APP_ID":
            try:
                values.append(ast.literal_eval(node.value))
            except (ValueError, TypeError):
                values.append(None)
    return values[0] if len(values) == 1 and isinstance(values[0], str) and values[0].isdigit() else None


def self_check():
    import contextlib
    import io
    from unittest.mock import patch

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
                       "ga4_property_id": None, "ads_profile": None, "ads_account": None,
                       "ads_genres": [], "ads_topics": []}
        config.write_text("**App ID**: 1234567890\n**Version**: 1.2.3\n**GA4 Property ID**: 234567890\n**Apple Ads profile**: def\n**Apple Ads account**: 999\n",
                          encoding="utf-8")
        app = resolve_app_identity(store)
        assert app["ga4_property_id"] == "234567890" and app["ads_profile"] == "def" and app["ads_account"] == "999"
        review_payload = json.dumps({"data": [{"attributes": {"body": "do not emit this text"}}],
                                     "meta": {"paging": {"total": 1}}})
        review_summary = compact_asc_output(review_payload, "unreplied")
        assert review_summary == "1 unresponded reviews (ASC total; review text omitted)."
        assert "do not emit this text" not in review_summary

        pull_script = Path(tmp) / "pull_funnel.py"
        pull_script.write_text('APP_ID = "1234567890"\n', encoding="utf-8")
        with patch(f"{__name__}.run_cmd", return_value=(0, "--out DIR --raw-dir DIR", "")):
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
        with patch(f"{__name__}.run_cmd", side_effect=AssertionError("identity mismatch must stop before helper")):
            mismatch, _, reason = prepare_funnel_pull(pull_script, store, app["app_id"])
        assert mismatch is None and "does not match configured App ID" in reason
        pull_script.write_text('APP_ID = "1234567890"\n', encoding="utf-8")
        with patch(f"{__name__}.run_cmd", return_value=(0, "--out DIR", "")):
            unsafe, _, reason = prepare_funnel_pull(pull_script, store, app["app_id"])
        assert unsafe is None and "refusing its default path" in reason

        args = argparse.Namespace(store=str(store), skip_pull=True, skip_ga=False)

        def cycle_result(responses):
            with patch(f"{__name__}.run_cmd", side_effect=responses):
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
        assert any(l.startswith("4 ") and " partial " in l for l in out_ga.rstrip().splitlines()[-6:])
        partial, output = cycle_result([(0, version_output, ""), (0, ratings_output, ""),
                                        (0, "", ""), (0, "GA metrics\n", ""), (0, "radar\n", ""), (0, "ledger\n", "")])
        assert partial == 2 and "whether there are zero rows is unknown" in output
        # the stage table is the LAST thing printed, one row per stage, and names the partial one
        tail = output.rstrip().splitlines()
        assert "STAGE SUMMARY" in output and len([l for l in tail[-6:] if l[:1] in "123456"]) == 6, tail[-8:]
        assert any(l.startswith("2 ") and " partial " in l for l in tail[-6:]), tail[-6:]
        sample = "\n▶ [1/6] A\n  fine\n\n▶ [3/6] Funnel\n  ⚠️ pull_funnel.py exited with code 1; Cause: 429\n\n▶ [4/6] GA\n  (GA4 pull explicitly skipped)\n"
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
        with patch(f"{__name__}.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            assert cmd_ga(ga_args) == 0
            command = run.call_args.args[0]
            assert command[command.index("--property-id") + 1] == "234567890"

        with patch(f"{__name__}.subprocess.run", return_value=subprocess.CompletedProcess([], 7)):
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

        # Test cmd_info with mock store and mock run_cmd
        info_args = argparse.Namespace(store=str(store), json=True, debug=False, info=False, quiet=False)
        with patch(f"{__name__}.run_cmd", return_value=(0, "mock", "")):
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

            batch_args = argparse.Namespace(anchor=anchor, terms=terms, file=None, country="UA",
                                            timeframe="today 12-m", delay=0, json=True)
            with patch(f"{__name__}._trend_req", return_value=(FakeReq, None)):
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


def run_cmd(args, capture=True, check=False, input_text=None):
    """Run shell command with clean output capture and logging."""
    log_debug(f"run_cmd: {' '.join(str(a) for a in args)}")
    try:
        res = subprocess.run(args, capture_output=capture, text=True, check=check, input=input_text)
        log_debug(f"run_cmd [{args[0]}] exit code: {res.returncode}")
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        log_error(f"Command not found: {args[0]}")
        return -1, "", f"Command not found: {args[0]}"
    except Exception as e:
        log_error(f"Command execution error: {e}")
        return -1, "", str(e)


def compact_asc_output(output, kind):
    """Return a bounded summary of structured ASC data without review bodies or raw links."""
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    if kind == "versions" and isinstance(payload.get("data"), list):
        rows = payload["data"]
        if not rows:
            return "ASC reports no versions."
        labels = []
        for row in rows[:5]:
            attributes = (row.get("attributes") or {}) if isinstance(row, dict) else {}
            if not isinstance(attributes, dict):
                attributes = {}
            labels.append(f"{attributes.get('versionString', 'version unknown')}: "
                          f"{attributes.get('appStoreState', 'state unknown')} / "
                          f"{attributes.get('appVersionState', 'build state unknown')}")
        suffix = f"; {len(rows) - 5} more omitted" if len(rows) > 5 else ""
        return f"{len(rows)} versions; " + "; ".join(labels) + suffix
    if kind == "ratings" and "averageRating" in payload and "totalCount" in payload:
        countries = payload.get("byCountry")
        histogram = payload.get("histogram")
        if isinstance(histogram, dict):
            counts = ", ".join(f"{star}:{histogram.get(str(star), histogram.get(star, '?'))}"
                                for star in range(1, 6))
            stars = f"stars {counts}"
        else:
            stars = "star histogram unavailable from ASC response"
        country_summary = ""
        if isinstance(countries, list):
            entries = [f"{row.get('country', '?')}:{row.get('ratingCount', '?')} @"
                       f"{row.get('averageRating', '?')}/5" for row in countries if isinstance(row, dict)]
            country_summary = "; " + ", ".join(entries) if entries else ""
        country_count = payload.get("countryCount")
        if country_count is None:
            country_count = len(countries) if isinstance(countries, list) else "unknown"
        return (f"Average {payload['averageRating']}/5; {payload['totalCount']} ratings; "
                f"{country_count} storefronts{country_summary}; {stars}")
    if kind == "unreplied" and isinstance(payload.get("data"), list):
        meta = payload.get("meta")
        paging = meta.get("paging") if isinstance(meta, dict) else None
        total = paging.get("total") if isinstance(paging, dict) else None
        if isinstance(total, int):
            return f"{total} unresponded reviews (ASC total; review text omitted)."
        return f"{len(payload['data'])} unresponded reviews returned; total unknown; review text omitted."
    return None


def prepare_funnel_pull(pull_script, store, app_id):
    """Build a safe pull only after verifying the helper identity and raw directory option."""
    store = Path(store).resolve()
    helper_app_id = declared_funnel_app_id(pull_script)
    if helper_app_id != app_id:
        return None, None, (f"Funnel helper declares App ID {helper_app_id or '(unverified)'}, which does not match "
                            f"configured App ID {app_id}; refusing the pull.")
    rc, help_text, err = run_cmd([sys.executable, str(pull_script), "--help"])
    if rc != 0 or "--raw-dir" not in help_text:
        detail = (err.strip() or f"exit {rc}") if rc != 0 else "--raw-dir is unsupported"
        return None, None, f"Funnel pull has no verified safe raw directory option ({detail}); refusing its default path."

    run_root = Path(tempfile.gettempdir()).resolve() / "ios-aso-copilot" / "funnel"
    run_root.mkdir(parents=True, exist_ok=True)
    raw_dir = Path(tempfile.mkdtemp(prefix=f"{app_id}-cycle-", dir=run_root)).resolve()
    command = [sys.executable, str(pull_script), "--out", str(store / "metrics"),
               "--raw-dir", str(raw_dir)]
    return command, raw_dir, ""


def cmd_status(args):
    """Quick high-level snapshot."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    partial = False

    print(f"\n📱 {app['brand']} Marketing Status · Store: {store}")
    print(f"App ID: {app['app_id']} · Working Version: {app['version']}\n")

    # 1. Version check via asc
    print("--- 1. App Store Versions ---")
    rc, out, err = run_cmd(["asc", "versions", "list", "--app", app["app_id"], "--platform", "IOS"])
    if rc == 0 and out.strip():
        summary = compact_asc_output(out, "versions")
        if summary:
            print(summary)
        else:
            print("  ⚠️ ASC version output format is unknown; payload omitted.")
            partial = True
    elif rc == 0:
        print("  ⚠️ ASC version query returned no output.")
        partial = True
    else:
        print(f"  ⚠️ Could not query asc versions list: {err.strip() or f'exit {rc}'}")
        partial = True

    # 2. Ratings summary
    print("\n--- 2. App Store Ratings ---")
    rc, out, err = run_cmd(["asc", "reviews", "ratings", "--app", app["app_id"], "--all"])
    if rc == 0 and out.strip():
        summary = compact_asc_output(out, "ratings")
        if summary:
            print(summary)
        else:
            print("  ⚠️ ASC ratings output format is unknown; payload omitted.")
            partial = True
    elif rc == 0:
        print("  ⚠️ ASC ratings query returned no output.")
        partial = True
    else:
        print(f"  ⚠️ Could not query asc reviews ratings: {err.strip() or f'exit {rc}'}")
        partial = True

    # 3. Ledger summary
    ledger_py = SKILL_DIR / "scripts" / "ledger.py"
    if ledger_py.exists():
        print("\n--- 3. Hypothesis Ledger ---")
        rc, out, err = run_cmd([sys.executable, str(ledger_py), "--store", str(store), "report"])
        if rc == 0:
            if out.strip():
                for line in out.splitlines():
                    if line.startswith("## B ·") or line.startswith("| Market | Key |"):
                        break
                    print(line)
            else:
                print("  ⚠️ Ledger report returned no output.")
                partial = True
        else:
            print(f"  ⚠️ Ledger report failed: {err.strip() or f'exit {rc}'}")
            partial = True
    else:
        print(f"  ⚠️ Ledger report unavailable — {ledger_py} not found.")
        partial = True
    return 2 if partial else 0


def cmd_info(args):
    """Print complete diagnostic information about environment, app identity, Apple Ads, and store state."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)

    log_info(f"Gathering environment and app info for store: {store}")

    info_data = {
        "skill": {
            "name": "ios-aso-copilot",
            "version": "2.7.0",
            "path": str(SKILL_DIR),
        },
        "app": {
            "brand": app["brand"],
            "app_id": app["app_id"],
            "version": app["version"],
            "ga4_property_id": app["ga4_property_id"],
        },
        "ads": {
            "profile": app.get("ads_profile"),
            "account": app.get("ads_account"),
            "genres": app.get("ads_genres", []),
            "topics": app.get("ads_topics", []),
        },
        "store": {
            "path": str(store),
            "exists": store.exists(),
        },
        "system": {
            "python": sys.version.split()[0],
            "executable": sys.executable,
        }
    }

    rc, out, _ = run_cmd(["asc", "--version"])
    info_data["system"]["asc"] = out.strip() if rc == 0 else "not found or error"

    rc, out, _ = run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = out.strip() if rc == 0 else "unknown"
    rc, out, _ = run_cmd(["git", "rev-parse", "--short", "HEAD"])
    commit = out.strip() if rc == 0 else "unknown"
    info_data["system"]["git"] = {"branch": branch, "commit": commit}

    if store.exists():
        hyp_dir = store / "hypotheses"
        dec_dir = store / "decisions"
        rep_dir = store / "reports"
        met_dir = store / "metrics"
        info_data["store"]["hypotheses_count"] = len(list(hyp_dir.glob("*.md"))) if hyp_dir.exists() else 0
        info_data["store"]["decisions_count"] = len(list(dec_dir.glob("*.md"))) if dec_dir.exists() else 0
        info_data["store"]["reports_count"] = len(list(rep_dir.glob("*"))) if rep_dir.exists() else 0
        info_data["store"]["metrics_csvs"] = [p.name for p in met_dir.glob("*.csv")] if met_dir.exists() else []

    if getattr(args, "json", False):
        print(json.dumps(info_data, indent=2))
        return 0

    print("=================================================================")
    print(f"🚀 iOS ASO Copilot CLI v{info_data['skill']['version']}")
    print("=================================================================\n")
    print("📱 App Identity:")
    print(f"  Brand:             {app['brand']}")
    print(f"  App ID:            {app['app_id']}")
    print(f"  Working Version:   {app['version']}")
    print(f"  GA4 Property ID:   {app['ga4_property_id'] or '(none)'}")
    print()
    print("🎯 Apple Ads Context:")
    print(f"  Profile:           {app['ads_profile'] or '(not set)'}")
    print(f"  Account ID:        {app['ads_account'] or '(not set)'}")
    print(f"  Categories:        {', '.join(app['ads_genres']) if app['ads_genres'] else '(none)'}")
    print(f"  Topic Words:       {', '.join(app['ads_topics']) if app['ads_topics'] else '(none)'}")
    print()
    print(f"📁 Marketing Store:   {store}")
    if store.exists():
        print(f"  Hypotheses:        {info_data['store']['hypotheses_count']} files")
        print(f"  Decisions:         {info_data['store']['decisions_count']} files")
        print(f"  Metrics CSVs:      {', '.join(info_data['store']['metrics_csvs']) or '(none)'}")
    else:
        print(f"  ⚠️ Directory not found: {store}")
    print()
    print("⚙️  System & Tools:")
    print(f"  Python:            {info_data['system']['python']} ({info_data['system']['executable']})")
    print(f"  asc CLI:           {info_data['system']['asc']}")
    print(f"  Git:               {branch} ({commit})")
    print("=================================================================")
    return 0


def probe_localization_vacuum(term: str, country: str, limit: int = 25):
    """Probe iTunes Search API to detect localization vacuums (unlocalized competitor apps)."""
    log_debug(f"Probing localization vacuum for '{term}' in {country} (limit {limit})...")
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(term)}&country={country.lower()}&entity=software&limit={limit}"
    headers = {"User-Agent": "iTunes/12.0 (Macintosh)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        log_error(f"iTunes Search API request failed: {exc}")
        return None, str(exc)

    results = payload.get("results", [])
    if not results:
        return {
            "term": term,
            "country": country.upper(),
            "results_count": 0,
            "vacuum_score": 100,
            "verdict": "VACUUM_HIGH",
            "reason": "No apps found for this query in this storefront. Maximum opportunity.",
            "localized_in_top5": 0,
            "avg_top5_ratings": 0.0,
            "apps": []
        }, ""

    words = set(term.casefold().split())
    apps = []
    localized_title_count = 0
    ratings = []

    for i, item in enumerate(results, 1):
        title = item.get("trackName", "")
        seller = item.get("artistName") or item.get("sellerName", "")
        rating_count = int(item.get("userRatingCount", 0))
        avg_rating = float(item.get("averageUserRating", 0.0))
        price = item.get("price", 0.0)
        bundle_id = item.get("bundleId", "")

        title_words = set(title.casefold().split())
        has_word_match = bool(words & title_words)
        is_localized = has_word_match
        if is_localized:
            localized_title_count += 1
        ratings.append(rating_count)

        apps.append({
            "rank": i,
            "title": title,
            "developer": seller,
            "ratings_count": rating_count,
            "average_rating": avg_rating,
            "price": price,
            "bundle_id": bundle_id,
            "localized_title": is_localized
        })

    top5 = apps[:5]
    top5_ratings = [a["ratings_count"] for a in top5]
    avg_top5_ratings = sum(top5_ratings) / max(len(top5_ratings), 1)
    localized_in_top5 = sum(1 for a in top5 if a["localized_title"])

    loc_penalty = (localized_in_top5 / 5.0) * 50.0
    rating_penalty = min(avg_top5_ratings / 200.0, 1.0) * 50.0
    vacuum_score = max(0, min(100, int(100 - loc_penalty - rating_penalty)))

    if vacuum_score >= 70:
        verdict = "VACUUM_HIGH"
        reason = f"Top apps lack localized titles ({localized_in_top5}/5) and average only {avg_top5_ratings:.0f} ratings in {country.upper()}. High ASO & Exact Ads potential!"
    elif vacuum_score >= 40:
        verdict = "VACUUM_MODERATE"
        reason = f"Moderate competition: {localized_in_top5}/5 top apps have localized titles, avg ratings {avg_top5_ratings:.0f}. Exact keywords & metadata optimization viable."
    else:
        verdict = "COMPETITIVE"
        reason = f"Established local competitors dominate top positions ({localized_in_top5}/5 localized, avg ratings {avg_top5_ratings:.0f}). High bidding required."

    data = {
        "term": term,
        "country": country.upper(),
        "results_count": len(results),
        "vacuum_score": vacuum_score,
        "verdict": verdict,
        "reason": reason,
        "localized_in_top5": localized_in_top5,
        "avg_top5_ratings": avg_top5_ratings,
        "apps": apps
    }
    return data, ""


def cmd_keywords(args):
    """Manage keyword discovery, hints, localization vacuums, and filtering."""
    subaction = getattr(args, "keywords_action", None)
    if subaction == "hints":
        return cmd_keywords_hints(args)
    elif subaction == "vacuum":
        return cmd_keywords_vacuum(args)
    elif subaction == "popularity":
        return cmd_keywords_popularity(args)
    elif subaction == "competitors":
        return cmd_keywords_competitors(args)
    elif subaction == "filter":
        return cmd_keywords_filter(args)
    else:
        print("Unknown keywords subcommand. Use: hints, vacuum, popularity, competitors, filter")
        return 1


def cmd_keywords_hints(args):
    from harvest_keywords import fetch_hints
    storefront = (getattr(args, "country", None) or getattr(args, "storefront", None) or "us").lower()
    term = args.term
    log_debug(f"Fetching hints for '{term}' in storefront '{storefront}'")
    try:
        hints = fetch_hints(term, storefront)
    except Exception as e:
        log_error(f"Failed to fetch hints: {e}")
        print(f"Error fetching hints: {e}")
        return 1
    if getattr(args, "json", False):
        print(json.dumps({"term": term, "storefront": storefront, "hints": hints}, indent=2))
        return 0
    print(f"\n🔍 Apple Search Autocomplete Hints for '{term}' [{storefront.upper()}]:")
    if not hints:
        print("  (no suggestions returned)")
    for i, h in enumerate(hints, 1):
        print(f"  {i:2d}. {h}")
    return 0


def cmd_keywords_vacuum(args):
    term = args.term
    country = (args.country or "us").lower()
    limit = getattr(args, "limit", 20)
    log_info(f"Auditing localization vacuum for '{term}' in {country.upper()}...")
    data, err = probe_localization_vacuum(term, country, limit)
    if err or not data:
        print(f"Error checking localization vacuum: {err}")
        return 1
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2))
        return 0

    print("\n=================================================================")
    print(f"🌌 Localization Vacuum Audit: '{term}' in {country.upper()}")
    print("=================================================================\n")
    print(f"Verdict:           {data['verdict']} (Score: {data['vacuum_score']}/100)")
    print(f"Analysis:          {data['reason']}")
    print(f"Results Count:     {data['results_count']} apps analyzed")
    print(f"Localized in Top5: {data['localized_in_top5']}/5 apps")
    print(f"Avg Top5 Ratings:  {data['avg_top5_ratings']:.0f}")
    print("\nTop Ranking Apps in Search Index:")
    print(f"{'#':<3} {'Title':<42} {'Localized':<10} {'Ratings':<10} {'Developer'}")
    print("-" * 80)
    for app in data["apps"][:15]:
        loc_badge = "✓ Yes" if app["localized_title"] else "✗ No"
        title_str = (app["title"][:38] + "..") if len(app["title"]) > 40 else app["title"]
        dev_str = (app["developer"][:24] + "..") if len(app["developer"]) > 26 else app["developer"]
        print(f"{app['rank']:<3} {title_str:<42} {loc_badge:<10} {app['ratings_count']:<10} {dev_str}")
    print("=================================================================")
    return 0


def cmd_keywords_popularity(args):
    store = Path(args.store).resolve()
    cfg = resolve_app_identity(store)
    country = (args.country or "us").upper()
    terms = [t.strip() for t in args.terms.split(",")] if getattr(args, "terms", None) else []
    log_debug(f"Querying popularity for country={country}, terms={terms}")

    if terms:
        # A per-term question gets a per-term answer from the stored weekly radar. Apple lists only each
        # storefront's head, so most terms are "below the cut": unknown, not zero. Never fall through to
        # the whole-store report (it used to, silently ignoring --terms, when the market had no rows).
        from radar import demand_lookup, demand_label
        demand = demand_lookup(store)
        explain = {"—": "market never pulled — run `copilot.py radar pull`",
                   "no data": "Apple lists nothing for this storefront"}
        answers = [{"market": country.lower(), "term": term,
                    "popularity": demand_label(demand, country.lower(), term)} for term in terms]
        if getattr(args, "json", False):
            print(json.dumps(answers, indent=2, ensure_ascii=False))
            return 0
        print(f"\n📊 Apple Search Popularity [{country}] (stored weekly radar; relative 1-100, not searches):")
        for a_ in answers:
            label = a_["popularity"]
            note = explain.get(label) or ("not in Apple's published head: volume unknown, not zero"
                                          if label.startswith("below") else "")
            print(f"  {a_['term']}: {label}" + (f"  ({note})" if note else ""))
        return 0

    pop_csv = store / "metrics" / "popularity.csv"
    if pop_csv.is_file():
        import csv
        rows = list(csv.DictReader(pop_csv.open(encoding="utf-8")))
        matched = [r for r in rows if r.get("market", "").upper() == country]
        if terms:
            matched = [r for r in matched if r.get("term", "").casefold() in [t.casefold() for t in terms]]
        if getattr(args, "json", False):
            print(json.dumps(matched, indent=2))
            return 0
        if matched:
            print(f"\n📊 Stored Apple Search Popularity [{country}]:")
            for r in matched[:30]:
                print(f"  {r.get('term')}: popularity {r.get('popularity_100')}/100 (genre: {r.get('genre')}, rank: {r.get('rank_in_genre')})")
            return 0

    if not cfg.get("ads_account") or not cfg.get("ads_profile"):
        print(f"Apple Ads credentials not configured in {store / 'config.md'} and no stored metrics/popularity.csv found.")
        print("Set **Apple Ads profile**: and **Apple Ads account**: in config.md to query live popularity.")
        return 2

    radar_py = SKILL_DIR / "scripts" / "radar.py"
    rc, out, err = run_cmd([sys.executable, str(radar_py), "--store", str(store), "report"])
    print(out if rc == 0 else f"Error: {err}")
    return rc


def cmd_keywords_competitors(args):
    from harvest_keywords import fetch_competitors
    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()]
    country = (args.country or "us").lower()
    limit = getattr(args, "limit", 25)
    log_debug(f"Fetching competitors for seeds={seeds} in {country} (limit {limit})")
    try:
        comps = fetch_competitors(seeds, country, limit)
    except Exception as e:
        log_error(f"Failed to fetch competitors: {e}")
        print(f"Error fetching competitors: {e}")
        return 1
    if getattr(args, "json", False):
        print(json.dumps([{"app": name, "hits": hits} for name, hits in comps], indent=2))
        return 0
    print(f"\n🏆 Top Competitors Discovered [{country.upper()}] (across {len(seeds)} seed terms):")
    print(f"{'#':<3} {'App Name':<50} {'Seed Hits'}")
    print("-" * 65)
    for i, (name, hits) in enumerate(comps, 1):
        app_str = (name[:46] + "..") if len(name) > 48 else name
        print(f"{i:<3} {app_str:<50} {hits} seeds")
    return 0


def cmd_keywords_filter(args):
    from ads_keywords import export
    in_path = Path(args.input).resolve()
    out_dir = Path(args.output).resolve()
    brands = [b.strip() for b in getattr(args, "brand", []) if b.strip()]
    limit = getattr(args, "limit", 5000)
    log_info(f"Filtering candidates from {in_path} to {out_dir} (limit {limit})...")
    try:
        summary = export(in_path, out_dir, brands=brands, limit=limit)
    except Exception as e:
        log_error(f"Filter failed: {e}")
        print(f"Error filtering candidates: {e}")
        return 1
    if getattr(args, "json", False):
        print(json.dumps(summary, indent=2))
        return 0
    print("✓ Keywords filtered successfully:")
    print(f"  Accepted:  {summary['accepted']}")
    print(f"  Rejected:  {summary['rejected']}")
    print(f"  Protected: {summary['protected']}")
    print(f"  Output:    {out_dir}")
    return 0


def cmd_ads(args):
    """Manage Apple Ads campaigns, ad groups, and targeting keywords."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    account = app.get("ads_account")
    profile = app.get("ads_profile")

    if not account:
        print(f"Error: Missing Apple Ads account ID. Set **Apple Ads account**: in {store / 'config.md'}")
        return 2

    action = getattr(args, "ads_action", None)
    if action in ("campaigns", "list"):
        return cmd_ads_campaigns(args, account, profile)
    elif action == "adgroups":
        return cmd_ads_adgroups(args, account, profile)
    elif action == "keywords":
        return cmd_ads_keywords(args, account, profile)
    elif action == "add-keywords":
        return cmd_ads_add_keywords(args, account, profile)
    elif action == "pause":
        return cmd_ads_set_campaign_status(args, account, profile, "PAUSED")
    elif action == "resume":
        return cmd_ads_set_campaign_status(args, account, profile, "ENABLED")
    else:
        print("Unknown ads subcommand. Use: campaigns, adgroups, keywords, add-keywords, pause, resume")
        return 1


def cmd_ads_campaigns(args, account, profile):
    log_info(f"Fetching Apple Ads campaigns for account {account}...")
    payload = {"pagination": {"offset": 0, "pageSize": 1000}}
    cmd = ["asc", "ads", "campaigns", "find", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
    if rc != 0:
        log_error(f"asc ads campaigns find failed: {err}")
        print(f"Error querying campaigns: {err.strip() or f'exit {rc}'}")
        return rc
    try:
        data = json.loads(out)
        campaigns = data.get("result", [])
    except Exception as exc:
        log_error(f"Failed to parse campaigns output: {exc}")
        print(f"Failed to parse campaigns JSON: {exc}")
        return 1

    status_filter = getattr(args, "status", None)
    country_filter = getattr(args, "country", None)

    filtered = []
    for c in campaigns:
        st = c.get("status") or c.get("displayStatus") or ""
        if status_filter and status_filter.upper() != "ALL" and st.upper() != status_filter.upper():
            continue
        countries = (c.get("targeting") or {}).get("countryOrRegion", {}).get("include", [])
        if country_filter and country_filter.upper() not in [ct.upper() for ct in countries]:
            continue
        filtered.append(c)

    if getattr(args, "json", False):
        print(json.dumps(filtered, indent=2))
        return 0

    print(f"\n📢 Apple Ads Campaigns (Account: {account}) — {len(filtered)} campaigns:")
    print(f"{'ID':<12} {'Status':<9} {'Budget':<8} {'Country':<8} {'Name'}")
    print("-" * 75)
    for c in sorted(filtered, key=lambda x: x.get("name", "")):
        cid = str(c.get("id"))
        status = c.get("displayStatus") or c.get("status") or "UNKNOWN"
        budget_val = (c.get("dailyBudget") or {}).get("value", {})
        budget_str = f"${budget_val.get('amount', '?')}/d"
        countries = (c.get("targeting") or {}).get("countryOrRegion", {}).get("include", [])
        country_str = ",".join(countries) if countries else "—"
        name = c.get("name", "")
        print(f"{cid:<12} {status:<9} {budget_str:<8} {country_str:<8} {name}")
    return 0


def cmd_ads_adgroups(args, account, profile):
    campaign_id = getattr(args, "campaign_id", None)
    payload = {"pagination": {"offset": 0, "pageSize": 1000}}
    if campaign_id:
        payload["filters"] = [{"field": "campaignId", "operator": "EQUALS", "value": [int(campaign_id)]}]
    cmd = ["asc", "ads", "ad-groups", "find", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
    if rc != 0:
        print(f"Error querying ad groups: {err.strip() or f'exit {rc}'}")
        return rc
    try:
        data = json.loads(out)
        groups = data.get("result", [])
    except Exception as exc:
        print(f"Failed to parse ad groups: {exc}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(groups, indent=2))
        return 0
    print(f"\n📦 Apple Ads Ad Groups — {len(groups)} groups:")
    print(f"{'ID':<12} {'Campaign ID':<13} {'Status':<9} {'Bid':<7} {'Name'}")
    print("-" * 75)
    for g in groups:
        gid = str(g.get("id"))
        cid = str(g.get("campaignId"))
        st = g.get("displayStatus") or g.get("status") or "UNKNOWN"
        bid_amount = ((g.get("bidStrategy") or {}).get("bid") or {}).get("amount", "?")
        bid_str = f"${bid_amount}"
        name = g.get("name", "")
        print(f"{gid:<12} {cid:<13} {st:<9} {bid_str:<7} {name}")
    return 0


def cmd_ads_keywords(args, account, profile):
    adgroup_id = getattr(args, "adgroup_id", None)
    campaign_id = getattr(args, "campaign_id", None)
    payload = {"pagination": {"offset": 0, "pageSize": 1000}}
    filters = []
    if adgroup_id:
        filters.append({"field": "adGroupId", "operator": "EQUALS", "value": [int(adgroup_id)]})
    if campaign_id:
        filters.append({"field": "campaignId", "operator": "EQUALS", "value": [int(campaign_id)]})
    if filters:
        payload["filters"] = filters

    cmd = ["asc", "ads", "targeting-keywords", "find", "--ad-account", str(account), "--file", "-"]
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
    if rc != 0:
        print(f"Error querying keywords: {err.strip() or f'exit {rc}'}")
        return rc
    try:
        data = json.loads(out)
        keywords = data.get("result", [])
    except Exception as exc:
        print(f"Failed to parse keywords: {exc}")
        return 1

    if getattr(args, "json", False):
        print(json.dumps(keywords, indent=2))
        return 0
    print(f"\n🎯 Apple Ads Targeting Keywords — {len(keywords)} keywords:")
    print(f"{'ID':<12} {'Match':<7} {'Bid':<7} {'Status':<9} {'Keyword Text'}")
    print("-" * 75)
    for kw in keywords[:100]:
        kid = str(kw.get("id"))
        match = kw.get("matchType", "EXACT")
        bid_amount = (kw.get("bid") or {}).get("amount", "?")
        bid_str = f"${bid_amount}"
        st = kw.get("displayStatus") or kw.get("status") or "UNKNOWN"
        text = kw.get("text", "")
        print(f"{kid:<12} {match:<7} {bid_str:<7} {st:<9} {text}")
    if len(keywords) > 100:
        print(f"... and {len(keywords) - 100} more keywords.")
    return 0


def cmd_ads_add_keywords(args, account, profile):
    adgroup_id = getattr(args, "adgroup_id", None)
    if not adgroup_id:
        print("Error: --adgroup-id is required to add keywords.")
        return 1
    terms = []
    if getattr(args, "terms", None):
        terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    elif getattr(args, "file", None):
        p = Path(args.file).resolve()
        if p.is_file():
            terms = [line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not terms:
        print("Error: provide --terms <comma-separated> or --file <path-to-txt>")
        return 1

    bid = getattr(args, "bid", "0.30")
    match_type = getattr(args, "match_type", "EXACT").upper()
    log_info(f"Adding {len(terms)} {match_type} keywords (bid ${bid}) to ad group {adgroup_id}...")

    chunk_size = 500
    added = 0
    for i in range(0, len(terms), chunk_size):
        chunk = terms[i:i + chunk_size]
        items = [
            {
                "correlationId": idx + 1,
                "data": {
                    "adGroupId": int(adgroup_id),
                    "text": term,
                    "matchType": match_type,
                    "bid": {"amount": str(bid), "currency": "USD"}
                }
            }
            for idx, term in enumerate(chunk)
        ]
        payload = {"allowPartialSuccess": True, "items": items}
        cmd = ["asc", "ads", "targeting-keywords", "create-bulk", "--ad-account", str(account), "--file", "-", "--confirm"]
        if profile:
            cmd.extend(["--ads-profile", str(profile)])
        rc, out, err = run_cmd(cmd, input_text=json.dumps(payload))
        if rc != 0:
            log_error(f"Failed to add chunk {i // chunk_size + 1}: {err}")
            print(f"Error adding keywords: {err.strip() or f'exit {rc}'}")
            return rc
        try:
            res_data = json.loads(out)
            chunk_results = res_data.get("result", [])
            successful = sum(1 for item in chunk_results if item.get("result") or item.get("id"))
            added += successful if successful > 0 else len(chunk)
            log_debug(f"Added chunk of {len(chunk)} keywords.")
        except Exception:
            added += len(chunk)

    print(f"✓ Successfully added {added} {match_type} keywords to ad group {adgroup_id} at ${bid} CPT.")
    return 0


def cmd_ads_set_campaign_status(args, account, profile, target_status):
    campaign_id = getattr(args, "campaign_id", None)
    if not campaign_id:
        print("Error: --campaign-id is required.")
        return 1
    action = "pause" if target_status == "PAUSED" else "resume"
    log_info(f"{action.capitalize()}ing campaign {campaign_id}...")
    cmd = ["asc", "ads", "campaigns", action, "--ad-account", str(account), "--campaign", str(campaign_id)]
    if action == "resume":
        cmd.append("--confirm")
    if profile:
        cmd.extend(["--ads-profile", str(profile)])
    rc, out, err = run_cmd(cmd)
    if rc == 0:
        print(f"✓ Campaign {campaign_id} {action}d successfully.")
        return 0
    else:
        print(f"Error: {err.strip() or f'exit {rc}'}")
        return rc


def cmd_reviews(args):
    """Inspect and manage App Store reviews and ratings."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    app_id = app["app_id"]

    if args.action == "ratings":
        result = subprocess.run(["asc", "reviews", "ratings", "--app", app_id, "--all"])
    elif args.action == "unreplied":
        result = subprocess.run(["asc", "reviews", "--app", app_id, "--only-unresponded"])
    elif args.action == "list":
        result = subprocess.run(["asc", "reviews", "--app", app_id, "--limit", str(args.limit)])
    elif args.action == "respond":
        if not args.review_id or not args.response:
            print("Error: --review-id and --response are required for respond action.")
            sys.exit(1)
        result = subprocess.run(["asc", "reviews", "respond", "--review-id", args.review_id, "--response", args.response])
    return result.returncode


def cmd_funnel(args):
    """Pull or summarize App Store Connect Funnel Analytics."""
    store = Path(args.store).resolve()
    pull_script = store / "scripts" / "pull_funnel.py"
    if not pull_script.exists():
        pull_script = SKILL_DIR / "scripts" / "pull_funnel.py"

    if args.pull:
        if not pull_script.is_file():
            print(f"Funnel pull script not found at {pull_script}")
            return 2
        app = resolve_app_identity(store)
        command, raw_dir, reason = prepare_funnel_pull(pull_script, store, app["app_id"])
        if command is None:
            print(reason)
            return 2
        print(f"Pulling ASC funnel analytics into {store / 'metrics'}...")
        print(f"Preserving source CSVs under {raw_dir}")
        return subprocess.run(command).returncode
    else:
        # Display latest summary from weekly.csv
        weekly_csv = store / "metrics" / "weekly.csv"
        if not weekly_csv.exists():
            print(f"No {weekly_csv} found. Run with --pull first.")
            return 2
        import csv
        with weekly_csv.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            print("weekly.csv is empty.")
            return 2
        # Find latest recorded date
        latest_rec = max(r.get("recorded", "") for r in rows)
        latest_rows = [r for r in rows if r.get("recorded") == latest_rec]
        all_row = next((r for r in latest_rows if r.get("segment") == "all"), None)
        print(f"\n📊 ASC Funnel Summary (Latest snapshot: {latest_rec})")
        if all_row:
            print(f"  Impressions:        {all_row.get('impressions')}")
            print(f"  Product Page Views: {all_row.get('product_page_views')}")
            print(f"  Downloads (first):  {all_row.get('downloads')}")
            print(f"  Conversion Rate:    {all_row.get('cvr_pct')}%")
            print(f"  Trial Starts:       {all_row.get('trial_starts')}")
            print(f"  Note:               {all_row.get('note')}")
        else:
            print("  ⚠️ Aggregate segment unavailable in this snapshot.")
        print("\nTop Storefronts:")
        for r in latest_rows:
            seg = r.get("segment")
            if seg != "all":
                print(f"  {seg.upper()}: {r.get('impressions')} imp, {r.get('product_page_views')} views, {r.get('downloads')} dl (CVR: {r.get('cvr_pct')}%)")
        print_lifecycle(store / "metrics" / "lifecycle.csv")
        return 0 if all_row else 2


def print_lifecycle(path):
    """Installs vs deletions from ASC's opt-in Installation and Deletion report."""
    import csv
    if not path.exists():
        print("\nLifecycle: no lifecycle.csv — the store's pull_funnel.py does not emit it yet "
              "(see references/funnel-analytics.md § Deletions).")
        return
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    latest = max(r.get("recorded", "") for r in rows)
    print(f"\n🗑️  Install → delete lifecycle (opt-in sample, snapshot {latest}; not totals, not a cohort rate)")
    for r in (r for r in rows if r.get("recorded") == latest):
        median = r.get("median_days_to_delete") or "—"
        print(f"  {r['segment'].upper():>4}: {r['first_installs_optin']} installs · {r['deletions_optin']} deletions "
              f"· {r['deleted_within_1d']}/{r['deletions_timed']} within 1 day · median {median} d")


def cmd_ga(args):
    """Pull Google Analytics 4 in-app telemetry."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    ga_script = SKILL_DIR / "scripts" / "pull_ga.py"
    if not ga_script.exists():
        ga_script = store / "scripts" / "pull_ga.py"

    if not ga_script.exists():
        print(f"GA4 pull script not found at {ga_script}")
        return 2
    property_id = getattr(args, "property_id", None) or app["ga4_property_id"]
    if not property_id or not property_id.isdigit():
        print(f"Set a numeric GA4 Property ID in {store / 'config.md'} or pass --property-id explicitly.")
        return 2

    # Use project .venv if available
    venv_py = Path.cwd() / ".venv" / "bin" / "python"
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    cmd = [py_exec, str(ga_script), "--store", str(store), "--days", str(args.days)]
    cmd.extend(["--property-id", property_id])
    if getattr(args, "credentials", None):
        cmd.extend(["--credentials", args.credentials])
    if getattr(args, "realtime", False):
        cmd.append("--realtime")
    if getattr(args, "include_debug", False):
        cmd.append("--include-debug")
    if getattr(args, "export_csv", False):
        cmd.append("--export-csv")

    return subprocess.run(cmd).returncode


def cmd_ledger(args):
    """Delegate to ledger.py."""
    store = Path(args.store).resolve()
    ledger_py = SKILL_DIR / "scripts" / "ledger.py"
    if not ledger_py.exists():
        print(f"ledger.py not found at {ledger_py}")
        return 1
    forward_args = [sys.executable, str(ledger_py), "--store", str(store)] + args.ledger_args
    return subprocess.run(forward_args).returncode


def cmd_radar(args):
    """Delegate to radar.py."""
    radar_py = SKILL_DIR / "scripts" / "radar.py"
    if not radar_py.exists():
        print(f"radar.py not found at {radar_py}")
        return 1
    return subprocess.run([sys.executable, str(radar_py), "--store", str(Path(args.store).resolve())]
                          + args.radar_args).returncode


def cmd_google(args):
    """Google Search Intelligence: Trends, Autocomplete suggestions, and Batch volume profiling."""
    action = getattr(args, "google_action", None)
    if not action:
        log_error("Specify a google action: 'trends', 'suggest', or 'batch'")
        return 1
    if action == "trends":
        return cmd_google_trends(args)
    elif action == "suggest":
        return cmd_google_suggest(args)
    elif action == "batch":
        return cmd_google_batch(args)
    else:
        log_error(f"Unknown google action: {action}")
        return 1


def _trend_req():
    """(TrendReq, None), or (None, exit code) after re-running this command inside the skill's .venv.

    pytrends is an unofficial scraper of Google Trends and is not a dependency of the rest of the skill, so it lives in
    `<skill>/.venv`. Nothing here may name a user's home directory: the repo is public and shared across apps.
    """
    try:
        from pytrends.request import TrendReq
        return TrendReq, None
    except ImportError:
        venv_py = SKILL_DIR / ".venv" / "bin" / "python3"
        if venv_py.exists() and str(sys.executable) != str(venv_py):
            return None, subprocess.run([str(venv_py), __file__] + sys.argv[1:]).returncode
        log_error(f"pytrends is not installed. Install it with: python3 -m venv {SKILL_DIR}/.venv && "
                  f"{SKILL_DIR}/.venv/bin/pip install pytrends")
        return None, 1


def cmd_google_trends(args):
    """Compare search interest via Google Trends."""
    terms = getattr(args, "terms", [])
    if not terms:
        log_error("Specify at least one keyword term to compare.")
        return 1

    country = getattr(args, "country", "UA")
    timeframe = getattr(args, "timeframe", "today 12-m")
    as_json = getattr(args, "json", False)
    do_related = getattr(args, "related", False)
    do_geo = getattr(args, "geo", False)

    TrendReq, code = _trend_req()
    if TrendReq is None:
        return code

    pytrend = TrendReq(hl="en-US", tz=180, timeout=(10, 30))

    # 1. Related queries mode
    if do_related:
        target = terms[0]
        log_info(f"Querying Google Trends related queries for '{target}' in {country} ({timeframe})...")
        try:
            pytrend.build_payload([target], cat=0, timeframe=timeframe, geo=country)
            rq = pytrend.related_queries()
        except Exception as exc:
            log_error(f"Google Trends query failed: {exc}")
            return 1

        top_df = rq.get(target, {}).get("top") if rq else None
        rising_df = rq.get(target, {}).get("rising") if rq else None

        top_list = top_df.to_dict(orient="records") if top_df is not None and not top_df.empty else []
        rising_list = rising_df.to_dict(orient="records") if rising_df is not None and not rising_df.empty else []

        if as_json:
            print(json.dumps({"target": target, "country": country, "timeframe": timeframe, "top": top_list, "rising": rising_list}, ensure_ascii=False, indent=2))
            return 0

        print(f"\n📡 Google Trends Related Queries for '{target}' in {country.upper()} ({timeframe}):")
        print("\n🔥 RISING QUERIES (Breakouts & Emerging Trends):")
        if rising_list:
            for item in rising_list[:10]:
                q = item.get("query", "")
                val = item.get("value", "")
                val_str = f"+{val}%" if isinstance(val, (int, float)) and val < 5000 else "Breakout (Explosive)"
                print(f"  • {q:<35} {val_str}")
        else:
            print("  (No rising queries detected for this period/country)")

        print("\n🔝 TOP RELATED QUERIES (Highest Search Volume):")
        if top_list:
            for item in top_list[:10]:
                q = item.get("query", "")
                val = item.get("value", "")
                print(f"  • {q:<35} (Score: {val})")
        else:
            print("  (No top related queries returned)")
        print()
        return 0

    # 2. Subregion Geo breakdown mode
    if do_geo:
        log_info(f"Querying Google Trends subregion breakdown for {terms[:5]} in {country} ({timeframe})...")
        try:
            pytrend.build_payload(terms[:5], cat=0, timeframe=timeframe, geo=country)
            geo_df = pytrend.interest_by_region(resolution="REGION", inc_low_vol=True, inc_geo_code=True)
        except Exception as exc:
            log_error(f"Google Trends geo query failed: {exc}")
            return 1

        if geo_df.empty:
            log_warn("No subregion data available.")
            return 0

        active_regions = geo_df[(geo_df[terms[:5]] > 0).any(axis=1)]
        if as_json:
            print(active_regions.to_json(orient="index", force_ascii=False, indent=2))
            return 0

        print(f"\n🗺️ Google Trends Subregion Interest Breakdown in {country.upper()} ({timeframe}):")
        for region_name, row in active_regions.head(15).iterrows():
            scores_str = ", ".join(f"{kw}: {row[kw]}" for kw in terms[:5] if kw in row)
            print(f"  • {region_name:<30} [{scores_str}]")
        print()
        return 0

    # 3. Standard comparison mode
    log_info(f"Querying Google Trends for {terms[:5]} in {country} ({timeframe})...")
    try:
        pytrend.build_payload(terms[:5], cat=0, timeframe=timeframe, geo=country)
        df = pytrend.interest_over_time()
    except Exception as exc:
        log_error(f"Google Trends query failed: {exc}")
        return 1

    if df.empty:
        log_warn("No direct trend data returned (queries may have low volume or Google rate-limited).")
        if as_json:
            print(json.dumps({"terms": terms, "country": country, "timeframe": timeframe, "scores": {}}))
        return 0

    means = {kw: float(df[kw].mean()) for kw in terms if kw in df}
    max_val = max(means.values()) if means else 1.0

    if as_json:
        res = {
            "country": country,
            "timeframe": timeframe,
            "scores": means,
            "relative_ratios": {kw: round(v / max_val, 3) for kw, v in means.items()} if max_val > 0 else {}
        }
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    print(f"\n📡 Google Trends Search Interest in {country.upper()} ({timeframe}):")
    print(f"   (Relative score 0-100 scale, normalized against peak)\n")
    first_val = list(means.values())[0] if means else 1.0
    for kw, val in sorted(means.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int((val / max_val) * 25) if max_val > 0 else ""
        ratio = (val / first_val) if first_val > 0 else 0
        print(f"  {kw:<30} {val:5.1f}  {bar:<25} ({ratio:.2f}x)")
    print()
    return 0


def cmd_google_suggest(args):
    """Live Google search autocomplete hints across storefronts and languages."""
    term = getattr(args, "term", "").strip()
    if not term:
        log_error("Specify a search term to inspect suggestions.")
        return 1

    country = getattr(args, "country", "UA")
    lang = getattr(args, "lang", "uk")
    limit = getattr(args, "limit", 15)
    matrix = getattr(args, "matrix", False)
    as_json = getattr(args, "json", False)

    def fetch_suggestions(q):
        url = f"https://suggestqueries.google.com/complete/search?client=chrome&q={urllib.parse.quote(q)}&hl={lang}&gl={country}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data[1] if len(data) > 1 else []
        except Exception:
            return []

    # Matrix expansion mode
    if matrix:
        log_info(f"Generating Google Autocomplete Intent Matrix for '{term}' [{country.upper()}/{lang}]...")
        if lang in ("uk", "ru"):
            modifiers = [
                ("how", f"як {term}"),
                ("what_tool", f"чим {term}"),
                ("for_platform", f"{term} для"),
                ("to_size", f"{term} до"),
                ("without_friction", f"{term} без"),
                ("on_device", f"{term} на"),
                ("app_tool", f"{term} програма"),
                ("app_tool2", f"{term} додаток"),
                ("online_fast", f"{term} онлайн"),
            ]
        else:
            modifiers = [
                ("how", f"how to {term}"),
                ("best", f"best {term}"),
                ("for_platform", f"{term} for"),
                ("to_size", f"{term} to"),
                ("without_friction", f"{term} without"),
                ("on_device", f"{term} on"),
                ("app_tool", f"{term} app"),
                ("online_fast", f"{term} online"),
            ]

        discovered = {}
        for mod_key, mod_q in modifiers:
            suggs = fetch_suggestions(mod_q)
            for s in suggs:
                if s not in discovered:
                    discovered[s] = mod_key

        categories = {
            "platforms": [],
            "size_limits": [],
            "quality_constraints": [],
            "devices": [],
            "questions": [],
            "tools_and_apps": [],
            "other": []
        }

        platform_kw = ("телеграм", "telegram", "вайбер", "viber", "інстаграм", "instagram", "фейсбук", "facebook", "whatsapp", "вотсап", "дискорд", "discord", "пошт", "mail", "gmail")
        size_kw = ("мб", "mb", "гб", "gb", "розмір", "размер", "size", "ваг")
        quality_kw = ("без втрати якості", "без потери качества", "якість", "качество", "watermark", "водяного знаку", "безкоштовно", "бесплатно", "free", "онлайн", "online")
        device_kw = ("айфон", "iphone", "ios", "телефон", "мак", "mac", "пк", "комп'ютер", "компьютер", "андроїд", "android")
        question_kw = ("як", "как", "чим", "чем", "how", "why")
        tool_kw = ("додаток", "приложение", "програма", "программа", "app", "софт", "converter", "компресор", "compressor")

        for s in discovered.keys():
            s_lower = s.lower()
            if any(k in s_lower for k in platform_kw):
                categories["platforms"].append(s)
            elif any(k in s_lower for k in size_kw):
                categories["size_limits"].append(s)
            elif any(k in s_lower for k in quality_kw):
                categories["quality_constraints"].append(s)
            elif any(k in s_lower for k in device_kw):
                categories["devices"].append(s)
            elif any(k in s_lower for k in question_kw):
                categories["questions"].append(s)
            elif any(k in s_lower for k in tool_kw):
                categories["tools_and_apps"].append(s)
            else:
                categories["other"].append(s)

        if as_json:
            print(json.dumps({"seed": term, "country": country, "lang": lang, "categories": categories}, ensure_ascii=False, indent=2))
            return 0

        print(f"\n🌐 Google Autocomplete Deep Intent Matrix for '{term}' [{country.upper()}/{lang}]:")
        print(f"   (Discovered {len(discovered)} verified high-intent long-tail search phrases)\n")

        icons = {
            "platforms": "📱 Platforms & Messengers (High Conversion)",
            "size_limits": "💾 File Size & Storage Limits",
            "quality_constraints": "⚙️ Quality & Friction Expectations",
            "devices": "🍎 Devices & Ecosystem Targets",
            "questions": "❓ Question & How-to Triggers (SEO / FAQ)",
            "tools_and_apps": "🛠️ Direct Tool & App Intent (Prime ASA)",
            "other": "🔍 Additional Discovered Terms"
        }

        for cat_key, title in icons.items():
            items = categories[cat_key]
            if items:
                print(f"[{title}]:")
                for item in items[:8]:
                    print(f"  • {item}")
                print()
        return 0

    # Standard suggestions
    suggestions = fetch_suggestions(term)[:limit]
    if as_json:
        print(json.dumps(suggestions, ensure_ascii=False, indent=2))
        return 0

    print(f"\n🔍 Live Google Autocomplete Suggestions for '{term}' [{country.upper()}/{lang}]:")
    print(f"   (Found {len(suggestions)} suggestions)\n")
    for i, s in enumerate(suggestions, 1):
        print(f"  {i:2d}. {s}")
    print()
    return 0


# Trends returns whole numbers 0-100 per week. An anchor that averages below this leaves large ratios dividing by a
# rounding error (a run on 2026-10-17 anchored on an index of ~6 and printed 13.08x, 1,307.6 and 2,694.0 for neighbouring
# spellings), so the table is then only an ORDER.
GOOGLE_ANCHOR_FLOOR = 8.0


def google_ratio(candidate_mean, anchor_mean):
    """Index with the anchor at 100, or None when the anchor cannot support a ratio (0 or missing)."""
    if anchor_mean is None or anchor_mean <= 0:
        return None
    return round(candidate_mean / anchor_mean * 100.0, 1)


def cmd_google_batch(args):
    """Relative demand of many keywords against one anchor: four candidates plus the anchor per Trends request.

    Never prints a number it cannot support: a throttled (empty) response and a zero anchor give `n/a`, and a candidate
    that Trends rounds to 0 next to the anchor is "below Trends' floor", not "no demand".
    """
    anchor = getattr(args, "anchor", None)
    terms_arg = getattr(args, "terms", None)
    file_arg = getattr(args, "file", None)
    country = getattr(args, "country", "UA")
    timeframe = getattr(args, "timeframe", "today 12-m")
    delay = getattr(args, "delay", 1.5)
    as_json = getattr(args, "json", False)

    TrendReq, code = _trend_req()
    if TrendReq is None:
        return code

    candidates = []
    if file_arg:
        fpath = Path(file_arg)
        if not fpath.exists():
            log_error(f"Candidate file not found: {file_arg}")
            return 1
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = [p.strip() for p in line.split(",") if p.strip()]
                    candidates.extend(parts)
    elif terms_arg:
        if isinstance(terms_arg, list):
            candidates = [t.strip() for t in terms_arg if t.strip()]
        else:
            candidates = [t.strip() for t in terms_arg.split(",") if t.strip()]

    if not candidates:
        log_error("Provide candidates via --terms 'kw1,kw2' or --file path/to/file.txt")
        return 1

    if not anchor:
        anchor = candidates[0]
        candidates = candidates[1:]
    else:
        candidates = [c for c in candidates if c.lower() != anchor.lower()]

    seen = set([anchor.lower()])
    unique_cands = []
    for c in candidates:
        if c.lower() not in seen:
            seen.add(c.lower())
            unique_cands.append(c)

    if not unique_cands:
        log_error("No distinct candidates to compare against anchor.")
        return 1

    log_info(f"Starting Google Trends Batch Profiling: {len(unique_cands)} candidates against Anchor '{anchor}' in {country} ({timeframe})...")

    pytrend = TrendReq(hl="en-US", tz=180, timeout=(10, 30))

    chunk_size = 4
    chunks = [unique_cands[i:i + chunk_size] for i in range(0, len(unique_cands), chunk_size)]

    scores = {anchor: 100.0}   # term -> index; None = unavailable
    notes = {}                 # term -> why it has no number, or what 0.0 means
    anchor_means = []

    for idx, chunk in enumerate(chunks, 1):
        batch = [anchor] + chunk
        log_info(f"Processing Batch {idx}/{len(chunks)}: {batch}...")
        df = None
        try:
            pytrend.build_payload(batch, cat=0, timeframe=timeframe, geo=country)
            df = pytrend.interest_over_time()
        except Exception as exc:
            log_error(f"Batch {idx} failed: {exc}")
        if df is None or df.empty or anchor not in df:
            # Google answers a throttled request with an empty frame: that is "no data", never "no demand".
            log_warn(f"Batch {idx} returned no data; its terms are n/a, not zero.")
            for c in chunk:
                scores[c], notes[c] = None, "no data"
        else:
            anchor_mean = float(df[anchor].mean())
            anchor_means.append(anchor_mean)
            for c in chunk:
                if c not in df:
                    scores[c], notes[c] = None, "no data"
                    continue
                c_mean = float(df[c].mean())
                scores[c] = google_ratio(c_mean, anchor_mean)
                if scores[c] is None:
                    notes[c] = "anchor read 0"
                elif c_mean == 0:
                    notes[c] = "below Trends' floor"
        if idx < len(chunks):
            time.sleep(delay)

    ranked = sorted(((v, k) for k, v in scores.items() if v is not None and k != anchor))
    warnings = []
    if anchor_means and min(anchor_means) < GOOGLE_ANCHOR_FLOOR:
        pick = ranked[(len(ranked) - 1) // 2][1] if ranked else None  # lower median: a mid-volume term, not the top one
        warnings.append(
            f"Anchor '{anchor}' averaged {min(anchor_means):.1f} on Trends' 0-100 scale (below {GOOGLE_ANCHOR_FLOOR:g}): "
            "the multipliers divide by a rounding error, so read the ORDER, not the sizes."
            + (f" Re-run with a mid-volume anchor, e.g. '{pick}'." if pick else ""))

    valid_items = [(k, v) for k, v in scores.items() if v is not None]
    sorted_scores = sorted(valid_items, key=lambda x: x[1], reverse=True)
    unavailable = [k for k, v in scores.items() if v is None]

    if as_json:
        print(json.dumps({"anchor": anchor, "country": country, "timeframe": timeframe,
                          "scores": dict(sorted_scores), "notes": notes, "unavailable": unavailable,
                          "anchor_means": anchor_means, "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0

    max_val = sorted_scores[0][1] if sorted_scores else 100.0
    print(f"\n📊 Google Trends Batch Profiling in {country.upper()} ({timeframe}):")
    print(f"   (Index against Anchor '{anchor}' = 100.0; Google web search, relative, languages mixed)\n")
    print(f"  {'Rank':<4} {'Keyword':<32} {'Index':>10}   {'Visual Scale':<22} {'Note'}")
    print(f"  {'-'*4} {'-'*32} {'-'*10}   {'-'*22} {'-'*20}")

    for rank, (kw, val) in enumerate(sorted_scores, 1):
        bar = "█" * (int((val / max_val) * 20) if max_val > 0 else 0)
        note = "[ANCHOR]" if kw.lower() == anchor.lower() else notes.get(kw, "")
        print(f"  {rank:<4d} {kw:<32} {val:>10.1f}   {bar:<22} {note}")
    for kw in unavailable:
        print(f"  {'-':<4} {kw:<32} {'n/a':>10}   {'':<22} {notes.get(kw, '')}")

    for w in warnings:
        print(f"\n  ⚠️ {w}")
    print()
    return 0


class _Tee:
    """Pass stdout through unchanged while keeping a copy for the closing stage table."""
    def __init__(self, real):
        self.real, self.parts = real, []

    def write(self, s):
        self.parts.append(s)
        return self.real.write(s)

    def flush(self):
        self.real.flush()

    def __getattr__(self, name):
        return getattr(self.real, name)


def cycle_stage_table(text):
    """Stage | status | reason, read back from the cycle's own `▶ [n/6]` sections.

    The long output scrolls and a caller that tails it loses the warnings; this is the part that
    must still be on screen. ok = no warning; partial = a warning line; failed = a source error or
    a non-zero child; skipped = the stage was switched off by a flag.
    """
    sections = re.split(r"(?m)^▶ \[(\d)/6\] (.*)$", text)
    rows = []
    for i in range(1, len(sections), 3):
        num, name, body = sections[i], sections[i + 1].rstrip("."), sections[i + 2]
        # the cycle flags trouble with "⚠️", except one 📝 line (unresponded reviews) that says "unknown"
        warn = [l.strip() for l in body.splitlines()
                if "⚠️" in l or ("📝" in l and re.search(r"unknown|no output", l))]
        if "explicitly skipped" in body and not warn:
            rows.append((num, name, "skipped", "flag"))
        elif not warn:
            rows.append((num, name, "ok", ""))
        else:
            hard = re.search(r"Could not|failed|unavailable|exited with code|not found|missing", warn[0])
            rows.append((num, name, "failed" if hard else "partial", warn[0].replace("⚠️", "").replace("📝", "").strip()[:150]))
    return rows


def funnel_digest(store, today=None):
    """The store funnel and install lifecycle the cycle already holds, as a table with its conversions.

    Reads metrics/weekly.csv and metrics/lifecycle.csv (the newest `recorded` block of each) so the numbers a
    reader needs are on screen without opening a file. A block older than 3 days is called STALE: this store's
    weekly.csv once sat 11 days behind its source and nobody could tell from the output.
    """
    import csv
    today = today or dt.date.today()

    def newest(name):
        path = store / "metrics" / name
        if not path.is_file():
            return None, []
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        if not rows:
            return None, []
        rec = max(r.get("recorded", "") for r in rows)
        return rec, [r for r in rows if r.get("recorded") == rec]

    def pct(a, b):
        try:
            return f"{100 * float(a) / float(b):.1f}%" if float(b) else "—"
        except (TypeError, ValueError):
            return "—"

    def age(rec):
        try:
            days = (today - dt.date.fromisoformat(rec)).days
        except ValueError:
            return ""
        return f" — STALE: {days} days old" if days > 3 else ""

    print("\nFUNNEL DIGEST (store → install; cumulative since the week_start of each block)")
    rec, rows = newest("weekly.csv")
    if not rows:
        print("  store funnel: no metrics/weekly.csv rows — run `copilot.py funnel --pull`")
    else:
        print(f"  App Store funnel, {rows[0].get('week_start')} → {rec}{age(rec)}  [store:metrics/weekly.csv]")
        print(f"  {'segment':<8}{'impr':>8}{'page views':>11}{'1st dl':>8}{'PV/impr':>9}{'dl/impr':>9}{'dl/PV':>8}{'trials':>8}")
        for r in rows:
            print(f"  {r.get('segment', ''):<8}{r.get('impressions', ''):>8}{r.get('product_page_views', ''):>11}"
                  f"{r.get('downloads', ''):>8}{pct(r.get('product_page_views'), r.get('impressions')):>9}"
                  f"{pct(r.get('downloads'), r.get('impressions')):>9}{pct(r.get('downloads'), r.get('product_page_views')):>8}"
                  f"{(r.get('trial_starts') or 'n/a'):>8}")
        print("  (dl/PV can exceed 100%: Apple counts downloads from the search card without a page view)")
    rec, rows = newest("lifecycle.csv")
    if not rows:
        print("  lifecycle: no metrics/lifecycle.csv rows")
    else:
        print(f"  Opt-in install lifecycle, {rows[0].get('week_start')} → {rec}{age(rec)}  [store:metrics/lifecycle.csv]")
        print(f"  {'segment':<8}{'installs':>9}{'deleted':>9}{'deleted %':>10}{'≤1 day':>8}")
        for r in rows:
            print(f"  {r.get('segment', ''):<8}{r.get('first_installs_optin', ''):>9}{r.get('deletions_optin', ''):>9}"
                  f"{pct(r.get('deletions_optin'), r.get('first_installs_optin')):>10}{r.get('deleted_within_1d', ''):>8}")


def cmd_brief(args):
    """One screen of everything already on disk or one cheap read away: App Store Connect state, Top-200 bands per
    storefront, every hypothesis with its state, the store funnel. No network except `asc` reads; writes nothing."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    print(f"BRIEF · {app['brand']} · app {app['app_id']} · {dt.date.today()}")

    print("\nAPP STORE CONNECT")
    rc, out, err = run_cmd(["asc", "status", "--app", app["app_id"]])
    try:
        d = json.loads(out[out.index("{"):]) if rc == 0 else {}
    except ValueError:
        d = {}
    if not d:
        print(f"  ⚠️ asc status unavailable: {err.strip()[:160] or f'exit {rc}'}")
    else:
        s, b, tf, v = d.get("summary", {}), d.get("builds", {}).get("latest", {}), d.get("testflight", {}), d.get("appstore", {})
        print(f"  health: {s.get('health')} · next: {s.get('nextAction')}")
        for blocker in s.get("blockers", []):
            print(f"  blocker: {blocker}")
        print(f"  working version: {v.get('version')} {v.get('state')} · latest build {b.get('version')} ({b.get('buildNumber')}) "
              f"{b.get('processingState')}, uploaded {str(b.get('uploadedDate', ''))[:16]} · TestFlight {tf.get('internalBuildState')}")
    rc, out, err = run_cmd(["asc", "versions", "list", "--app", app["app_id"], "--platform", "IOS"])
    try:
        versions = json.loads(out[out.index("{"):])["data"] if rc == 0 else []
    except ValueError:
        versions = []
    if versions:
        print("  versions: " + " · ".join(f"{x['attributes']['versionString']} {x['attributes']['appStoreState']}" for x in versions[:5]))
    for label, cmd in (("subscriptions", ["asc", "subscriptions", "list", "--app", app["app_id"]]),
                       ("in-app purchases", ["asc", "iap", "list", "--app", app["app_id"]])):
        rc, out, err = run_cmd(cmd)
        try:
            items = json.loads(out[out.index("{"):])["data"] if rc == 0 else []
        except ValueError:
            items = []
        if items:
            print(f"  {label}: " + " · ".join(f"{i['attributes'].get('productId', '?').rsplit('.', 1)[-1]} {i['attributes'].get('state')}" for i in items))

    import ledger
    ledger.bands(store)

    print("\nHYPOTHESES (state as of today; `ledger.py report` has the per-key detail)")
    rc, out, err = run_cmd([sys.executable, str(SKILL_DIR / "scripts" / "ledger.py"), "--store", str(store), "report"])
    section = out.split("## A", 1)[-1].split("## B", 1)[0] if rc == 0 and "## A" in out else ""
    print(section.strip() or f"  ⚠️ ledger report unavailable: {err.strip()[:160]}")

    funnel_digest(store)
    return 0


def cmd_cycle(args):
    """Run the cycle, then print the funnel digest and a stage → status → reason table LAST."""
    tee = _Tee(sys.stdout)
    sys.stdout = tee
    try:
        code = _cycle_run(args)
    finally:
        sys.stdout = tee.real
    rows = cycle_stage_table("".join(tee.parts))
    funnel_digest(Path(args.store).resolve())
    print("\nSTAGE SUMMARY (a footer above is not a completeness certificate)")
    print(f"{'#':<2} {'stage':<46} {'status':<8} reason")
    for num, name, status, reason in rows:
        print(f"{num:<2} {name[:46]:<46} {status:<8} {reason}")
    return code


def _cycle_run(args):
    """Run the consolidated live-read and local snapshot pass."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    app_id = app["app_id"]
    partial = False

    print("=================================================================")
    print(f"🚀 {app['brand']} Marketing CLI Cycle · {store}")
    print(f"App ID: {app_id} · Version: {app['version']}")
    print("=================================================================\n")

    # Step 1: Reconcile versions
    print("▶ [1/6] Verifying App Store Connect Versions...")
    rc, out, err = run_cmd(["asc", "versions", "list", "--app", app_id, "--platform", "IOS"])
    if rc == 0:
        if out.strip():
            summary = compact_asc_output(out, "versions")
            if summary:
                print(f"  {summary}")
            else:
                print("  ⚠️ ASC version output format is unknown; payload omitted.")
                partial = True
        else:
            print("  ⚠️ ASC version query returned no output.")
            partial = True
    else:
        print(f"  ⚠️ Could not query ASC versions: {err.strip() or f'exit {rc}'}")
        partial = True

    # Step 2: Reviews & Ratings
    print("\n▶ [2/6] Auditing Customer Reviews & Ratings...")
    rc, out, err = run_cmd(["asc", "reviews", "ratings", "--app", app_id, "--all"])
    if rc == 0 and out.strip():
        summary = compact_asc_output(out, "ratings")
        if summary:
            print(f"  {summary}")
        else:
            print("  ⚠️ ASC ratings output format is unknown; payload omitted.")
            partial = True
    elif rc == 0:
        print("  ⚠️ ASC ratings query returned no output.")
        partial = True
    else:
        print(f"  ⚠️ Could not query ASC ratings: {err.strip() or f'exit {rc}'}")
        partial = True
    rc, out, err = run_cmd(["asc", "reviews", "--app", app_id, "--only-unresponded"])
    if rc == 0 and out.strip():
        summary = compact_asc_output(out, "unreplied")
        if summary:
            print(f"  📝 {summary}")
        else:
            print("  📝 Unresponded review output format is unknown; payload omitted.")
            partial = True
    elif rc == 0:
        print("  📝 Unresponded review query returned no output; whether there are zero rows is unknown.")
        partial = True
    else:
        print(f"  ⚠️ Could not query unresponded reviews: {err.strip() or f'exit {rc}'}")
        partial = True

    # Step 3: Funnel metrics
    print("\n▶ [3/6] Syncing Funnel Analytics...")
    pull_script = store / "scripts" / "pull_funnel.py"
    if not pull_script.exists():
        pull_script = SKILL_DIR / "scripts" / "pull_funnel.py"
    if args.skip_pull:
        print("  (Funnel pull explicitly skipped)")
    elif pull_script.exists():
        command, raw_dir, reason = prepare_funnel_pull(pull_script, store, app_id)
        if command is None:
            print(f"  ⚠️ {reason}")
            partial = True
        else:
            print("  Running pull_funnel.py (ASC analytics reporting is not real-time — this can take "
                  "several minutes for a storefront with many tracked keywords)...")
            print(f"  Preserving source CSVs under {raw_dir}")
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            lines = []
            for line in proc.stdout:
                lines.append(line.strip())
                print("  " + line.rstrip("\n"), flush=True)
            rc = proc.wait()
            if rc == 0:
                print("  ✓ Funnel metrics updated.")
            else:
                why = next((l for l in reversed(lines) if re.search(r"refus|rate limit|429|Error:", l)),
                           next((l for l in reversed(lines) if l), "no output"))
                print(f"  ⚠️ pull_funnel.py exited with code {rc}; funnel metrics may be stale. "
                      f"Cause: {why[:200]}")
                partial = True
    else:
        print("  ⚠️ Funnel pull unavailable — pull_funnel.py not found in store or skill scripts/.")
        partial = True

    # Step 4: GA4 Telemetry
    print("\n▶ [4/6] Pulling In-App Telemetry (GA4)...")
    ga_script = SKILL_DIR / "scripts" / "pull_ga.py"
    if not ga_script.exists():
        ga_script = store / "scripts" / "pull_ga.py"
    venv_py = Path.cwd() / ".venv" / "bin" / "python"
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    if args.skip_ga:
        print("  (GA4 pull explicitly skipped)")
    elif not app["ga4_property_id"]:
        print(f"  ⚠️ GA4 Property ID missing from {store / 'config.md'}; skipping rather than using a fallback.")
        partial = True
    elif ga_script.exists():
        rc, out, err = run_cmd([py_exec, str(ga_script), "--store", str(store), "--days", "14",
                                "--property-id", app["ga4_property_id"]])
        if rc == 0:
            if not out.strip():
                print("  ⚠️ GA4 returned no output; whether the result is empty or unavailable is unknown.")
                partial = True
            else:
                lines = out.splitlines()
                for l in lines[:250]:
                    print(f"  {l}")
                if len(lines) > 250:
                    print(f"  … {len(lines) - 250} additional GA4 output lines omitted.")
        elif rc == 2 and out.strip():
            # pull_ga.py uses exit 2 for "partial" and prints everything it did get; the cycle used to
            # report "failed: exit 2" and drop the tables (and the reason) on the floor.
            lines = out.splitlines()
            for l in lines[:250]:
                print(f"  {l}")
            if len(lines) > 250:
                print(f"  … {len(lines) - 250} additional GA4 output lines omitted.")
            why = next((l.strip(" ⚠️") for l in reversed(lines) if "⚠️" in l), "see the GA4 output above")
            print(f"  ⚠️ GA4 pull partial (exit 2): {why[:160]}")
            partial = True
        else:
            print(f"  ⚠️ GA4 pull failed: {err.strip() or f'exit {rc}'}")
            partial = True
    else:
        print("  ⚠️ GA4 pull unavailable — pull_ga.py not found in skill or store scripts/.")
        partial = True

    # Step 5: Apple demand radar
    print("\n▶ [5/6] Apple demand radar (search popularity, impression share)...")
    radar_py = SKILL_DIR / "scripts" / "radar.py"
    rc, out, err = run_cmd([sys.executable, str(radar_py), "--store", str(store), "pull", "--if-configured"])
    if rc == 0:
        for l in out.splitlines():
            print(f"  {l}")
    else:
        print(f"  ⚠️ Radar pull incomplete (exit {rc}); stored weeks are unchanged for the markets that failed:")
        for l in (out + err).splitlines()[:20]:
            print(f"    {l}")
        partial = True

    # Step 6: Ledger Report
    print("\n▶ [6/6] Generating Hypothesis & Keyword Ledger Report...")
    ledger_py = SKILL_DIR / "scripts" / "ledger.py"
    if ledger_py.exists():
        rc, out, err = run_cmd([sys.executable, str(ledger_py), "--store", str(store), "report"])
        if rc == 0:
            if out.strip():
                print(out)
            else:
                print("  ⚠️ Ledger report returned no output.")
                partial = True
        else:
            print(f"  ⚠️ Ledger report failed: {err.strip() or f'exit {rc}'}")
            partial = True
    else:
        print(f"  ⚠️ Ledger report unavailable — {ledger_py} not found.")
        partial = True

    print("\n=================================================================")
    state = "PARTIAL" if partial else "finished"
    print(f"Cycle command {state}. Review every warning and skipped stage; this footer does not certify data completeness.")
    print("=================================================================")
    return 2 if partial else 0


def build_parser():
    # Common flags inherited by all subcommands
    common_parent = argparse.ArgumentParser(add_help=False)
    common_parent.add_argument("--store", default=argparse.SUPPRESS, help="Path to marketing store directory")
    common_parent.add_argument("--debug", "-d", action="store_true", default=argparse.SUPPRESS, help="Print debug diagnostics to stderr")
    common_parent.add_argument("--info", "-v", action="store_true", default=argparse.SUPPRESS, help="Print informational logs to stderr")
    common_parent.add_argument("--quiet", "-q", action="store_true", default=argparse.SUPPRESS, help="Suppress non-essential output")
    common_parent.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="Format output as JSON where applicable")

    parser = argparse.ArgumentParser(description="Unified CLI for iOS ASO Copilot")
    parser.add_argument("--store", default=str(DEFAULT_STORE), help="Path to marketing store directory")
    parser.add_argument("--debug", "-d", action="store_true", help="Print debug diagnostics to stderr")
    parser.add_argument("--info", "-v", action="store_true", help="Print informational logs to stderr")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress non-essential output")
    parser.add_argument("--json", action="store_true", help="Format output as JSON where applicable")
    parser.add_argument("--self-check", action="store_true", help="check app identity parsing without network access")
    subparsers = parser.add_subparsers(dest="command")

    # info
    subparsers.add_parser("info", help="Diagnostic info and environment report", parents=[common_parent])

    # status
    subparsers.add_parser("status", help="Quick status snapshot", parents=[common_parent])

    # keywords
    p_kw = subparsers.add_parser("keywords", help="Keyword discovery, hints, localization vacuums, and filtering", parents=[common_parent])
    kw_subs = p_kw.add_subparsers(dest="keywords_action")

    p_hint = kw_subs.add_parser("hints", help="Apple App Store autocomplete hints", parents=[common_parent])
    p_hint.add_argument("--term", "-t", required=True, help="Search prefix/term")
    p_hint.add_argument("--country", "-c", "--storefront", default="us", help="Storefront code (e.g. us, pl, jp)")

    p_vac = kw_subs.add_parser("vacuum", help="Audit localization vacuum in storefront", parents=[common_parent])
    p_vac.add_argument("--term", "-t", required=True, help="Keyword query")
    p_vac.add_argument("--country", "-c", required=True, help="Country code (e.g. pl, de, jp)")
    p_vac.add_argument("--limit", type=int, default=20, help="Number of apps to inspect")

    p_pop = kw_subs.add_parser("popularity", help="Apple Ads Search Term Popularity (1-100)", parents=[common_parent])
    p_pop.add_argument("--country", "-c", required=True, help="Country code (e.g. pl, us)")
    p_pop.add_argument("--terms", help="Comma-separated terms to inspect")
    p_pop.add_argument("--genre", help="Genre category (e.g. PHOTO_VIDEO)")

    p_comp = kw_subs.add_parser("competitors", help="Discover competitors from seed terms", parents=[common_parent])
    p_comp.add_argument("--seeds", "-s", required=True, help="Comma-separated seed terms")
    p_comp.add_argument("--country", "-c", default="us", help="Country code (e.g. us, pl)")
    p_comp.add_argument("--limit", type=int, default=25, help="Limit of competitors")

    p_filt = kw_subs.add_parser("filter", help="Deterministic candidate review and export", parents=[common_parent])
    p_filt.add_argument("--input", "-i", required=True, help="Input CSV path")
    p_filt.add_argument("--output", "-o", required=True, help="Output directory")
    p_filt.add_argument("--brand", action="append", default=[], help="Protected brand name(s)")
    p_filt.add_argument("--limit", type=int, default=5000, help="Max candidates ceiling")

    # ads
    p_ads = subparsers.add_parser("ads", help="Manage Apple Ads campaigns, ad groups, and keywords", parents=[common_parent])
    ads_subs = p_ads.add_subparsers(dest="ads_action")

    p_acamp = ads_subs.add_parser("campaigns", aliases=["list"], help="List Apple Ads campaigns", parents=[common_parent])
    p_acamp.add_argument("--status", default="ALL", help="Filter by status (ENABLED, PAUSED, ALL)")
    p_acamp.add_argument("--country", "-c", help="Filter by targeted country")

    p_agrp = ads_subs.add_parser("adgroups", help="List ad groups in campaign", parents=[common_parent])
    p_agrp.add_argument("--campaign-id", help="Campaign ID filter")

    p_akw = ads_subs.add_parser("keywords", help="List targeting keywords", parents=[common_parent])
    p_akw.add_argument("--adgroup-id", help="Ad Group ID filter")
    p_akw.add_argument("--campaign-id", help="Campaign ID filter")

    p_aadd = ads_subs.add_parser("add-keywords", help="Add keywords to ad group", parents=[common_parent])
    p_aadd.add_argument("--adgroup-id", required=True, help="Ad Group ID")
    p_aadd.add_argument("--terms", help="Comma-separated keyword terms")
    p_aadd.add_argument("--file", help="Path to text file with keywords (one per line)")
    p_aadd.add_argument("--bid", default="0.30", help="CPT bid amount in USD (default: 0.30)")
    p_aadd.add_argument("--match-type", default="EXACT", choices=["EXACT", "BROAD"], help="Match type")

    p_apause = ads_subs.add_parser("pause", help="Pause a campaign", parents=[common_parent])
    p_apause.add_argument("--campaign-id", required=True, help="Campaign ID")

    p_aresume = ads_subs.add_parser("resume", help="Resume a campaign", parents=[common_parent])
    p_aresume.add_argument("--campaign-id", required=True, help="Campaign ID")

    # cycle
    subparsers.add_parser("brief", help="One screen: ASC state, Top-200 bands, all hypotheses, store funnel", parents=[common_parent])
    p_cycle = subparsers.add_parser("cycle", help="Run the consolidated data collection pass", parents=[common_parent])
    p_cycle.add_argument("--skip-pull", action="store_true", help="Skip remote ASC funnel download")
    p_cycle.add_argument("--skip-ga", action="store_true", help="Skip GA4 pull")

    # reviews
    p_rev = subparsers.add_parser("reviews", help="Audit and reply to customer reviews", parents=[common_parent])
    p_rev.add_argument("action", choices=["ratings", "unreplied", "list", "respond"], default="ratings", nargs="?")
    p_rev.add_argument("--limit", type=int, default=10, help="Limit for list")
    p_rev.add_argument("--review-id", help="Review ID for response")
    p_rev.add_argument("--response", help="Response text")

    # funnel
    p_fun = subparsers.add_parser("funnel", help="Inspect or pull ASC funnel", parents=[common_parent])
    p_fun.add_argument("--pull", action="store_true", help="Trigger remote ASC pull")

    # ga
    p_ga = subparsers.add_parser("ga", help="Inspect in-app telemetry", parents=[common_parent])
    p_ga.add_argument("--days", type=int, default=14, help="Days window")
    p_ga.add_argument("--property-id", help="GA4 Property ID (numeric)")
    p_ga.add_argument("--credentials", help="Path to service-account.json")
    p_ga.add_argument("--realtime", action="store_true", help="Show events from the last 30 minutes only")
    p_ga.add_argument("--include-debug", action="store_true", help="Include debug / simulator traffic")
    p_ga.add_argument("--export-csv", action="store_true", help="Export funnel metrics to <store>/metrics/ga4_funnel.csv")

    # ledger
    p_led = subparsers.add_parser("ledger", help="Manage hypothesis and keyword ledger", parents=[common_parent])
    p_led.add_argument("ledger_args", nargs=argparse.REMAINDER, help="Arguments passed to ledger.py")

    # radar
    p_rad = subparsers.add_parser("radar", help="Apple demand radar: popularity, impression share, keyword lens",
                                  parents=[common_parent])
    p_rad.add_argument("radar_args", nargs=argparse.REMAINDER, help="Arguments passed to radar.py (pull, report, keywords)")

    # google
    p_goog = subparsers.add_parser("google", help="Google search intelligence: trends, autocomplete hints, and batch volume profiling",
                                   parents=[common_parent])
    goog_subs = p_goog.add_subparsers(dest="google_action")

    p_gtrend = goog_subs.add_parser("trends", help="Compare search interest via Google Trends", parents=[common_parent])
    p_gtrend.add_argument("terms", nargs="+", help="Keywords to compare (up to 5)")
    p_gtrend.add_argument("--country", "-c", default="UA", help="Two-letter country code (default: UA)")
    p_gtrend.add_argument("--timeframe", "-t", default="today 12-m", help="Timeframe (default: today 12-m)")
    p_gtrend.add_argument("--related", action="store_true", help="Fetch top and rising related queries for first term")
    p_gtrend.add_argument("--geo", action="store_true", help="Fetch subregion / oblast interest breakdown")

    p_gsug = goog_subs.add_parser("suggest", help="Live Google search autocomplete hints", parents=[common_parent])
    p_gsug.add_argument("term", help="Root search query or seed word")
    p_gsug.add_argument("--country", "-c", default="UA", help="Two-letter country code (default: UA)")
    p_gsug.add_argument("--lang", "-l", default="uk", help="Language code (default: uk)")
    p_gsug.add_argument("--limit", type=int, default=15, help="Max results (default: 15)")
    p_gsug.add_argument("--matrix", action="store_true", help="Deep multi-angle intent matrix expansion")

    p_gbatch = goog_subs.add_parser("batch", help="Batch relative volume profiling normalized to an anchor keyword", parents=[common_parent])
    p_gbatch.add_argument("--anchor", "-a", required=True, help="Anchor keyword (normalized to 100.0)")
    p_gbatch.add_argument("--terms", help="Comma-separated candidate keywords")
    p_gbatch.add_argument("--file", "-f", help="Path to text or CSV file with candidate keywords")
    p_gbatch.add_argument("--country", "-c", default="UA", help="Two-letter country code (default: UA)")
    p_gbatch.add_argument("--timeframe", "-t", default="today 12-m", help="Timeframe (default: today 12-m)")
    p_gbatch.add_argument("--delay", type=float, default=1.5, help="Polite delay in seconds between batches (default: 1.5)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    set_log_level(
        debug=getattr(args, "debug", False),
        info=getattr(args, "info", False),
        quiet=getattr(args, "quiet", False)
    )

    if args.self_check:
        return self_check()
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "info":
        return cmd_info(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "keywords":
        return cmd_keywords(args)
    elif args.command == "ads":
        return cmd_ads(args)
    elif args.command == "brief":
        return cmd_brief(args)
    elif args.command == "cycle":
        return cmd_cycle(args)
    elif args.command == "reviews":
        return cmd_reviews(args)
    elif args.command == "funnel":
        return cmd_funnel(args)
    elif args.command == "ga":
        return cmd_ga(args)
    elif args.command == "ledger":
        return cmd_ledger(args)
    elif args.command == "radar":
        return cmd_radar(args)
    elif args.command == "google":
        return cmd_google(args)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
