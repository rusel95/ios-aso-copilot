#!/usr/bin/env python3
"""
funnel_visualizer.py — Storefront Conversion Pyramid & Funnel Analyzer
Part of ios-marketing-ops.

Visualizes App Store conversion funnels as an inverted pyramid,
cleanly distinguishing between:
  1. Step Conversion (TTR %, Page CVR %, Paywall CVR %) on transition arrows
  2. Total Funnel Retention (% of initial impressions reaching each stage) on tier labels
Compares against Apple category benchmarks and diagnoses conversion bottlenecks.
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

def get_badge(metric_key, val_pct):
    if val_pct is None:
        return "—", "⚪ N/A"
    bm = BENCHMARKS[metric_key]
    if val_pct < bm["leak"]:
        return bm["label"], "🔴 LEAK (Below baseline)"
    elif val_pct < bm["good"]:
        return bm["label"], "🟡 FAIR (Baseline)"
    else:
        return bm["label"], "🟢 STRONG (Above avg)"

def diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr):
    diagnoses = []
    
    if ttr is not None and ttr < BENCHMARKS["ttr"]["leak"]:
        diagnoses.append({
            "severity": "HIGH",
            "bottleneck": "Top-of-Funnel Search Card Leak (Low TTR)",
            "cause": f"Only {ttr:.1f}% of users tap the search card (benchmark: >1.8%).",
            "lever": "Run Product Page Optimization (PPO) test on App Icon; redesign Screenshot #1 with punchy 3-word hook; align subtitle with user search intent."
        })
    elif overall_cvr is not None and overall_cvr < BENCHMARKS["overall_cvr"]["leak"]:
        diagnoses.append({
            "severity": "HIGH",
            "bottleneck": "Overall Storefront Conversion Leak",
            "cause": f"Total impressions-to-download CVR is {overall_cvr:.2f}% (benchmark: >1.2%).",
            "lever": "Audit search impression quality: users see the app for high-volume keywords that don't match their exact intent."
        })

    if page_cvr is not None and page_cvr < BENCHMARKS["page_cvr"]["leak"]:
        diagnoses.append({
            "severity": "HIGH",
            "bottleneck": "Product Page View Drop-off (Low Page CVR)",
            "cause": f"Only {page_cvr:.1f}% download after opening the full page (benchmark: >18.0%).",
            "lever": "Localize screenshots for this storefront; triage negative reviews; highlight free trial in first 3 lines of description."
        })

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

def render_pyramid(title, imp, views, downloads, trials):
    ttr = (views / imp * 100.0) if imp and views is not None else None
    page_cvr = (downloads / views * 100.0) if views and downloads is not None else None
    overall_cvr = (downloads / imp * 100.0) if imp and downloads is not None else None
    paywall_cvr = (trials / downloads * 100.0) if downloads and trials is not None else None
    overall_sub_cvr = (trials / imp * 100.0) if imp and trials is not None else None

    _, ttr_b = get_badge("ttr", ttr)
    _, page_b = get_badge("page_cvr", page_cvr)
    _, paywall_b = get_badge("paywall_cvr", paywall_cvr)

    lines = []
    lines.append("╔══════════════════════════════════════════════════════════════════════════════════════════╗")
    lines.append(f"║ 🎯 STOREFRONT CONVERSION PYRAMID: {title:<53} ║")
    lines.append("╠══════════════════════════════════════════════════════════════════════════════════════════╣")
    lines.append("║                                                                                          ║")
    lines.append("║  ▼════════════════════════════════════════════════════════════════════════════════════▼  ║")
    lines.append(f"║  █ 1. SEARCH IMPRESSIONS: {imp:<10,d}                                          100.0% █  ║")
    lines.append("║  █ ██████████████████████████████████████████████████████████████████████████████████ █  ║")
    lines.append("║  ╰──────────────────────────────────────────┬─────────────────────────────────────────╯  ║")
    
    ttr_str = f"{ttr:.1f}%" if ttr is not None else "N/A"
    views_val = f"{views:,d}" if views is not None else "N/A"
    lines.append(f"║                      TTR (Tap-Through Rate):│ {ttr_str:>5} ({views_val} page views / {imp:,d} imp)        ║")
    lines.append(f"║                                  Benchmark: │ {ttr_b:<46} ║")
    lines.append("║                                             ▼                                            ║")
    lines.append("║       ▼════════════════════════════════════════════════════════════════════════▼         ║")
    lines.append(f"║       █ 2. PRODUCT PAGE VIEWS: {views_val:<8}                             {ttr_str:>5} of top █         ║")
    lines.append("║       █ ██████████████████████████████████████████████████████████████████████ █         ║")
    lines.append("║       ╰─────────────────────────────────────┬──────────────────────────────────╯         ║")
    
    page_str = f"{page_cvr:.1f}%" if page_cvr is not None else "N/A"
    dl_val = f"{downloads:,d}" if downloads is not None else "N/A"
    lines.append(f"║                      Page CVR (Storefront): │ {page_str:>5} ({dl_val} downloads / {views_val} views)       ║")
    lines.append(f"║                                  Benchmark: │ {page_b:<46} ║")
    lines.append("║                                             ▼                                            ║")
    lines.append("║             ▼════════════════════════════════════════════════════════════▼               ║")
    ovr_str = f"{overall_cvr:.2f}%" if overall_cvr is not None else "N/A"
    lines.append(f"║             █ 3. FIRST-TIME DOWNLOADS: {dl_val:<6}                  {ovr_str:>6} Overall CVR █               ║")
    lines.append("║             █ ██████████████████████████████████████████████████████████ █               ║")
    lines.append("║             ╰───────────────────────────────┬────────────────────────────╯               ║")
    
    if trials is not None:
        paywall_str = f"{paywall_cvr:.1f}%" if paywall_cvr is not None else "N/A"
        sub_str = f"{overall_sub_cvr:.2f}%" if overall_sub_cvr is not None else "N/A"
        lines.append(f"║                                Paywall CVR: │ {paywall_str:>5} ({trials:,d} trials / {dl_val} dl)             ║")
        lines.append(f"║                                  Benchmark: │ {paywall_b:<46} ║")
        lines.append("║                                             ▼                                            ║")
        lines.append("║                   ▼════════════════════════════════════════════════▼                     ║")
        lines.append(f"║                   █ 4. PAID SUBS & TRIALS: {trials:<4,d}           {sub_str:>6} of top █                     ║")
        lines.append("║                   █ ██████████████████████████████████████████████ █                     ║")
        lines.append("║                   ╰────────────────────────────────────────────────╯                     ║")
    
    lines.append("║                                                                                          ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════════════════════════╝")
    lines.append("")
    lines.append("🔍 FUNNEL BOTTLENECK DIAGNOSIS:")
    diagnoses = diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr)
    for d in diagnoses:
        lines.append(f"  • [{d['severity']}] {d['bottleneck']}")
        lines.append(f"    Cause: {d['cause']}")
        lines.append(f"    Actionable Lever: {d['lever']}")
    
    return "\n".join(lines)

def render_markdown(title, imp, views, downloads, trials):
    ttr = (views / imp * 100.0) if imp and views is not None else None
    page_cvr = (downloads / views * 100.0) if views and downloads is not None else None
    overall_cvr = (downloads / imp * 100.0) if imp and downloads is not None else None
    paywall_cvr = (trials / downloads * 100.0) if downloads and trials is not None else None
    overall_sub_cvr = (trials / imp * 100.0) if imp and trials is not None else None

    ttr_l, ttr_b = get_badge("ttr", ttr)
    page_l, page_b = get_badge("page_cvr", page_cvr)
    paywall_l, paywall_b = get_badge("paywall_cvr", paywall_cvr)

    md = []
    md.append(f"### 🎯 Storefront Conversion Pyramid ({title})")
    md.append("")
    md.append("| Funnel Stage | Volume | Step Conversion (Arrow) | Funnel Reach (% of Top) | Benchmark | Status |")
    md.append("|---|---|---|---|---|---|")
    md.append(f"| **1. Search Impressions** | `{imp:,d}` | — | **100.0%** (Top) | — | — |")
    
    ttr_str = f"{ttr:.1f}%" if ttr is not None else "N/A"
    md.append(f"| **2. Product Page Views** | `{views:,d}` | **{ttr_str} TTR** (views ÷ imp) | **{ttr_str}** | {ttr_l} | {ttr_b} |")
    
    page_str = f"{page_cvr:.1f}%" if page_cvr is not None else "N/A"
    ovr_str = f"{overall_cvr:.2f}%" if overall_cvr is not None else "N/A"
    md.append(f"| **3. First-Time Downloads** | `{downloads:,d}` | **{page_str} Page CVR** (dl ÷ views) | **{ovr_str} Overall CVR** | {page_l} | {page_b} |")
    
    if trials is not None:
        paywall_str = f"{paywall_cvr:.1f}%" if paywall_cvr is not None else "N/A"
        sub_str = f"{overall_sub_cvr:.2f}%" if overall_sub_cvr is not None else "N/A"
        md.append(f"| **4. Paid Subs & Trials** | `{trials:,d}` | **{paywall_str} Paywall CVR** (trials ÷ dl) | **{sub_str} Revenue CVR** | {paywall_l} | {paywall_b} |")
    
    md.append("")
    md.append("#### 🔍 Bottleneck Diagnosis & Actionable Levers")
    diagnoses = diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr)
    for d in diagnoses:
        md.append(f"- **{d['bottleneck']}** ({d['severity']} Priority)")
        md.append(f"  - *Root Cause:* {d['cause']}")
        md.append(f"  - *Actionable Lever:* {d['lever']}")
    
    return "\n".join(md)

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

def main():
    parser = argparse.ArgumentParser(description="Storefront Conversion Pyramid Analyzer")
    parser.add_argument("--store", default="marketing", help="Path to marketing directory")
    parser.add_argument("--impressions", type=int, help="Search impressions count")
    parser.add_argument("--views", type=int, help="Product page views count")
    parser.add_argument("--downloads", type=int, help="Downloads count")
    parser.add_argument("--trials", type=int, help="Trial starts / subs count")
    parser.add_argument("--period", default="Latest Available Window", help="Period title")
    parser.add_argument("--format", choices=["pyramid", "markdown", "json"], default="pyramid", help="Output format")
    parser.add_argument("--output", help="File to write output")
    parser.add_argument("--self-check", action="store_true", help="Self check")

    args = parser.parse_args()

    if args.self_check:
        p = render_pyramid("Self Check", 10000, 420, 110, 12)
        assert "STOREFRONT CONVERSION PYRAMID" in p
        m = render_markdown("Self Check", 10000, 420, 110, 12)
        assert "Storefront Conversion Pyramid" in m
        print("Self-check passed successfully.")
        return

    if args.impressions is not None:
        imp = args.impressions
        views = args.views
        downloads = args.downloads
        trials = args.trials
        period = args.period
    else:
        csv_path = os.path.join(args.store, "metrics", "weekly.csv")
        rows = parse_weekly_csv(csv_path)
        valid_rows = [r for r in rows if r.get('impressions') and r.get('impressions').isdigit()] if rows else []
        if not valid_rows:
            imp, views, downloads, trials = 546, 39, 9, 1
            period = "Baseline Estimate (No complete weekly rows)"
        else:
            latest = valid_rows[-1]
            imp = int(latest.get('impressions', 0))
            views = int(latest.get('product_page_views', 0)) if latest.get('product_page_views', '').isdigit() else None
            downloads = int(latest.get('downloads', 0)) if latest.get('downloads', '').isdigit() else None
            trials = int(latest.get('trial_starts', 0)) if latest.get('trial_starts', '').isdigit() else None
            period = f"Week of {latest.get('week_start', 'Recent')}"

    if args.format == "pyramid":
        result = render_pyramid(period, imp, views, downloads, trials)
    elif args.format == "markdown":
        result = render_markdown(period, imp, views, downloads, trials)
    elif args.format == "json":
        ttr = (views / imp * 100.0) if imp and views is not None else None
        page_cvr = (downloads / views * 100.0) if views and downloads is not None else None
        overall_cvr = (downloads / imp * 100.0) if imp and downloads is not None else None
        paywall_cvr = (trials / downloads * 100.0) if downloads and trials is not None else None
        result = json.dumps({
            "period": period,
            "impressions": imp,
            "product_page_views": views,
            "downloads": downloads,
            "trial_starts": trials,
            "ttr_pct": round(ttr, 2) if ttr else None,
            "page_cvr_pct": round(page_cvr, 2) if page_cvr else None,
            "overall_cvr_pct": round(overall_cvr, 2) if overall_cvr else None,
            "paywall_cvr_pct": round(paywall_cvr, 2) if paywall_cvr else None,
            "diagnoses": diagnose_funnel(ttr, page_cvr, overall_cvr, paywall_cvr)
        }, indent=2)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result + "\n")
        print(f"Saved to {args.output}")
    else:
        print(result)

if __name__ == "__main__":
    main()
