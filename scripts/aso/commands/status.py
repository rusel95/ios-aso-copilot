"""Read-only pictures of the app: status, info, brief."""

import datetime as dt
import json
import sys
from pathlib import Path

from aso.commands.base import SKILL_DIR, compact_asc_output, log_info, resolve_app_identity, run_cmd
from aso.commands.charts import fetch_category_chart, find_app_in_chart
from aso.commands.cycle import cashflow_digest, funnel_digest


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

    # 4. App Store Category Charts
    print("\n--- 4. App Store Category Charts ---")
    try:
        apps, err = fetch_category_chart("ua", 6002, limit=100, timeout=3.0)
        if not err and apps:
            match = find_app_in_chart(apps, app["app_id"], app["brand"])
            if match:
                print(f"  🎉 {app['brand']} is #{match['rank']} in Top Free Utilities [UA]!")
            else:
                th = apps[-1] if apps else None
                th_name = f"#{th['rank']} {th['name']} by {th['developer']}" if th else "no entries"
                print(f"  Not in Top 100 Utilities [UA] (Threshold: {th_name}). Run 'copilot charts' for details.")
        else:
            print(f"  Category chart query unavailable ({err or 'no data'}).")
    except Exception as exc:
        print(f"  Category chart query skipped ({exc}).")

    # 5. RevenueCat & Cashflow digest (from cached snapshot or config)
    cashflow_digest(store, refresh=False)

    return 2 if partial else 0


def cmd_info(args):
    """Print complete diagnostic information about environment, app identity, Apple Ads, and store state."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)

    log_info(f"Gathering environment and app info for store: {store}")

    info_data = {
        "skill": {
            "name": "ios-aso-copilot",
            "version": "2.11.0",
            "path": str(SKILL_DIR),
        },
        "app": {
            "brand": app["brand"],
            "app_id": app["app_id"],
            "version": app["version"],
            "ga4_property_id": app["ga4_property_id"],
            "rc_project_id": app.get("rc_project_id"),
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

    rc_code, rc_out, _ = run_cmd(["rc", "--version"])
    info_data["system"]["rc"] = rc_out.strip() if rc_code == 0 else "not found or error"

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
    print(f"  RevenueCat ID:     {app.get('rc_project_id') or '(none)'}")
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
    print(f"  rc CLI:            {info_data['system']['rc']}")
    print(f"  Git:               {branch} ({commit})")
    print("=================================================================")
    return 0


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
    cashflow_digest(store, refresh=False)
    return 0
