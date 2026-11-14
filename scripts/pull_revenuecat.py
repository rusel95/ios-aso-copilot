#!/usr/bin/env python3
"""Pull live RevenueCat metrics, 3-tier revenue (Gross, Net of Taxes, Proceeds),
and join with Apple Search Ads spend to compute real Cashflow & ROAS.

Supports:
  - Overview KPIs (Active Subscriptions, Active Trials, MRR, 28d Revenue, New Customers)
  - Transaction-level & Country-level breakdown across:
      1. Gross Revenue (`revenue` — customer price paid in App Store)
      2. Net of Taxes (`revenue_net_of_taxes` — after VAT/GST)
      3. Developer Proceeds (`proceeds` — net cash after Apple 15%/30% commission)
  - Product breakdown (Monthly, Yearly, Lifetime)
  - Cashflow & ROAS reconciliation:
      * Active Apple Ads Flights (Flight 1, Flight 2, Combined active market window)
      * Rolling windows (Last 14d, Last 28d, All-Time)
      * Country-by-Country Cashflow (Proceeds - Ad Spend)
"""

import argparse
import csv
import datetime as dt
import json
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from aso.pull_revenuecat_series import ads_weeks, cashflow_weeks, store_series  # noqa: E402
from aso.store_state import first_release_day  # noqa: E402,F401
from aso.pull_revenuecat_fetch import (  # noqa: E402,F401
    CODE_TO_COUNTRY_NAME,
    COUNTRY_NAME_TO_CODE,
    fetch_apple_ads_spend,
    fetch_rc_overview,
    fetch_rc_revenue_series,
    fetch_rc_trials_and_mrr,
    find_bin,
    rc_api_get,
    run_json_cmd,
)


def resolve_config(store: Path):
    config_file = store / "config.md"
    cfg = {
        "app_id": None,
        "brand": store.parent.name,
        "rc_project_id": None,
        "ads_account": None,
        "ads_profile": None,
    }
    if not config_file.is_file():
        return cfg
    for line in config_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        for label, key in (
            ("**App ID**:", "app_id"),
            ("**Brand tokens**:", "brand"),
            ("**RevenueCat Project ID**:", "rc_project_id"),
            ("**Apple Ads account**:", "ads_account"),
            ("**Apple Ads profile**:", "ads_profile"),
        ):
            if s.startswith(label):
                val = s.split(":", 1)[1].strip()
                if val and not val.upper().startswith("TODO"):
                    cfg[key] = val.split()[0] if key != "ads_profile" else val
    return cfg


def aggregate_window(start_str: str, end_str: str, by_country_daily: dict, trials_by_country: dict, daily_spend: dict, country_filter: str = None):
    """Aggregate RevenueCat Gross/NetTax/Proceeds and Apple Ads Spend within [start_str, end_str]."""
    gross = 0.0
    net_tax = 0.0
    proceeds = 0.0
    tx = 0
    trials = 0
    spend = 0.0
    impr = 0
    taps = 0

    cf = country_filter.upper() if country_filter else None

    for (d_str, code, _), vals in by_country_daily.items():
        if start_str <= d_str <= end_str and (not cf or code == cf):
            gross += vals["gross"]
            net_tax += vals["net_tax"]
            proceeds += vals["proceeds"]
            tx += vals["tx"]

    for (d_str, code, _), count in trials_by_country.items():
        if start_str <= d_str <= end_str and (not cf or code == cf):
            trials += count

    for (d_str, _, code), vals in daily_spend.items():
        if start_str <= d_str <= end_str and (not cf or code == cf):
            spend += vals["spend"]
            impr += vals["impressions"]
            taps += vals["taps"]

    net_cashflow = proceeds - spend
    gross_cashflow = gross - spend
    net_roas = (proceeds / spend * 100.0) if spend > 0 else None
    gross_roas = (gross / spend * 100.0) if spend > 0 else None

    return {
        "start": start_str,
        "end": end_str,
        "country": cf or "ALL",
        "transactions": tx,
        "new_trials": trials,
        "gross_revenue": round(gross, 2),
        "net_of_taxes": round(net_tax, 2),
        "proceeds": round(proceeds, 2),
        "ad_spend": round(spend, 2),
        "impressions": impr,
        "taps": taps,
        "gross_cashflow": round(gross_cashflow, 2),
        "net_cashflow": round(net_cashflow, 2),
        "gross_roas_pct": round(gross_roas, 1) if gross_roas is not None else None,
        "net_roas_pct": round(net_roas, 1) if net_roas is not None else None,
    }


def history_start(lookup, today: dt.date) -> str:
    """Where a pull of the whole history begins: the app's first release day, or a year back when the lookup is silent."""
    return first_release_day(lookup) or (today - dt.timedelta(days=365)).isoformat()


def default_start(cfg: dict, today: dt.date) -> str:
    from aso.commands.collect import fetch_lookup
    return history_start(fetch_lookup(cfg["app_id"]) if cfg.get("app_id") else None, today)


def collect_ads(store: Path, start_date: str = None, end_date: str = None):
    """Apple Ads results by closed week for a store with no subscription provider -> (rows for ads.csv, error)."""
    cfg = resolve_config(store)
    if not cfg.get("ads_account"):
        return None, f"Missing **Apple Ads account**: in {store / 'config.md'}"
    today = dt.date.today()
    end_str = end_date or today.isoformat()
    _, _, daily_spend = fetch_apple_ads_spend(find_bin("asc"), cfg.get("ads_account"), cfg.get("ads_profile"),
                                              start_date or default_start(cfg, today), end_str, app_id=cfg.get("app_id"))
    # an app that never ran an ad has no rows: nothing to store, and not a failure
    return ads_weeks(daily_spend, dt.date.fromisoformat(end_str), end_str), None


def collect_revenuecat_and_cashflow(store: Path, project_id_override: str = None, start_date: str = None, end_date: str = None):
    cfg = resolve_config(store)
    project_id = project_id_override or cfg.get("rc_project_id")
    if not project_id:
        return None, f"Missing **RevenueCat Project ID**: in {store / 'config.md'}"

    rc_bin = find_bin("rc")
    asc_bin = find_bin("asc")
    today = dt.date.today()
    end_str = end_date or today.isoformat()
    start_date = start_date or default_start(cfg, today)

    overview, err = fetch_rc_overview(rc_bin, project_id)
    if err:
        return None, f"RevenueCat CLI error: {err}"

    by_country_daily, by_product_daily = fetch_rc_revenue_series(rc_bin, project_id, start_date, end_str)
    trials_by_country, mrr_by_country, attr_campaigns = fetch_rc_trials_and_mrr(rc_bin, project_id, start_date, end_str)
    campaigns_meta, all_campaign_rows, daily_spend = fetch_apple_ads_spend(
        asc_bin, cfg.get("ads_account"), cfg.get("ads_profile"), start_date, end_str, app_id=cfg.get("app_id")
    )

    # Build transaction ledger (chronological)
    tx_ledger = []
    for (d_str, code, cname), vals in sorted(by_country_daily.items()):
        # Match product on same date if possible
        prods = [pname.split(" (")[0] for (pd_str, pname), pvals in by_product_daily.items() if pd_str == d_str]
        tx_ledger.append({
            "date": d_str,
            "country_code": code,
            "country": cname,
            "products": ", ".join(prods) if prods else "Subscription",
            "transactions": vals["tx"],
            "gross_revenue": round(vals["gross"], 2),
            "net_of_taxes": round(vals["net_tax"], 2),
            "proceeds": round(vals["proceeds"], 2),
        })

    # Build product summary
    product_summary = {}
    for (_, pname), vals in by_product_daily.items():
        short_name = pname.split(" (")[0]
        p = product_summary.setdefault(short_name, {"transactions": 0, "gross": 0.0, "net_tax": 0.0, "proceeds": 0.0})
        p["transactions"] += vals["tx"]
        p["gross"] = round(p["gross"] + vals["gross"], 2)
        p["net_tax"] = round(p["net_tax"] + vals["net_tax"], 2)
        p["proceeds"] = round(p["proceeds"] + vals["proceeds"], 2)

    # Build country cashflow table (all-time in range)
    all_countries = set()
    for (_, code, _) in by_country_daily.keys():
        all_countries.add(code)
    for (_, code, _) in trials_by_country.keys():
        all_countries.add(code)
    for r in all_campaign_rows:
        if r["spend"] > 0 or not r["deleted"]:
            all_countries.add(r["country"])

    country_cashflow = []
    for code in sorted(all_countries):
        w = aggregate_window(start_date, end_str, by_country_daily, trials_by_country, daily_spend, country_filter=code)
        cname = CODE_TO_COUNTRY_NAME.get(code, code)
        w["country_name"] = cname
        w["mrr"] = round(mrr_by_country.get(cname, 0.0), 2)
        country_cashflow.append(w)

    country_cashflow.sort(key=lambda x: (x["proceeds"], x["ad_spend"]), reverse=True)

    # Windows analysis:
    d_14 = (today - dt.timedelta(days=14)).isoformat()
    d_28 = (today - dt.timedelta(days=28)).isoformat()
    windows = {
        "last_14d_global": aggregate_window(d_14, end_str, by_country_daily, trials_by_country, daily_spend),
        "last_28d_global": aggregate_window(d_28, end_str, by_country_daily, trials_by_country, daily_spend),
        "all_time_global": aggregate_window(start_date, end_str, by_country_daily, trials_by_country, daily_spend),
    }

    # Active / Non-deleted campaign flight evaluations
    flight_evaluations = []
    non_deleted = [c for c in all_campaign_rows if not c["deleted"]]
    non_deleted.sort(key=lambda x: x.get("start_time") or "")
    for c in non_deleted:
        cid = c["campaign_id"]
        c_start = c.get("start_time") or start_date
        c_end = c.get("end_time") or end_str
        c_country = c["country"]
        # Calculate RC revenue in that country during [c_start, c_end]
        w = aggregate_window(c_start, c_end, by_country_daily, trials_by_country, daily_spend, country_filter=c_country)
        # Override ad_spend with exact campaign spend
        c_spend = round(c["spend"], 2)
        net_cf = round(w["proceeds"] - c_spend, 2)
        gross_cf = round(w["gross_revenue"] - c_spend, 2)
        flight_evaluations.append({
            "campaign_id": cid,
            "name": c["name"],
            "status": c["status"],
            "country": c_country,
            "start": c_start,
            "end": c_end,
            "impressions": c["impressions"],
            "taps": c["taps"],
            "ad_spend": c_spend,
            "new_trials": w["new_trials"],
            "transactions": w["transactions"],
            "gross_revenue": w["gross_revenue"],
            "net_of_taxes": w["net_of_taxes"],
            "proceeds": w["proceeds"],
            "gross_cashflow": gross_cf,
            "net_cashflow": net_cf,
            "gross_roas_pct": round(w["gross_revenue"] / c_spend * 100.0, 1) if c_spend > 0 else None,
            "net_roas_pct": round(w["proceeds"] / c_spend * 100.0, 1) if c_spend > 0 else None,
        })

    # Combined active country window (e.g. UA from earliest non-deleted campaign start to today)
    by_active_country = {}
    for f in flight_evaluations:
        cc = f["country"]
        grp = by_active_country.setdefault(cc, {"starts": [], "spend": 0.0, "impr": 0, "taps": 0})
        if f["start"]:
            grp["starts"].append(f["start"])
        grp["spend"] += f["ad_spend"]
        grp["impr"] += f["impressions"]
        grp["taps"] += f["taps"]

    combined_active_markets = []
    for cc, grp in by_active_country.items():
        earliest = min(grp["starts"]) if grp["starts"] else d_28
        w = aggregate_window(earliest, end_str, by_country_daily, trials_by_country, daily_spend, country_filter=cc)
        combined_active_markets.append(w)

    result = {
        "captured_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_id": project_id,
        "period": {"start": start_date, "end": end_str},
        "overview": overview,
        "mrr_by_country": mrr_by_country,
        "rc_attribution_campaigns_populated": bool(attr_campaigns),
        "product_summary": product_summary,
        "transactions_ledger": tx_ledger,
        "flight_evaluations": flight_evaluations,
        "combined_active_markets": combined_active_markets,
        "windows": windows,
        "country_cashflow": country_cashflow,
        # closed Monday weeks, as rows: what the store keeps as history (export_snapshots appends them)
        "weekly_cashflow": cashflow_weeks(by_country_daily, trials_by_country, daily_spend, dt.date.fromisoformat(end_str), end_str),
        "weekly_ads": ads_weeks(daily_spend, dt.date.fromisoformat(end_str), end_str),
    }
    return result, ""


def print_cashflow_report(data: dict):
    ov = data.get("overview", {})
    active_subs = ov.get("active_subscriptions", {}).get("value", 0)
    active_trials = ov.get("active_trials", {}).get("value", 0)
    mrr = ov.get("mrr", {}).get("value", 0)
    rev_28d = ov.get("revenue", {}).get("value", 0)
    new_cust = ov.get("new_customers", {}).get("value", 0)
    act_users = ov.get("active_users", {}).get("value", 0)

    print("\n==================================================================================")
    print(f"💰 REVENUECAT & CASHFLOW REPORT · Project {data['project_id']} · {data['period']['start']} → {data['period']['end']}")
    print("==================================================================================")
    print(f"  Active Paid Subscriptions: {active_subs}   | Active Free Trials: {active_trials}   | Live MRR: ${mrr}")
    print(f"  Last 28d Gross Revenue:    ${rev_28d}  | 28d New Customers:  {new_cust} | 28d Active Users: {act_users}")
    if data.get("mrr_by_country"):
        mrr_parts = [f"{k}: ${v:.2f}" for k, v in data["mrr_by_country"].items() if v > 0]
        if mrr_parts:
            print(f"  MRR by Storefront:         {', '.join(mrr_parts)}")

    if not data.get("rc_attribution_campaigns_populated"):
        print("  ℹ️  Note: RevenueCat 'attribution_campaign' is unpopulated ('No campaign'). Upload Apple Search Ads")
        print("     API credentials in RevenueCat → Project Settings → Attribution → Apple Search Ads to resolve")
        print("     campaign IDs inside RC charts (BigQuery already resolves them via traffic_source.name).")

    print("\n--- 1. Product Revenue Breakdown (Gross vs Net of Taxes vs Developer Proceeds) ---")
    print(f"  {'Product':<20} {'Tx':>4} {'Gross ($)':>11} {'Net Tax ($)':>13} {'Proceeds / Чистими ($)':>24} {'Avg Proceeds/Tx':>16}")
    print("  " + "-" * 92)
    tot_tx = 0
    tot_g = tot_nt = tot_p = 0.0
    for pname, p in sorted(data.get("product_summary", {}).items(), key=lambda x: x[1]["proceeds"], reverse=True):
        tx = p["transactions"]
        g, nt, pr = p["gross"], p["net_tax"], p["proceeds"]
        avg_p = pr / tx if tx else 0.0
        tot_tx += tx
        tot_g += g
        tot_nt += nt
        tot_p += pr
        print(f"  {pname:<20} {tx:>4d} {f'${g:.2f}':>11} {f'${nt:.2f}':>13} {f'${pr:.2f}':>24} {f'${avg_p:.2f}':>16}")
    print("  " + "-" * 92)
    print(f"  {'TOTAL':<20} {tot_tx:>4d} {f'${tot_g:.2f}':>11} {f'${tot_nt:.2f}':>13} {f'${tot_p:.2f}':>24}")

    print("\n--- 2. Chronological Transaction Ledger (RevenueCat Exact Figures) ---")
    print(f"  {'Date':<12} {'Storefront':<14} {'Product(s)':<26} {'Tx':>3} {'Gross ($)':>10} {'Net Tax ($)':>12} {'Proceeds ($)':>13}")
    print("  " + "-" * 94)
    for row in data.get("transactions_ledger", []):
        st_label = f"{row['country_code']} ({row['country']})"
        g_s = f"${row['gross_revenue']:.2f}"
        nt_s = f"${row['net_of_taxes']:.2f}"
        pr_s = f"${row['proceeds']:.2f}"
        print(f"  {row['date']:<12} {st_label:<14} {row['products'][:26]:<26} {row['transactions']:>3d} "
              f"{g_s:>10} {nt_s:>12} {pr_s:>13}")

    if data.get("flight_evaluations"):
        print("\n--- 3. Active Apple Ads Flights & Market Cashflow (Proceeds vs Ad Spend) ---")
        print(f"  {'Flight / Window':<36} {'Period':<23} {'Spend':>8} {'Trials':>6} {'Tx':>3} {'Gross':>8} {'Proceeds':>9} {'Net Cashflow':>13} {'Net ROAS':>9}")
        print("  " + "-" * 122)
        for f in data["flight_evaluations"]:
            label = f"[{f['country']}] {f['name'][:28]} ({f['status']})"
            per = f"{f['start']}→{f['end']}"
            roas_s = f"{f['net_roas_pct']:.0f}%" if f["net_roas_pct"] is not None else "—"
            cf_val = f["net_cashflow"]
            cf_s = f"+${cf_val:.2f}" if cf_val >= 0 else f"-${abs(cf_val):.2f}"
            sp_s = f"${f['ad_spend']:.2f}"
            gr_s = f"${f['gross_revenue']:.2f}"
            pr_s = f"${f['proceeds']:.2f}"
            print(f"  {label:<36} {per:<23} {sp_s:>8} {f['new_trials']:>6d} {f['transactions']:>3d} "
                  f"{gr_s:>8} {pr_s:>9} {cf_s:>13} {roas_s:>9}")
        for m in data.get("combined_active_markets", []):
            label = f"[{m['country']}] COMBINED ACTIVE ADS SERIES"
            per = f"{m['start']}→{m['end']}"
            roas_s = f"{m['net_roas_pct']:.0f}%" if m["net_roas_pct"] is not None else "—"
            cf_val = m["net_cashflow"]
            cf_s = f"+${cf_val:.2f}" if cf_val >= 0 else f"-${abs(cf_val):.2f}"
            sp_s = f"${m['ad_spend']:.2f}"
            gr_s = f"${m['gross_revenue']:.2f}"
            pr_s = f"${m['proceeds']:.2f}"
            print(f"  {label:<36} {per:<23} {sp_s:>8} {m['new_trials']:>6d} {m['transactions']:>3d} "
                  f"{gr_s:>8} {pr_s:>9} {cf_s:>13} {roas_s:>9}")

    print("\n--- 4. Global Cashflow Windows (All Storefronts Combined) ---")
    print(f"  {'Window':<24} {'Period':<23} {'Ad Spend':>10} {'Gross ($)':>10} {'Net Tax ($)':>12} {'Proceeds ($)':>13} {'Net Cashflow':>13} {'Net ROAS':>9}")
    print("  " + "-" * 120)
    win_labels = [
        ("Last 14 Days (Global)", data["windows"]["last_14d_global"]),
        ("Last 28 Days (Global)", data["windows"]["last_28d_global"]),
        (f"All-Time (since {data['period']['start']})", data["windows"]["all_time_global"]),
    ]
    for wname, w in win_labels:
        per = f"{w['start']}→{w['end']}"
        roas_s = f"{w['net_roas_pct']:.0f}%" if w["net_roas_pct"] is not None else "—"
        cf_val = w["net_cashflow"]
        cf_s = f"+${cf_val:.2f}" if cf_val >= 0 else f"-${abs(cf_val):.2f}"
        sp_s = f"${w['ad_spend']:.2f}"
        gr_s = f"${w['gross_revenue']:.2f}"
        nt_s = f"${w['net_of_taxes']:.2f}"
        pr_s = f"${w['proceeds']:.2f}"
        print(f"  {wname:<24} {per:<23} {sp_s:>10} {gr_s:>10} "
              f"{nt_s:>12} {pr_s:>13} {cf_s:>13} {roas_s:>9}")

    print("\n--- 5. All-Time Country Cashflow Breakdown (RevenueCat Proceeds vs Total Apple Ads Spend) ---")
    print(f"  {'Country':<16} {'Trials':>6} {'Tx':>4} {'MRR':>8} {'Gross ($)':>10} {'Proceeds ($)':>13} {'Ad Spend ($)':>13} {'Net Cashflow':>13} {'Net ROAS':>9}")
    print("  " + "-" * 98)
    for c in data.get("country_cashflow", []):
        if c["proceeds"] == 0 and c["ad_spend"] < 0.50 and c["new_trials"] == 0:
            continue
        cname = f"{c['country']} ({c['country_name'][:10]})"
        roas_s = f"{c['net_roas_pct']:.0f}%" if c["net_roas_pct"] is not None else "organic"
        cf_val = c["net_cashflow"]
        cf_s = f"+${cf_val:.2f}" if cf_val >= 0 else f"-${abs(cf_val):.2f}"
        mrr_s = f"${c['mrr']:.2f}"
        gr_s = f"${c['gross_revenue']:.2f}"
        pr_s = f"${c['proceeds']:.2f}"
        sp_s = f"${c['ad_spend']:.2f}"
        print(f"  {cname:<16} {c['new_trials']:>6d} {c['transactions']:>4d} {mrr_s:>8} "
              f"{gr_s:>10} {pr_s:>13} {sp_s:>13} "
              f"{cf_s:>13} {roas_s:>9}")
    print("==================================================================================\n")


def export_snapshots(store: Path, data: dict, write_json=True, write_csv=True):
    metrics_dir = store / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    if write_csv:
        # the history: one row per read, and the closed weeks; appended, never rewritten
        gained = store_series(store, data)
        print("  stored: " + ", ".join(f"{name} +{count}" for name, count in gained.items()))
    if write_json:
        (metrics_dir / "revenuecat_latest.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if write_csv:
        csv_path = metrics_dir / "cashflow.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "recorded", "country", "transactions", "new_trials", "mrr_usd",
                "gross_revenue_usd", "net_of_taxes_usd", "proceeds_usd",
                "ad_spend_usd", "net_cashflow_usd", "net_roas_pct"
            ])
            rec = data["period"]["end"]
            for c in data.get("country_cashflow", []):
                writer.writerow([
                    rec, c["country"], c["transactions"], c["new_trials"], c["mrr"],
                    c["gross_revenue"], c["net_of_taxes"], c["proceeds"],
                    c["ad_spend"], c["net_cashflow"],
                    c["net_roas_pct"] if c["net_roas_pct"] is not None else ""
                ])


def main():
    parser = argparse.ArgumentParser(description="Pull RevenueCat metrics and Apple Ads Cashflow")
    parser.add_argument("--store", default=str(Path.cwd() / "marketing"), help="Path to marketing store")
    parser.add_argument("--project-id", help="Explicit RevenueCat project ID")
    parser.add_argument("--start", help="Start date YYYY-MM-DD (default: the day the app was first released)")
    parser.add_argument("--end", help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--export", action="store_true", help="Write metrics/revenuecat_latest.json and metrics/cashflow.csv")
    args = parser.parse_args()

    store = Path(args.store).resolve()
    data, err = collect_revenuecat_and_cashflow(store, project_id_override=args.project_id, start_date=args.start, end_date=args.end)
    if err or not data:
        print(f"⚠️ {err}", file=sys.stderr)
        return 2

    if args.export:
        export_snapshots(store, data)

    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    print_cashflow_report(data)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
