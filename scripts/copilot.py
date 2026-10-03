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
import subprocess
import sys
import tempfile
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
        partial, output = cycle_result([(0, version_output, ""), (0, ratings_output, ""),
                                        (0, "", ""), (0, "GA metrics\n", ""), (0, "radar\n", ""), (0, "ledger\n", "")])
        assert partial == 2 and "whether there are zero rows is unknown" in output
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
    print("OK: app identity, safe funnel paths, and CLI complete/partial/failure semantics")


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


def cmd_cycle(args):
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
            rc = subprocess.run(command).returncode
            if rc == 0:
                print("  ✓ Funnel metrics updated.")
            else:
                print(f"  ⚠️ pull_funnel.py exited with code {rc}; funnel metrics may be stale.")
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
                for l in lines[:80]:
                    print(f"  {l}")
                if len(lines) > 80:
                    print(f"  … {len(lines) - 80} additional GA4 output lines omitted.")
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
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
