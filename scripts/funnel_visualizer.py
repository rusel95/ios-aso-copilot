#!/usr/bin/env python3
"""
funnel_visualizer.py — Storefront Conversion Funnel Analyzer & Visualizer
Part of ios-marketing-ops.

Visualizes App Store conversion funnels (Impressions -> Page Views -> Downloads -> Trials),
compares against industry peer benchmarks, and automatically diagnoses the primary bottleneck.
"""

import argparse
import csv
import json
import os
import sys

# Category Benchmarks (Health & Fitness / Utilities / Audio)
BENCHMARKS = {
    "ttr": {"leak": 1.8, "good": 4.2, "label": "1.8 – 4.2%", "name": "Tap-Through Rate (TTR)"},
    "page_cvr": {"leak": 18.0, "good": 32.0, "label": "18.0 – 32.0%", "name": "Page CVR"},
    "overall_cvr": {"leak": 1.2, "good": 3.0, "label": "1.2 – 3.0%", "name": "Overall ASO CVR"},
    "paywall_cvr": {"leak": 4.0, "good": 9.0, "label": "4.0 – 9.0%", "name": "Paywall CVR"}
}

def render_bar(pct, width=20):
    if pct <= 0:
        return "░" * width
    clamped = min(max(pct, 0.0), 100.0)
    filled = int(round((clamped / 100.0) * width))
    empty = width - filled
    return "█" * filled + "░" * empty

def get_health(metric_key, val_pct):
    if val_pct is None:
        return "—", "⚪ UNKNOWN"
    bm = BENCHMARKS[metric_key]
    if val_pct < bm["leak"]:
        return bm["label"], "🔴 CRITICAL LEAK"
    elif val_pct < bm["good"]:
        return bm["label"], "🟡 FAIR (Baseline)"
    else:
        return bm["label"], "🟢 HEALTHY (Strong)"

def diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr):
    diagnoses = []
    
    # 1. Top-of-funnel search card check
    if ttr is not None and ttr < BENCHMARKS["ttr"]["leak"]:
        diagnoses.append({
            "severity": "HIGH",
            "bottleneck": "Top-of-Funnel Search Card Leak (Low TTR)",
            "cause": f"Only {ttr:.1f}% of users tap after seeing the search card (benchmark: >1.8%).",
            "lever": "Run Product Page Optimization (PPO) test on App Icon; redesign Screenshot #1 with punchy 3-word hook; align subtitle with user search intent."
        })
    elif overall_cvr is not None and overall_cvr < BENCHMARKS["overall_cvr"]["leak"]:
        diagnoses.append({
            "severity": "HIGH",
            "bottleneck": "Overall Storefront Conversion Leak",
            "cause": f"Total impressions-to-download CVR is {overall_cvr:.2f}% (benchmark: >1.2%).",
            "lever": "Audit search impression quality: users see the app for high-volume keywords that don't match their exact intent."
        })

    # 2. Product Page View drop-off check
    if page_cvr is not None and page_cvr < BENCHMARKS["page_cvr"]["leak"]:
        diagnoses.append({
            "severity": "HIGH",
            "bottleneck": "Product Page View Drop-off (Low Page CVR)",
            "cause": f"Only {page_cvr:.1f}% download after opening the full page (benchmark: >18.0%).",
            "lever": "Localize screenshots for this storefront; triage negative reviews; highlight free trial in first 3 lines of description."
        })

    # 3. Paywall monetization check
    if paywall_cvr is not None and paywall_cvr < BENCHMARKS["paywall_cvr"]["leak"]:
        diagnoses.append({
            "severity": "MEDIUM",
            "bottleneck": "In-App Paywall Monetization Leak",
            "cause": f"Only {paywall_cvr:.1f}% of new downloads start a trial (benchmark: >4.0%).",
            "lever": "Audit Localizable.xcstrings for missing paywall keys; add monthly equivalent pricing anchor; emphasize 7-day free trial."
        })

    if not diagnoses:
        diagnoses.append({
            "severity": "LOW",
            "bottleneck": "No Critical Leaks Detected",
            "cause": "All conversion stages perform within or above baseline industry benchmarks.",
            "lever": "Focus on expanding top-of-funnel keyword reach (RespectASO autocomplete mining) and international storefront localization."
        })

    return diagnoses

def parse_weekly_csv(csv_path):
    if not os.path.exists(csv_path):
        return None
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        return None
    return sorted(rows, key=lambda x: x.get('week_start', ''))

def format_text_table(period_name, imp, views, downloads, trials):
    ttr = (views / imp * 100.0) if imp and views is not None else None
    page_cvr = (downloads / views * 100.0) if views and downloads is not None else None
    overall_cvr = (downloads / imp * 100.0) if imp and downloads is not None else None
    paywall_cvr = (trials / downloads * 100.0) if downloads and trials is not None else None

    ttr_label, ttr_health = get_health("ttr", ttr)
    page_label, page_health = get_health("page_cvr", page_cvr)
    overall_label, overall_health = get_health("overall_cvr", overall_cvr)
    paywall_label, paywall_health = get_health("paywall_cvr", paywall_cvr)

    diagnoses = diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr)

    lines = []
    lines.append("┌────────────────────────────────────────────────────────────────────────────────────────┐")
    lines.append(f"│ 🎯 STOREFRONT CONVERSION FUNNEL ({period_name:<53}) │")
    lines.append("├──────────────────────────────┬──────────┬──────────┬─────────────┬─────────────────────┤")
    lines.append("│ Funnel Stage                 │   Volume │ Conv Rate│  Benchmark  │ Health Status       │")
    lines.append("├──────────────────────────────┼──────────┼──────────┼─────────────┼─────────────────────┤")
    
    # Stage 1: Impressions
    lines.append(f"│ 1. Search Impressions        │ {imp:>8,d} │   100.0% │      —      │                     │")
    lines.append(f"│    │ [{render_bar(100.0)}]  │          │          │             │                     │")
    ttr_str = f"{ttr:.1f}%" if ttr is not None else "N/A"
    lines.append(f"│    ▼ Tap-Through Rate (TTR)  │          │ {ttr_str:>8} │ {ttr_label:<11} │ {ttr_health:<19} │")
    
    # Stage 2: Page Views
    views_str = f"{views:,d}" if views is not None else "N/A"
    lines.append(f"│ 2. Product Page Views        │ {views_str:>8} │ {ttr_str:>8} │      —      │                     │")
    views_bar = render_bar(ttr if ttr else 0.0)
    lines.append(f"│    │ [{views_bar}]  │          │          │             │                     │")
    page_str = f"{page_cvr:.1f}%" if page_cvr is not None else "N/A"
    lines.append(f"│    ▼ Page Conversion (CVR)   │          │ {page_str:>8} │ {page_label:<11} │ {page_health:<19} │")
    
    # Stage 3: Downloads
    dl_str = f"{downloads:,d}" if downloads is not None else "N/A"
    lines.append(f"│ 3. First-Time Downloads      │ {dl_str:>8} │ {page_str:>8} │      —      │                     │")
    dl_bar = render_bar(overall_cvr if overall_cvr else 0.0)
    lines.append(f"│    │ [{dl_bar}]  │          │          │             │                     │")
    ovr_str = f"{overall_cvr:.2f}%" if overall_cvr is not None else "N/A"
    lines.append(f"│    │ (Overall ASO CVR)       │          │ {ovr_str:>8} │ {overall_label:<11} │ {overall_health:<19} │")
    
    # Stage 4: Paywall
    if trials is not None:
        paywall_str = f"{paywall_cvr:.1f}%" if paywall_cvr is not None else "N/A"
        lines.append(f"│    ▼ Paywall Conversion      │          │ {paywall_str:>8} │ {paywall_label:<11} │ {paywall_health:<19} │")
        lines.append(f"│ 4. Trial Starts & Subs       │ {trials:>8,d} │ {paywall_str:>8} │      —      │                     │")
    
    lines.append("└──────────────────────────────┴──────────┴──────────┴─────────────┴─────────────────────┘")
    lines.append("")
    lines.append("🔍 FUNNEL BOTTLENECK DIAGNOSIS:")
    for d in diagnoses:
        lines.append(f"  • [{d['severity']}] {d['bottleneck']}")
        lines.append(f"    Cause: {d['cause']}")
        lines.append(f"    Actionable Lever: {d['lever']}")
    
    return "\n".join(lines)

def format_markdown_table(period_name, imp, views, downloads, trials):
    ttr = (views / imp * 100.0) if imp and views is not None else None
    page_cvr = (downloads / views * 100.0) if views and downloads is not None else None
    overall_cvr = (downloads / imp * 100.0) if imp and downloads is not None else None
    paywall_cvr = (trials / downloads * 100.0) if downloads and trials is not None else None

    ttr_label, ttr_health = get_health("ttr", ttr)
    page_label, page_health = get_health("page_cvr", page_cvr)
    overall_label, overall_health = get_health("overall_cvr", overall_cvr)
    paywall_label, paywall_health = get_health("paywall_cvr", paywall_cvr)

    diagnoses = diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr)

    md = []
    md.append(f"### 🎯 Storefront Conversion Funnel ({period_name})")
    md.append("")
    md.append("| Funnel Stage | Volume | Conversion Rate | Benchmark | Health Status |")
    md.append("|---|---|---|---|---|")
    md.append(f"| **1. Search Impressions** | `{imp:,d}` | `100.0%` | — | — |")
    ttr_str = f"{ttr:.1f}%" if ttr is not None else "N/A"
    md.append(f"| ↳ *Tap-Through Rate (TTR)* | — | **{ttr_str}** | {ttr_label} | {ttr_health} |")
    views_str = f"{views:,d}" if views is not None else "N/A"
    md.append(f"| **2. Product Page Views** | `{views_str}` | `{ttr_str}` | — | — |")
    page_str = f"{page_cvr:.1f}%" if page_cvr is not None else "N/A"
    md.append(f"| ↳ *Page Conversion (Page CVR)* | — | **{page_str}** | {page_label} | {page_health} |")
    dl_str = f"{downloads:,d}" if downloads is not None else "N/A"
    md.append(f"| **3. First-Time Downloads** | `{dl_str}` | `{page_str}` | — | — |")
    ovr_str = f"{overall_cvr:.2f}%" if overall_cvr is not None else "N/A"
    md.append(f"| ↳ *Overall ASO CVR (Imp → DL)* | — | **{ovr_str}** | {overall_label} | {overall_health} |")
    if trials is not None:
        paywall_str = f"{paywall_cvr:.1f}%" if paywall_cvr is not None else "N/A"
        md.append(f"| ↳ *Paywall CVR (DL → Trial)* | — | **{paywall_str}** | {paywall_label} | {paywall_health} |")
        md.append(f"| **4. Subscriptions & Trials** | `{trials:,d}` | `{paywall_str}` | — | — |")
    
    md.append("")
    md.append("#### 🔍 Bottleneck Diagnosis & Actionable Levers")
    for d in diagnoses:
        md.append(f"- **{d['bottleneck']}** ({d['severity']} Priority)")
        md.append(f"  - *Root Cause:* {d['cause']}")
        md.append(f"  - *Prescribed Action:* {d['lever']}")
    
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(description="Storefront Conversion Funnel Analyzer & Visualizer")
    parser.add_argument("--store", default="marketing", help="Path to marketing/ directory containing metrics/weekly.csv")
    parser.add_argument("--impressions", type=int, help="Direct impressions count")
    parser.add_argument("--views", type=int, help="Direct product page views count")
    parser.add_argument("--downloads", type=int, help="Direct downloads count")
    parser.add_argument("--trials", type=int, help="Direct trial starts count")
    parser.add_argument("--period", default="Latest Available Window", help="Period label")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="Output format")
    parser.add_argument("--output", help="File path to save output")
    parser.add_argument("--self-check", action="store_true", help="Run unit self check")

    args = parser.parse_args()

    if args.self_check:
        print("Running funnel_visualizer self-check...")
        t = format_text_table("Self Check", 10000, 350, 90, 8)
        assert "STOREFRONT CONVERSION FUNNEL" in t
        m = format_markdown_table("Self Check", 10000, 350, 90, 8)
        assert "Storefront Conversion Funnel" in m
        print("Self-check passed successfully.")
        return

    # Check if direct values provided
    if args.impressions is not None:
        imp = args.impressions
        views = args.views
        downloads = args.downloads
        trials = args.trials
        period = args.period
    else:
        # Load from marketing/metrics/weekly.csv
        csv_path = os.path.join(args.store, "metrics", "weekly.csv")
        rows = parse_weekly_csv(csv_path)
        if not rows:
            print(f"Error: No weekly records found in {csv_path}. Specify direct values via --impressions.", file=sys.stderr)
            sys.exit(1)
        
        valid_rows = [r for r in rows if r.get('impressions') and r.get('impressions').isdigit()]
        if not valid_rows:
            print(f"Warning: All records in {csv_path} are pending or absent figures. Using sample baseline.", file=sys.stderr)
            imp, views, downloads, trials = 857, 46, 12, 1
            period = "Recent Sample Period"
        else:
            latest = valid_rows[-1]
            imp = int(latest.get('impressions', 0))
            views = int(latest.get('product_page_views', 0)) if latest.get('product_page_views', '').isdigit() else None
            downloads = int(latest.get('downloads', 0)) if latest.get('downloads', '').isdigit() else None
            trials = int(latest.get('trial_starts', 0)) if latest.get('trial_starts', '').isdigit() else None
            period = f"Week of {latest.get('week_start', 'Recent')}"

    if args.format == "text":
        result = format_text_table(period, imp, views, downloads, trials)
    elif args.format == "markdown":
        result = format_markdown_table(period, imp, views, downloads, trials)
    elif args.format == "json":
        ttr = (views / imp * 100.0) if imp and views is not None else None
        page_cvr = (downloads / views * 100.0) if views and downloads is not None else None
        overall_cvr = (downloads / imp * 100.0) if imp and downloads is not None else None
        paywall_cvr = (trials / downloads * 100.0) if downloads and trials is not None else None
        data = {
            "period": period,
            "impressions": imp,
            "product_page_views": views,
            "downloads": downloads,
            "trial_starts": trials,
            "metrics": {
                "ttr_pct": round(ttr, 2) if ttr else None,
                "page_cvr_pct": round(page_cvr, 2) if page_cvr else None,
                "overall_cvr_pct": round(overall_cvr, 2) if overall_cvr else None,
                "paywall_cvr_pct": round(paywall_cvr, 2) if paywall_cvr else None
            },
            "diagnoses": diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr)
        }
        result = json.dumps(data, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result + "\n")
        print(f"Saved funnel report to {args.output}")
    else:
        print(result)

if __name__ == "__main__":
    main()
