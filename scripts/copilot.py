#!/usr/bin/env python3
"""Unified CLI for iOS ASO Copilot (ios-marketing-ops).

Consolidates multi-step marketing operations into a single entrypoint:
  - copilot cycle: consolidated read/pull pass (versions, reviews, funnel, GA4, ledger)
  - copilot status: quick snapshot of active versions, hypotheses and ratings
  - copilot reviews: check rating histograms and unreplied customer reviews
  - copilot funnel: pull and summarize ASC analytics
  - copilot ga: pull in-app GA4 / Firebase telemetry
  - copilot ledger: delegate to ledger.py (report, refresh, draft, ingest)
"""

import argparse
import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STORE = Path.cwd() / "marketing"


def resolve_app_identity(store: Path):
    """Read App ID, version, and brand tokens from config.md."""
    config_file = store / "config.md"
    if not config_file.is_file():
        raise SystemExit(f"Missing app identity: create {config_file} from assets/store-template/config.md.")

    values = {}
    for line in config_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        for label, key in (("**App ID**:", "app_id"), ("**Version**:", "version"),
                           ("**Brand tokens**:", "brand"), ("**GA4 Property ID**:", "ga4_property_id"),
                           ("**Firebase Property ID**:", "ga4_property_id")):
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
    return {"app_id": app_id, "version": version, "brand": values.get("brand") or store.parent.name,
            "ga4_property_id": property_value if property_value.isdigit() else None}


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
                       "ga4_property_id": None}
        config.write_text("**App ID**: 1234567890\n**Version**: 1.2.3\n**GA4 Property ID**: 234567890\n",
                          encoding="utf-8")
        app = resolve_app_identity(store)
        assert app["ga4_property_id"] == "234567890"
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
                    (0, reviews_output, ""), (0, "GA metrics\n", ""), (0, "ledger\n", "")]
        assert cycle_result(complete)[0] == 0
        partial, output = cycle_result([(0, version_output, ""), (0, ratings_output, ""),
                                        (0, "", ""), (0, "GA metrics\n", ""), (0, "ledger\n", "")])
        assert partial == 2 and "whether there are zero rows is unknown" in output
        empty_ga, output = cycle_result([(0, version_output, ""), (0, ratings_output, ""),
                                         (0, reviews_output, ""), (0, "", ""), (0, "ledger\n", "")])
        assert empty_ga == 2 and "GA4 returned no output" in output
        failed, _ = cycle_result([(1, "", "ASC unavailable"), (0, ratings_output, ""),
                                  (0, reviews_output, ""), (0, "GA metrics\n", ""), (0, "ledger\n", "")])
        assert failed == 2

        ga_args = argparse.Namespace(store=str(store), property_id=None, days=14, credentials=None,
                                     realtime=False, include_debug=False, export_csv=False)
        with patch(f"{__name__}.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            assert cmd_ga(ga_args) == 0
            command = run.call_args.args[0]
            assert command[command.index("--property-id") + 1] == "234567890"

        with patch(f"{__name__}.subprocess.run", return_value=subprocess.CompletedProcess([], 7)):
            assert cmd_reviews(argparse.Namespace(store=str(store), action="ratings")) == 7
    print("OK: app identity, safe funnel paths, and CLI complete/partial/failure semantics")


def run_cmd(args, capture=True, check=False):
    """Run shell command with clean output capture."""
    try:
        res = subprocess.run(args, capture_output=capture, text=True, check=check)
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except Exception as e:
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
    print("▶ [1/5] Verifying App Store Connect Versions...")
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
    print("\n▶ [2/5] Auditing Customer Reviews & Ratings...")
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
    print("\n▶ [3/5] Syncing Funnel Analytics...")
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
    print("\n▶ [4/5] Pulling In-App Telemetry (GA4)...")
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

    # Step 5: Ledger Report
    print("\n▶ [5/5] Generating Hypothesis & Keyword Ledger Report...")
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


def main():
    store_parent = argparse.ArgumentParser(add_help=False)
    store_parent.add_argument("--store", default=str(DEFAULT_STORE), help="Path to marketing store directory")

    parser = argparse.ArgumentParser(description="Unified CLI for iOS ASO Copilot", parents=[store_parent])
    parser.add_argument("--self-check", action="store_true", help="check app identity parsing without network access")
    subparsers = parser.add_subparsers(dest="command")

    # cycle
    p_cycle = subparsers.add_parser("cycle", help="Run the consolidated data collection pass", parents=[store_parent])
    p_cycle.add_argument("--skip-pull", action="store_true", help="Skip remote ASC funnel download")
    p_cycle.add_argument("--skip-ga", action="store_true", help="Skip GA4 pull")

    # status
    subparsers.add_parser("status", help="Quick status snapshot", parents=[store_parent])

    # reviews
    p_rev = subparsers.add_parser("reviews", help="Audit and reply to customer reviews", parents=[store_parent])
    p_rev.add_argument("action", choices=["ratings", "unreplied", "list", "respond"], default="ratings", nargs="?")
    p_rev.add_argument("--limit", type=int, default=10, help="Limit for list")
    p_rev.add_argument("--review-id", help="Review ID for response")
    p_rev.add_argument("--response", help="Response text")

    # funnel
    p_fun = subparsers.add_parser("funnel", help="Inspect or pull ASC funnel", parents=[store_parent])
    p_fun.add_argument("--pull", action="store_true", help="Trigger remote ASC pull")

    # ga
    p_ga = subparsers.add_parser("ga", help="Inspect in-app telemetry", parents=[store_parent])
    p_ga.add_argument("--days", type=int, default=14, help="Days window")
    p_ga.add_argument("--property-id", help="GA4 Property ID (numeric)")
    p_ga.add_argument("--credentials", help="Path to service-account.json")
    p_ga.add_argument("--realtime", action="store_true", help="Show events from the last 30 minutes only")
    p_ga.add_argument("--include-debug", action="store_true", help="Include debug / simulator traffic")
    p_ga.add_argument("--export-csv", action="store_true", help="Export funnel metrics to <store>/metrics/ga4_funnel.csv")

    # ledger
    p_led = subparsers.add_parser("ledger", help="Manage hypothesis and keyword ledger", parents=[store_parent])
    p_led.add_argument("ledger_args", nargs=argparse.REMAINDER, help="Arguments passed to ledger.py")

    args = parser.parse_args()

    if args.self_check:
        return self_check()
    if not args.command:
        parser.print_help()
        return 0

    if args.command == "cycle":
        return cmd_cycle(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "reviews":
        return cmd_reviews(args)
    elif args.command == "funnel":
        return cmd_funnel(args)
    elif args.command == "ga":
        return cmd_ga(args)
    elif args.command == "ledger":
        return cmd_ledger(args)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
