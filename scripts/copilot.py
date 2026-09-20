#!/usr/bin/env python3
"""Unified CLI for iOS ASO Copilot (ios-marketing-ops).

Consolidates multi-step marketing operations into a single entrypoint:
  - copilot cycle: full end-to-end audit (versions, reviews, funnel, GA4, ledger)
  - copilot status: quick snapshot of active versions, hypotheses and ratings
  - copilot reviews: check rating histograms and unreplied customer reviews
  - copilot funnel: pull and summarize ASC analytics
  - copilot ga: pull in-app GA4 / Firebase telemetry
  - copilot ledger: delegate to ledger.py (report, refresh, draft, ingest)
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_STORE = Path.cwd() / "marketing"


def resolve_app_identity(store: Path):
    """Read App ID, version, and brand tokens from config.md."""
    config_file = store / "config.md"
    app_id = "6449785515"
    version = "1.5.5"
    brand = "hush"
    if config_file.exists():
        for line in config_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("**App ID**:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "TODO":
                    app_id = val.split()[0]
            elif line.startswith("**Version**:"):
                val = line.split(":", 1)[1].strip()
                if val and val != "TODO":
                    version = val.split()[0]
            elif line.startswith("**Brand tokens**:"):
                val = line.split(":", 1)[1].strip()
                if val:
                    brand = val
    return {"app_id": app_id, "version": version, "brand": brand}


def run_cmd(args, capture=True, check=False):
    """Run shell command with clean output capture."""
    try:
        res = subprocess.run(args, capture_output=capture, text=True, check=check)
        return res.returncode, res.stdout, res.stderr
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except Exception as e:
        return -1, "", str(e)


def cmd_status(args):
    """Quick high-level snapshot."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)

    print(f"\n📱 Hush Marketing Status · Store: {store}")
    print(f"App ID: {app['app_id']} · Working Version: {app['version']}\n")

    # 1. Version check via asc
    print("--- 1. App Store Versions ---")
    rc, out, _ = run_cmd(["asc", "versions", "list", "--app", app["app_id"], "--platform", "IOS"])
    if rc == 0:
        print(out.strip())
    else:
        print("  (Could not query asc versions list)")

    # 2. Ratings summary
    print("\n--- 2. App Store Ratings ---")
    rc, out, _ = run_cmd(["asc", "reviews", "ratings", "--app", app["app_id"], "--all"])
    if rc == 0:
        for line in out.splitlines()[:15]:
            print(f"  {line}")
    else:
        print("  (Could not query asc reviews ratings)")

    # 3. Ledger summary
    ledger_py = SKILL_DIR / "scripts" / "ledger.py"
    if ledger_py.exists():
        print("\n--- 3. Hypothesis Ledger ---")
        rc, out, _ = run_cmd([sys.executable, str(ledger_py), "--store", str(store), "report"])
        if rc == 0:
            for line in out.splitlines():
                if line.startswith("## B ·") or line.startswith("| Market | Key |"):
                    break
                print(line)


def cmd_reviews(args):
    """Inspect and manage App Store reviews and ratings."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    app_id = app["app_id"]

    if args.action == "ratings":
        subprocess.run(["asc", "reviews", "ratings", "--app", app_id, "--all"])
    elif args.action == "unreplied":
        subprocess.run(["asc", "reviews", "--app", app_id, "--only-unresponded"])
    elif args.action == "list":
        subprocess.run(["asc", "reviews", "--app", app_id, "--limit", str(args.limit)])
    elif args.action == "respond":
        if not args.review_id or not args.response:
            print("Error: --review-id and --response are required for respond action.")
            sys.exit(1)
        subprocess.run(["asc", "reviews", "respond", "--review-id", args.review_id, "--response", args.response])


def cmd_funnel(args):
    """Pull or summarize App Store Connect Funnel Analytics."""
    store = Path(args.store).resolve()
    pull_script = store / "scripts" / "pull_funnel.py"
    if not pull_script.exists():
        pull_script = SKILL_DIR / "scripts" / "pull_funnel.py"

    if args.pull:
        print(f"Pulling ASC funnel analytics into {store / 'metrics'}...")
        subprocess.run([sys.executable, str(pull_script), "--out", str(store / "metrics")])
    else:
        # Display latest summary from weekly.csv
        weekly_csv = store / "metrics" / "weekly.csv"
        if not weekly_csv.exists():
            print(f"No {weekly_csv} found. Run with --pull first.")
            return
        import csv
        with weekly_csv.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            print("weekly.csv is empty.")
            return
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
        print("\nTop Storefronts:")
        for r in latest_rows:
            seg = r.get("segment")
            if seg != "all":
                print(f"  {seg.upper()}: {r.get('impressions')} imp, {r.get('product_page_views')} views, {r.get('downloads')} dl (CVR: {r.get('cvr_pct')}%)")


def cmd_ga(args):
    """Pull Google Analytics 4 in-app telemetry."""
    store = Path(args.store).resolve()
    ga_script = SKILL_DIR / "scripts" / "pull_ga.py"
    if not ga_script.exists():
        ga_script = store / "scripts" / "pull_ga.py"

    if not ga_script.exists():
        print(f"GA4 pull script not found at {ga_script}")
        return

    # Use project .venv if available
    venv_py = Path.cwd() / ".venv" / "bin" / "python"
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    cmd = [py_exec, str(ga_script), "--store", str(store), "--days", str(args.days)]
    if getattr(args, "property_id", None):
        cmd.extend(["--property-id", args.property_id])
    if getattr(args, "credentials", None):
        cmd.extend(["--credentials", args.credentials])
    if getattr(args, "realtime", False):
        cmd.append("--realtime")
    if getattr(args, "include_debug", False):
        cmd.append("--include-debug")
    if getattr(args, "export_csv", False):
        cmd.append("--export-csv")

    subprocess.run(cmd)


def cmd_ledger(args):
    """Delegate to ledger.py."""
    store = Path(args.store).resolve()
    ledger_py = SKILL_DIR / "scripts" / "ledger.py"
    if not ledger_py.exists():
        print(f"ledger.py not found at {ledger_py}")
        sys.exit(1)
    forward_args = [sys.executable, str(ledger_py), "--store", str(store)] + args.ledger_args
    subprocess.run(forward_args)


def cmd_cycle(args):
    """Run full marketing copilot iteration."""
    store = Path(args.store).resolve()
    app = resolve_app_identity(store)
    app_id = app["app_id"]

    print("=================================================================")
    print(f"🚀 Hush Marketing Full Iteration Cycle · {store}")
    print(f"App ID: {app_id} · Version: {app['version']}")
    print("=================================================================\n")

    # Step 1: Reconcile versions
    print("▶ [1/5] Verifying App Store Connect Versions...")
    rc, out, _ = run_cmd(["asc", "versions", "list", "--app", app_id, "--platform", "IOS"])
    if rc == 0:
        lines = out.strip().splitlines()
        for l in lines[:5]:
            print(f"  {l}")
    else:
        print("  ⚠️ Could not query ASC versions.")

    # Step 2: Reviews & Ratings
    print("\n▶ [2/5] Auditing Customer Reviews & Ratings...")
    rc, out, _ = run_cmd(["asc", "reviews", "ratings", "--app", app_id, "--all"])
    if rc == 0:
        for l in out.strip().splitlines():
            if "GLOBAL:" in l or "Country" in l or "Ukraine" in l or "Poland" in l:
                print(f"  {l}")
    rc, out, _ = run_cmd(["asc", "reviews", "--app", app_id, "--only-unresponded"])
    if rc == 0 and "Created" in out:
        unreplied_count = len([l for l in out.splitlines() if "UKR" in l or "POL" in l or "USA" in l])
        print(f"  📝 Unreplied customer reviews: {unreplied_count}")
    else:
        print("  📝 Unreplied customer reviews: 0")

    # Step 3: Funnel metrics
    print("\n▶ [3/5] Syncing Funnel Analytics...")
    pull_script = store / "scripts" / "pull_funnel.py"
    if not pull_script.exists():
        pull_script = SKILL_DIR / "scripts" / "pull_funnel.py"
    if pull_script.exists() and not args.skip_pull:
        print("  Running pull_funnel.py (ASC analytics reporting is not real-time — this can take "
              "several minutes for a storefront with many tracked keywords)...")
        # Previously this used stdout=subprocess.DEVNULL, which suppressed ALL output — including
        # progress — until the whole (genuinely slow) ASC pull finished. That made a normal,
        # multi-minute pull indistinguishable from a frozen process; an operator watching the cycle
        # had no signal to tell the two apart except killing it and finding out the hard way.
        rc = subprocess.run([sys.executable, str(pull_script), "--out", str(store / "metrics")]).returncode
        if rc == 0:
            print("  ✓ Funnel metrics updated.")
        else:
            print(f"  ⚠️ pull_funnel.py exited with code {rc}; funnel metrics may be stale.")
    else:
        print("  (Skipping remote funnel pull — pull_funnel.py not found in store or skill scripts/)")

    # Step 4: GA4 Telemetry
    print("\n▶ [4/5] Pulling In-App Telemetry (GA4)...")
    ga_script = SKILL_DIR / "scripts" / "pull_ga.py"
    if not ga_script.exists():
        ga_script = store / "scripts" / "pull_ga.py"
    venv_py = Path.cwd() / ".venv" / "bin" / "python"
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    if ga_script.exists() and not args.skip_ga:
        rc, out, _ = run_cmd([py_exec, str(ga_script), "--store", str(store), "--days", "14"])
        if rc == 0:
            for l in out.splitlines()[:15]:
                print(f"  {l}")
        else:
            print("  ⚠️ GA4 script returned non-zero.")
    else:
        print("  (Skipping GA4 pull)")

    # Step 5: Ledger Report
    print("\n▶ [5/5] Generating Hypothesis & Keyword Ledger Report...")
    ledger_py = SKILL_DIR / "scripts" / "ledger.py"
    if ledger_py.exists():
        rc, out, _ = run_cmd([sys.executable, str(ledger_py), "--store", str(store), "report"])
        if rc == 0:
            print(out)
        else:
            print("  ⚠️ Ledger report failed.")

    print("\n=================================================================")
    print("✅ Iteration cycle completed. Review findings and update STATE.md.")
    print("=================================================================")


def main():
    store_parent = argparse.ArgumentParser(add_help=False)
    store_parent.add_argument("--store", default=str(DEFAULT_STORE), help="Path to marketing store directory")

    parser = argparse.ArgumentParser(description="Unified CLI for iOS ASO Copilot", parents=[store_parent])
    subparsers = parser.add_subparsers(dest="command")

    # cycle
    p_cycle = subparsers.add_parser("cycle", help="Run full marketing audit cycle", parents=[store_parent])
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

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "cycle":
        cmd_cycle(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "reviews":
        cmd_reviews(args)
    elif args.command == "funnel":
        cmd_funnel(args)
    elif args.command == "ga":
        cmd_ga(args)
    elif args.command == "ledger":
        cmd_ledger(args)


if __name__ == "__main__":
    main()
