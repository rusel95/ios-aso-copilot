"""Single collectors: reviews and ratings, the store funnel, GA4, telemetry, RevenueCat, ledger, radar."""

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from aso.commands.base import SKILL_DIR, resolve_app_identity, run_cmd


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


def funnel_script(store: Path) -> Path:
    """The collector the funnel is pulled with: the skill's own. Only it folds the daily reports into closed Monday
    weeks, which is all the export shows; a store-local script of the same name is used only if the skill has none."""
    own = SKILL_DIR / "scripts" / "pull_funnel.py"
    return own if own.exists() else store / "scripts" / "pull_funnel.py"


def prepare_funnel_pull(pull_script, store, app_id):
    """Build a safe pull only after verifying the helper identity and raw directory option."""
    store = Path(store).resolve()
    pull_script = Path(pull_script).resolve()
    skill_pull = (SKILL_DIR / "scripts" / "pull_funnel.py").resolve()
    is_skill_helper = pull_script == skill_pull

    if not is_skill_helper:
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
    if "--app" in help_text:
        command.extend(["--app", str(app_id)])
    return command, raw_dir, ""


def cmd_reviews(args):
    """Inspect App Store reviews and ratings. Reading only: the reply is `cmd_reviews_respond` in ads_actions."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    app_id = app["app_id"]

    if args.action == "ratings":
        result = subprocess.run(["asc", "reviews", "ratings", "--app", app_id, "--all"])
    elif args.action == "unreplied":
        result = subprocess.run(["asc", "reviews", "--app", app_id, "--only-unresponded"])
    elif args.action == "list":
        result = subprocess.run(["asc", "reviews", "--app", app_id, "--limit", str(args.limit)])
    else:
        raise SystemExit(f"reviews {args.action}: not a read. A reply goes through aso.commands.ads_actions.")
    return result.returncode


def cmd_funnel(args):
    """Pull or summarize App Store Connect Funnel Analytics."""
    store = Path(args.store).resolve()
    pull_script = funnel_script(store)

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
        
        channel_segs = {"search", "browse", "web_referrer", "app_referrer"}
        channel_rows = [r for r in latest_rows if r.get("segment") in channel_segs or (r.get("segment") or "").startswith("other_")]
        
        if all_row:
            total_imp = int(all_row.get('impressions') or 0)
            total_pv = int(all_row.get('product_page_views') or 0)
            total_dl = int(all_row.get('downloads') or 0)
            cvr = all_row.get('cvr_pct') or (f"{100.0 * total_dl / total_pv:.1f}" if total_pv else "—")
        else:
            total_imp = sum(int(r.get('impressions') or 0) for r in channel_rows)
            total_pv = sum(int(r.get('product_page_views') or 0) for r in channel_rows)
            total_dl = sum(int(r.get('downloads') or 0) for r in channel_rows)
            cvr = f"{100.0 * total_dl / total_pv:.1f}" if total_pv else "—"

        print(f"\n📊 ASC Funnel Summary (Latest snapshot: {latest_rec})")
        print(f"  Total Impressions:  {total_imp:,}")
        print(f"  Product Page Views: {total_pv:,}")
        print(f"  Downloads (first):  {total_dl:,}")
        print(f"  Conversion Rate:    {cvr}%")
        if all_row and all_row.get('trial_starts'):
            print(f"  Trial Starts:       {all_row.get('trial_starts')}")

        if channel_rows:
            print("\nAcquisition Channels:")
            for r in channel_rows:
                seg = r.get("segment", "")
                imp = r.get('impressions') or "0"
                pv = r.get('product_page_views') or "0"
                dl = r.get('downloads') or "0"
                cvr_p = r.get('cvr_pct') or (f"{100.0 * int(dl) / int(pv):.1f}%" if int(pv) else "—")
                print(f"  {seg.upper():<16}: {imp:>6} imp, {pv:>4} views, {dl:>3} dl (CVR: {cvr_p})")

        territories = [r for r in latest_rows if len(r.get("segment") or "") == 2]
        if territories:
            print("\nTop Storefronts:")
            for r in sorted(territories, key=lambda x: int(x.get('impressions') or 0), reverse=True)[:10]:
                print(f"  {r['segment'].upper():<4}: {r.get('impressions', '0'):>6} imp, {r.get('product_page_views', '0'):>4} views, {r.get('downloads', '0'):>3} dl")

        print_lifecycle(store / "metrics" / "lifecycle.csv")
        return 0


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


def cmd_telemetry(args):
    """Pull BigQuery in-depth product telemetry (funnel, core engine, retention, paywall)."""
    store = Path(args.store).resolve()
    script = SKILL_DIR / "scripts" / "pull_bigquery_telemetry.py"
    if not script.exists():
        script = store / "scripts" / "pull_bigquery_telemetry.py"
    if not script.exists():
        print(f"BigQuery telemetry script not found at {script}")
        return 2

    cmd = [sys.executable, str(script), "--store", str(store), "--days", str(args.days)]
    if getattr(args, "export_md", False):
        cmd.append("--export-md")
    if getattr(args, "export_json", False):
        cmd.append("--export-json")

    return subprocess.run(cmd).returncode


def cmd_rc(args):
    """Pull RevenueCat metrics, 3-tier revenue (Gross, Net Tax, Proceeds), and Apple Ads Cashflow."""
    store = Path(args.store).resolve()
    script = SKILL_DIR / "scripts" / "pull_revenuecat.py"
    if not script.exists():
        script = store / "scripts" / "pull_revenuecat.py"
    if not script.exists():
        print(f"RevenueCat pull script not found at {script}")
        return 2

    cmd = [sys.executable, str(script), "--store", str(store)]
    if getattr(args, "project_id", None):
        cmd.extend(["--project-id", args.project_id])
    if getattr(args, "start", None):
        cmd.extend(["--start", args.start])
    if getattr(args, "end", None):
        cmd.extend(["--end", args.end])
    if getattr(args, "json", False):
        cmd.append("--json")
    if getattr(args, "export", False):
        cmd.append("--export")

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


def fetch_lookup(app_id: str, timeout: int = 15):
    """The public store lookup of the app: the version it shows now and the day that version was released.
    None when it cannot be read; the caller says so and goes on."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"https://itunes.apple.com/lookup?id={app_id}", timeout=timeout) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
