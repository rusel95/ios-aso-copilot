#!/usr/bin/env python3
"""Pull in-depth product telemetry and cohort analytics directly from BigQuery (Firebase / GA4 raw events).

Pillars analyzed:
1. Full Activation & Conversion Funnel (first_open -> permissions -> scan -> core actions -> paywall -> purchase)
2. Core Feature Value Engine (Compression performance by media type, GB saved, cleanup volume)
3. Retention & Cohort Dynamics (D1/D3/D7/D14/D30 retention curves, active days frequency)
4. Monetization Breakdown (Paywall entries, purchase rates, cancellation reasons)

Usage:
  python3 pull_bigquery_telemetry.py --store /path/to/marketing [--days 30] [--export-md]
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def parse_config(store_dir: Path):
    config_file = store_dir / "config.md"
    if not config_file.exists():
        raise FileNotFoundError(f"config.md not found in {store_dir}")

    config = {}
    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            match = re.match(r"\*\*([^*]+)\*\*:\s*(.*)", line.strip())
            if match:
                key, val = match.group(1).strip(), match.group(2).strip()
                config[key] = val
    return config


def run_bq_query(project_id: str, query: str):
    env = dict(os.environ)
    curr_env = env.get("CLOUDSDK_METRICS_ENVIRONMENT", "")
    env["CLOUDSDK_METRICS_ENVIRONMENT"] = f"{curr_env} datacloud.antigravity".strip()

    cmd = [
        "bq", "query",
        "--use_legacy_sql=false",
        "--format=json",
        "--label", "datacloud:antigravity",
        "--project_id", project_id,
        query
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise RuntimeError(f"BigQuery query failed (exit {res.returncode}):\n{res.stderr}\nQuery was:\n{query}")

    try:
        return json.loads(res.stdout) if res.stdout.strip() else []
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse BigQuery JSON output: {res.stdout}") from exc


def analyze_telemetry(project_id: str, dataset_id: str, days: int = 0):
    date_filter = ""
    if days > 0:
        date_filter = f'WHERE _TABLE_SUFFIX >= FORMAT_DATE("%Y%m%d", DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY))'

    # 1. Overview
    overview_sql = f"""
    SELECT
      MIN(_TABLE_SUFFIX) as min_date,
      MAX(_TABLE_SUFFIX) as max_date,
      COUNT(DISTINCT _TABLE_SUFFIX) as total_days,
      COUNT(1) as total_events,
      COUNT(DISTINCT user_pseudo_id) as total_users
    FROM `{project_id}.{dataset_id}.events_*`
    {date_filter}
    """
    overview_data = run_bq_query(project_id, overview_sql)
    overview = overview_data[0] if overview_data else {}

    # 2. Funnel Milestones
    funnel_sql = f"""
    WITH user_events AS (
      SELECT
        user_pseudo_id,
        LOGICAL_OR(event_name = "first_open") as has_first_open,
        LOGICAL_OR(event_name = "photo_access_gate_shown") as has_gate_shown,
        LOGICAL_OR(event_name = "photo_access_granted") as has_photo_granted,
        LOGICAL_OR(event_name = "photo_access_limited") as has_photo_limited,
        LOGICAL_OR(event_name = "photo_access_denied") as has_photo_denied,
        LOGICAL_OR(event_name = "cold_scan_finished") as has_cold_scan,
        LOGICAL_OR(event_name = "onboarding_completed") as has_onboarding_completed,
        LOGICAL_OR(event_name = "media_swiped") as has_media_swiped,
        LOGICAL_OR(event_name = "cleanup_completed") as has_cleanup_completed,
        LOGICAL_OR(event_name = "paywall_shown") as has_paywall_shown,
        LOGICAL_OR(event_name = "paywall_plan_selected") as has_plan_selected,
        LOGICAL_OR(event_name = "purchase_started") as has_purchase_started,
        LOGICAL_OR(event_name = "purchase_finished" AND (SELECT value.string_value FROM UNNEST(event_params) WHERE key = "result") = "purchased") as has_purchased
      FROM `{project_id}.{dataset_id}.events_*`
      {date_filter}
      GROUP BY user_pseudo_id
    )
    SELECT
      COUNT(1) as total_users,
      COUNTIF(has_first_open) as step1_first_open,
      COUNTIF(has_gate_shown) as step2_gate_shown,
      COUNTIF(has_photo_granted) as step3_photo_granted,
      COUNTIF(has_photo_limited) as step3_photo_limited,
      COUNTIF(has_photo_denied) as step3_photo_denied,
      COUNTIF(has_cold_scan) as step4_cold_scan,
      COUNTIF(has_media_swiped) as step5_media_swiped,
      COUNTIF(has_cleanup_completed) as step6_cleanup_completed,
      COUNTIF(has_paywall_shown) as step7_paywall_shown,
      COUNTIF(has_plan_selected) as step8_plan_selected,
      COUNTIF(has_purchase_started) as step9_purchase_started,
      COUNTIF(has_purchased) as step10_purchased
    FROM user_events
    """
    funnel_data = run_bq_query(project_id, funnel_sql)
    funnel = funnel_data[0] if funnel_data else {}

    # 3. Compression Core Engine
    compression_sql = f"""
    SELECT
      COALESCE((SELECT value.string_value FROM UNNEST(event_params) WHERE key = "media_type"), "unknown") as media_type,
      COUNTIF(event_name = "compression_initiated") as initiated,
      COUNTIF(event_name = "compression_completed") as completed,
      COUNTIF(event_name = "compression_failed") as failed,
      SAFE_DIVIDE(COUNTIF(event_name = "compression_completed"), COUNTIF(event_name = "compression_initiated")) * 100 as completion_rate,
      COUNT(DISTINCT IF(event_name = "compression_initiated", user_pseudo_id, NULL)) as users_initiated,
      COUNT(DISTINCT IF(event_name = "compression_completed", user_pseudo_id, NULL)) as users_completed,
      ROUND(SUM(IF(event_name = "compression_completed", (SELECT COALESCE(value.int_value, CAST(value.string_value AS INT64), CAST(value.double_value AS INT64)) FROM UNNEST(event_params) WHERE key = "bytes_saved"), 0)) / 1024 / 1024 / 1024, 2) as total_gb_saved,
      ROUND(AVG(IF(event_name = "compression_completed", (SELECT COALESCE(value.int_value, CAST(value.string_value AS INT64), CAST(value.double_value AS INT64)) FROM UNNEST(event_params) WHERE key = "bytes_saved"), NULL)) / 1024 / 1024, 2) as avg_mb_saved
    FROM `{project_id}.{dataset_id}.events_*`
    WHERE event_name IN ("compression_initiated", "compression_completed", "compression_failed")
    {("AND " + date_filter[6:]) if date_filter else ""}
    GROUP BY media_type
    ORDER BY initiated DESC
    """
    compression_data = run_bq_query(project_id, compression_sql)

    # 4. Retention & Frequency
    max_d = overview.get("max_date", "20261025")
    retention_sql = f"""
    WITH user_first_day AS (
      SELECT
        user_pseudo_id,
        MIN(PARSE_DATE("%Y%m%d", _TABLE_SUFFIX)) as first_date
      FROM `{project_id}.{dataset_id}.events_*`
      GROUP BY user_pseudo_id
    ),
    user_activity_days AS (
      SELECT DISTINCT
        user_pseudo_id,
        PARSE_DATE("%Y%m%d", _TABLE_SUFFIX) as activity_date
      FROM `{project_id}.{dataset_id}.events_*`
      WHERE event_name IN ("user_engagement", "session_start", "media_swiped", "compression_completed", "cleanup_completed")
    ),
    retention_raw AS (
      SELECT
        u.user_pseudo_id,
        u.first_date,
        DATE_DIFF(a.activity_date, u.first_date, DAY) as day_diff
      FROM user_first_day u
      JOIN user_activity_days a ON u.user_pseudo_id = a.user_pseudo_id
    )
    SELECT
      COUNT(DISTINCT user_pseudo_id) as total_users,
      COUNT(DISTINCT IF(day_diff = 0, user_pseudo_id, NULL)) as d0_users,
      COUNT(DISTINCT IF(day_diff = 1, user_pseudo_id, NULL)) as d1_users,
      ROUND(SAFE_DIVIDE(COUNT(DISTINCT IF(day_diff = 1, user_pseudo_id, NULL)), COUNT(DISTINCT IF(day_diff = 0 AND DATE_DIFF(PARSE_DATE("%Y%m%d", "{max_d}"), first_date, DAY) >= 1, user_pseudo_id, NULL))) * 100, 1) as d1_pct,
      COUNT(DISTINCT IF(day_diff = 3, user_pseudo_id, NULL)) as d3_users,
      ROUND(SAFE_DIVIDE(COUNT(DISTINCT IF(day_diff = 3, user_pseudo_id, NULL)), COUNT(DISTINCT IF(day_diff = 0 AND DATE_DIFF(PARSE_DATE("%Y%m%d", "{max_d}"), first_date, DAY) >= 3, user_pseudo_id, NULL))) * 100, 1) as d3_pct,
      COUNT(DISTINCT IF(day_diff = 7, user_pseudo_id, NULL)) as d7_users,
      ROUND(SAFE_DIVIDE(COUNT(DISTINCT IF(day_diff = 7, user_pseudo_id, NULL)), COUNT(DISTINCT IF(day_diff = 0 AND DATE_DIFF(PARSE_DATE("%Y%m%d", "{max_d}"), first_date, DAY) >= 7, user_pseudo_id, NULL))) * 100, 1) as d7_pct,
      COUNT(DISTINCT IF(day_diff = 14, user_pseudo_id, NULL)) as d14_users,
      ROUND(SAFE_DIVIDE(COUNT(DISTINCT IF(day_diff = 14, user_pseudo_id, NULL)), COUNT(DISTINCT IF(day_diff = 0 AND DATE_DIFF(PARSE_DATE("%Y%m%d", "{max_d}"), first_date, DAY) >= 14, user_pseudo_id, NULL))) * 100, 1) as d14_pct,
      COUNT(DISTINCT IF(day_diff = 30, user_pseudo_id, NULL)) as d30_users,
      ROUND(SAFE_DIVIDE(COUNT(DISTINCT IF(day_diff = 30, user_pseudo_id, NULL)), COUNT(DISTINCT IF(day_diff = 0 AND DATE_DIFF(PARSE_DATE("%Y%m%d", "{max_d}"), first_date, DAY) >= 30, user_pseudo_id, NULL))) * 100, 1) as d30_pct
    FROM retention_raw
    """
    retention_data = run_bq_query(project_id, retention_sql)
    retention = retention_data[0] if retention_data else {}

    # Active days distribution
    activity_sql = f"""
    WITH active_days AS (
      SELECT
        user_pseudo_id,
        COUNT(DISTINCT _TABLE_SUFFIX) as days_active
      FROM `{project_id}.{dataset_id}.events_*`
      GROUP BY user_pseudo_id
    )
    SELECT
      CASE
        WHEN days_active = 1 THEN "1 day only"
        WHEN days_active = 2 THEN "2 days"
        WHEN days_active BETWEEN 3 AND 5 THEN "3-5 days"
        WHEN days_active BETWEEN 6 AND 10 THEN "6-10 days"
        ELSE "11+ days"
      END as activity_bucket,
      COUNT(1) as users,
      ROUND(COUNT(1) * 100.0 / SUM(COUNT(1)) OVER(), 1) as pct
    FROM active_days
    GROUP BY activity_bucket, CASE
        WHEN days_active = 1 THEN 1
        WHEN days_active = 2 THEN 2
        WHEN days_active BETWEEN 3 AND 5 THEN 3
        WHEN days_active BETWEEN 6 AND 10 THEN 4
        ELSE 5
      END
    ORDER BY 1
    """
    activity_data = run_bq_query(project_id, activity_sql)

    # 5. Monetization by Entry Point
    monetization_sql = f"""
    SELECT
      COALESCE((SELECT value.string_value FROM UNNEST(event_params) WHERE key = "entry"), "unspecified") as entry_point,
      COUNTIF(event_name = "paywall_shown") as paywall_views,
      COUNT(DISTINCT IF(event_name = "paywall_shown", user_pseudo_id, NULL)) as paywall_users,
      COUNTIF(event_name = "purchase_started") as purchase_attempts,
      COUNTIF(event_name = "purchase_finished" AND (SELECT value.string_value FROM UNNEST(event_params) WHERE key = "result") = "purchased") as purchases_completed,
      COUNT(DISTINCT IF(event_name = "purchase_finished" AND (SELECT value.string_value FROM UNNEST(event_params) WHERE key = "result") = "purchased", user_pseudo_id, NULL)) as buyers,
      ROUND(SAFE_DIVIDE(COUNT(DISTINCT IF(event_name = "purchase_finished" AND (SELECT value.string_value FROM UNNEST(event_params) WHERE key = "result") = "purchased", user_pseudo_id, NULL)), COUNT(DISTINCT IF(event_name = "paywall_shown", user_pseudo_id, NULL))) * 100, 1) as cvr_pct
    FROM `{project_id}.{dataset_id}.events_*`
    WHERE event_name IN ("paywall_shown", "purchase_started", "purchase_finished")
    {("AND " + date_filter[6:]) if date_filter else ""}
    GROUP BY entry_point
    ORDER BY paywall_views DESC
    """
    monetization_data = run_bq_query(project_id, monetization_sql)

    return {
        "overview": overview,
        "funnel": funnel,
        "compression": compression_data,
        "retention": retention,
        "activity": activity_data,
        "monetization": monetization_data
    }


def format_markdown_report(data: dict) -> str:
    ov = data["overview"]
    fn = data["funnel"]
    rt = data["retention"]
    
    total_u = int(fn.get("total_users", 0) or 1)
    first_open = int(fn.get("step1_first_open", 0) or 1)
    
    lines = [
        "# BigQuery Product Telemetry & In-App Analytics Report",
        "",
        f"**Date Range**: {ov.get('min_date', '-')} to {ov.get('max_date', '-')} ({ov.get('total_days', 0)} recorded days)",
        f"**Total Events**: {int(ov.get('total_events', 0) or 0):,} | **Total Unique Users**: {int(ov.get('total_users', 0) or 0):,}",
        "",
        "## 1. Activation & Conversion Funnel",
        "",
        "| Step | Event / Milestone | Users | % of First Open | Step Conversion |",
        "| :---: | :--- | :---: | :---: | :---: |",
        f"| 1 | `first_open` | {fn.get('step1_first_open', 0)} | 100.0% | — |",
        f"| 2 | Photo Permission Gate Shown | {fn.get('step2_gate_shown', 0)} | {int(fn.get('step2_gate_shown',0))*100/first_open:.1f}% | {int(fn.get('step2_gate_shown',0))*100/first_open:.1f}% |",
        f"| 3 | Full Photo Access Granted | {fn.get('step3_photo_granted', 0)} | {int(fn.get('step3_photo_granted',0))*100/first_open:.1f}% | {int(fn.get('step3_photo_granted',0))*100/max(1, int(fn.get('step2_gate_shown',0))):.1f}% |",
        f"| 4 | Cold Scan Finished | {fn.get('step4_cold_scan', 0)} | {int(fn.get('step4_cold_scan',0))*100/first_open:.1f}% | {int(fn.get('step4_cold_scan',0))*100/max(1, int(fn.get('step3_photo_granted',0))):.1f}% |",
        f"| 5 | Media Swiped (Core Action) | {fn.get('step5_media_swiped', 0)} | {int(fn.get('step5_media_swiped',0))*100/first_open:.1f}% | {int(fn.get('step5_media_swiped',0))*100/max(1, int(fn.get('step4_cold_scan',0))):.1f}% |",
        f"| 6 | Cleanup Completed | {fn.get('step6_cleanup_completed', 0)} | {int(fn.get('step6_cleanup_completed',0))*100/first_open:.1f}% | {int(fn.get('step6_cleanup_completed',0))*100/max(1, int(fn.get('step5_media_swiped',0))):.1f}% |",
        f"| 7 | Paywall Shown | {fn.get('step7_paywall_shown', 0)} | {int(fn.get('step7_paywall_shown',0))*100/first_open:.1f}% | — |",
        f"| 8 | Purchase Started | {fn.get('step9_purchase_started', 0)} | {int(fn.get('step9_purchase_started',0))*100/first_open:.1f}% | {int(fn.get('step9_purchase_started',0))*100/max(1, int(fn.get('step7_paywall_shown',0))):.1f}% |",
        f"| 9 | Pro Purchase Completed | {fn.get('step10_purchased', 0)} | {int(fn.get('step10_purchased',0))*100/first_open:.1f}% | {int(fn.get('step10_purchased',0))*100/max(1, int(fn.get('step7_paywall_shown',0))):.1f}% |",
        "",
        "## 2. Core Value Engine (Media Compression)",
        "",
        "| Media Type | Initiated | Completed | Failed | Success Rate | Saved (GB) | Avg Saved/Item | Users |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]
    
    total_gb = 0.0
    for row in data["compression"]:
        gb = float(row.get("total_gb_saved", 0) or 0)
        total_gb += gb
        rate = float(row.get("completion_rate", 0) or 0)
        lines.append(
            f"| **{row.get('media_type')}** | {row.get('initiated')} | {row.get('completed')} | {row.get('failed')} | {rate:.1f}% | {gb:.2f} GB | {row.get('avg_mb_saved')} MB | {row.get('users_completed')} |"
        )
    lines.append(f"**Total Volume Saved Across All Types**: **{total_gb:.2f} GB**")
    lines.append("")
    
    lines.extend([
        "## 3. Retention & User Churn Curve",
        "",
        "| Cohort Metric | D1 Retention | D3 Retention | D7 Retention | D14 Retention | D30 Retention |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
        f"| **Return Rate** | **{rt.get('d1_pct')}%** ({rt.get('d1_users')} users) | **{rt.get('d3_pct')}%** ({rt.get('d3_users')} users) | **{rt.get('d7_pct')}%** ({rt.get('d7_users')} users) | **{rt.get('d14_pct')}%** ({rt.get('d14_users')} users) | **{rt.get('d30_pct')}%** ({rt.get('d30_users')} users) |",
        "",
        "### User Lifetime Activity Days Distribution:",
        "| Activity Depth | Users | Percentage |",
        "| :--- | :---: | :---: |"
    ])
    for act in data["activity"]:
        lines.append(f"| {act.get('activity_bucket')} | {act.get('users')} | {act.get('pct')}% |")
        
    lines.extend([
        "",
        "## 4. Paywall & Monetization Entry Points",
        "",
        "| Entry Trigger | Paywall Views | Paywall Users | Purchase Attempts | Completed Buyers | Paywall CVR |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |"
    ])
    for mon in data["monetization"]:
        lines.append(
            f"| **{mon.get('entry_point')}** | {mon.get('paywall_views')} | {mon.get('paywall_users')} | {mon.get('purchase_attempts')} | {mon.get('buyers')} | **{mon.get('cvr_pct')}%** |"
        )
        
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Pull BigQuery in-app telemetry.")
    parser.add_argument("--store", default="marketing", help="Path to marketing store folder")
    parser.add_argument("--days", type=int, default=0, help="Days to look back (0 for all-time)")
    parser.add_argument("--export-md", action="store_true", help="Save markdown report to metrics/telemetry_latest.md")
    parser.add_argument("--export-json", action="store_true", help="Save raw JSON to metrics/telemetry_latest.json")
    args = parser.parse_args()

    store_path = Path(args.store).resolve()
    config = parse_config(store_path)

    project_id = config.get("Firebase Project ID") or config.get("BigQuery Project ID")
    ga_prop = config.get("GA4 Property ID")
    dataset_id = config.get("BigQuery Dataset") or (f"analytics_{ga_prop}" if ga_prop else None)

    if not project_id:
        print("Error: 'Firebase Project ID' or 'BigQuery Project ID' must be set in config.md", file=sys.stderr)
        return 1
    if not dataset_id:
        print("Error: 'BigQuery Dataset' or 'GA4 Property ID' must be set in config.md", file=sys.stderr)
        return 1

    print(f"Executing BigQuery telemetry analysis for {project_id}:{dataset_id}...")
    data = analyze_telemetry(project_id, dataset_id, args.days)

    report_md = format_markdown_report(data)
    print("\n" + report_md + "\n")

    metrics_dir = store_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    if args.export_md:
        md_file = metrics_dir / "telemetry_latest.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(report_md)
        print(f"Report exported to {md_file}")

    if args.export_json:
        json_file = metrics_dir / "telemetry_latest.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Raw data exported to {json_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
