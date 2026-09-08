#!/usr/bin/env python3
"""
measure_velocity.py — Audit competitor review velocity, recency, and vulnerability across target App Store markets.

Measures:
1. Competitor review recency (days since last written review via Apple RSS)
2. Review velocity (number of reviews in the last 30d, 90d)
3. App update recency (days since currentVersionReleaseDate via iTunes API)
4. Vulnerability Score (identifies dormant incumbents and prime targets for ASA/ASO)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TARGETS = [
    # Ukraine
    ("ua", "стиснути фото"),
    ("ua", "стиснути відео"),
    ("ua", "очистити пам'ять"),
    
    # Germany
    ("de", "speicherplatz freigeben"),
    ("de", "fotos komprimieren"),
    ("de", "video komprimieren"),
    ("de", "fotos verkleinern"),
    
    # Poland
    ("pl", "czyszczenie zdjęć"),
    ("pl", "kompresja zdjęć"),
    ("pl", "zwolnij miejsce"),
    
    # Netherlands
    ("nl", "opslagruimte vrijmaken"),
    ("nl", "foto comprimeren"),
    
    # France
    ("fr", "liberer espace"),
    ("fr", "compresser photo"),
    
    # Spain
    ("es", "comprimir video"),
    ("es", "comprimir fotos"),
    
    # Japan
    ("jp", "容量削減"),
    ("jp", "写真圧縮"),
    
    # United States
    ("us", "shrink video"),
    ("us", "compress photo"),
    ("us", "photo size reducer"),
    
    # Great Britain
    ("gb", "shrink video"),
    ("gb", "compress photos"),
]

def fetch_json(url: str, timeout: float = 8.0) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None

def get_app_recent_reviews(country: str, app_id: int) -> dict:
    url = f"https://itunes.apple.com/{country}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"
    data = fetch_json(url)
    if not data:
        return {
            "has_rss_feed": False,
            "feed_review_count": 0,
            "days_since_last_review": None,
            "velocity_30d": 0,
            "velocity_90d": 0,
            "recent_rating": None,
            "last_review_date": None
        }
    
    entries = data.get("feed", {}).get("entry", [])
    review_entries = [e for e in entries if isinstance(e, dict) and "updated" in e and "im:rating" in e]
    
    if not review_entries:
        return {
            "has_rss_feed": True,
            "feed_review_count": 0,
            "days_since_last_review": None,
            "velocity_30d": 0,
            "velocity_90d": 0,
            "recent_rating": None,
            "last_review_date": None
        }
    
    now = datetime.now(timezone.utc)
    dates = []
    ratings = []
    
    for r in review_entries:
        try:
            dt = datetime.fromisoformat(r["updated"]["label"])
            dates.append(dt)
            ratings.append(int(r["im:rating"]["label"]))
        except Exception:
            continue
            
    if not dates:
        return {
            "has_rss_feed": True,
            "feed_review_count": 0,
            "days_since_last_review": None,
            "velocity_30d": 0,
            "velocity_90d": 0,
            "recent_rating": None,
            "last_review_date": None
        }
        
    days_since = (now - dates[0]).days
    v_30d = sum(1 for d in dates if (now - d).days <= 30)
    v_90d = sum(1 for d in dates if (now - d).days <= 90)
    recent_avg = sum(ratings[:10]) / len(ratings[:10]) if ratings else None
    
    return {
        "has_rss_feed": True,
        "feed_review_count": len(dates),
        "days_since_last_review": days_since,
        "velocity_30d": v_30d,
        "velocity_90d": v_90d,
        "recent_rating": round(recent_avg, 2) if recent_avg else None,
        "last_review_date": dates[0].strftime("%Y-%m-%d")
    }

def analyze_competitor(country: str, app: dict, rank: int) -> dict:
    app_id = app.get("trackId")
    name = app.get("trackName", "Unknown")
    total_ratings = app.get("userRatingCount", 0)
    avg_rating = round(app.get("averageUserRating", 0.0), 2)
    current_ver_date = app.get("currentVersionReleaseDate", "")
    version = app.get("version", "")
    seller = app.get("sellerName", "")
    
    now = datetime.now(timezone.utc)
    days_since_update = None
    if current_ver_date:
        try:
            up_dt = datetime.fromisoformat(current_ver_date.replace("Z", "+00:00"))
            days_since_update = (now - up_dt).days
        except Exception:
            pass
            
    reviews_info = get_app_recent_reviews(country, app_id)
    
    days_last_rev = reviews_info["days_since_last_review"]
    v_30d = reviews_info["velocity_30d"]
    
    # Classification
    if total_ratings < 50:
        classification = "🎯 Soft Target"
        vulnerability_score = 9.0
    elif days_last_rev is not None and days_last_rev > 120:
        classification = "💤 Sleeping Giant"
        vulnerability_score = 8.0
    elif days_since_update is not None and days_since_update > 180:
        classification = "🪦 Outdated Incumbent"
        vulnerability_score = 7.5
    elif v_30d >= 10:
        classification = "🔥 Active Defender"
        vulnerability_score = 3.0
    else:
        classification = "⚡ Moderate Defender"
        vulnerability_score = 5.0
        
    # Adjust vulnerability score
    if avg_rating < 4.2:
        vulnerability_score = min(10.0, vulnerability_score + 1.5)
    if total_ratings > 10000 and v_30d > 5:
        vulnerability_score = max(1.0, vulnerability_score - 3.0)
        
    return {
        "rank": rank,
        "app_id": app_id,
        "name": name,
        "seller": seller,
        "version": version,
        "total_ratings": total_ratings,
        "avg_rating": avg_rating,
        "days_since_update": days_since_update,
        "days_since_last_review": days_last_rev,
        "velocity_30d": v_30d,
        "velocity_90d": reviews_info["velocity_90d"],
        "recent_rating": reviews_info["recent_rating"],
        "last_review_date": reviews_info["last_review_date"],
        "classification": classification,
        "vulnerability_score": round(vulnerability_score, 1)
    }

def audit_target(country: str, query: str) -> dict:
    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&country={country}&entity=software&limit=5"
    data = fetch_json(url)
    results = data.get("results", []) if data else []
    
    competitors = []
    for idx, app in enumerate(results[:5], 1):
        comp = analyze_competitor(country, app, idx)
        competitors.append(comp)
        
    # Query vulnerability = average vulnerability of Top 3
    top3 = competitors[:3]
    avg_vuln = sum(c["vulnerability_score"] for c in top3) / len(top3) if top3 else 0.0
    
    # Determine prime strategy
    top1 = competitors[0] if competitors else None
    if top1 and top1["vulnerability_score"] >= 7.5:
        recommendation = f"🚀 HIGH OPPORTUNITY: Top 1 is {top1['classification']}. Attack with ASA Exact Match + reviews!"
    elif any(c["vulnerability_score"] >= 8.0 for c in competitors[:3]):
        recommendation = "⚡ MODERATE: Top 1 defended, but Top 2/3 is vulnerable. Target Top 3 placement."
    else:
        recommendation = "🛡️ COMPETITIVE: High velocity incumbents defend this key. Require significant ad budget."
        
    return {
        "country": country.upper(),
        "query": query,
        "total_results": len(results),
        "query_vulnerability": round(avg_vuln, 1),
        "recommendation": recommendation,
        "competitors": competitors
    }

def main():
    parser = argparse.ArgumentParser(description="Audit competitor review velocity and vulnerability")
    parser.add_argument("--markets", default="all", help="Comma-separated country codes or 'all'")
    parser.add_argument("--output-json", default="marketing/reports/competitor_velocity_audit_2026-09-08.json")
    parser.add_argument("--output-md", default="marketing/reports/competitor_velocity_audit_2026-09-08.md")
    args = parser.parse_args()
    
    targets = DEFAULT_TARGETS
    if args.markets != "all":
        mkts = set(args.markets.lower().split(","))
        targets = [t for t in targets if t[0] in mkts]
        
    print(f"Auditing {len(targets)} query targets across markets with multi-threading...")
    start_t = time.time()
    
    audits = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(audit_target, cc, q): (cc, q) for cc, q in targets}
        for fut in concurrent.futures.as_completed(futures):
            cc, q = futures[fut]
            try:
                res = fut.result()
                audits.append(res)
                print(f"  ✓ {res['country']:4} | '{q}': Vuln={res['query_vulnerability']}/10 ({res['recommendation'][:35]}...)")
            except Exception as e:
                print(f"  ✗ {cc.upper()} | '{q}': Error {e}")
                
    # Sort audits by query_vulnerability descending (highest opportunity first)
    audits.sort(key=lambda x: x["query_vulnerability"], reverse=True)
    
    # Save JSON
    Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(audits, f, indent=2, ensure_ascii=False)
    print(f"\nSaved JSON audit to {args.output_json}")
    
    # Generate Markdown Report
    lines = [
        "# Competitor Review Velocity & Vulnerability Audit",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} | **Total Queries Analyzed:** {len(audits)}",
        "",
        "## 🎯 Top Vulnerable Keywords (Highest Opportunity to Rank #1 / Top 3)",
        "",
        "| Rank | Country | Query | Query Vuln | Top 1 Competitor | Top 1 Ratings | Last Review | 30d Vel | Last Update | Recommendation |",
        "|---|---|---|---|---|---|---|---|---|---|"
    ]
    
    for idx, a in enumerate(audits, 1):
        top1 = a["competitors"][0] if a["competitors"] else {}
        t1_name = top1.get("name", "N/A")[:18]
        t1_ratings = f"{top1.get('total_ratings', 0)}★ ({top1.get('avg_rating', 0)})"
        last_rev = f"{top1.get('days_since_last_review')}d ago" if top1.get('days_since_last_review') is not None else "No RSS"
        v30 = top1.get("velocity_30d", 0)
        last_up = f"{top1.get('days_since_update')}d ago" if top1.get('days_since_update') is not None else "N/A"
        rec = a["recommendation"].split(":")[0]
        
        lines.append(f"| {idx} | {a['country']} | `{a['query']}` | **{a['query_vulnerability']}/10** | {t1_name} | {t1_ratings} | {last_rev} | {v30}/mo | {last_up} | {rec} |")
        
    lines.append("\n---\n")
    lines.append("## Detailed Competitor Breakdown by Market\n")
    
    for a in audits:
        lines.append(f"### {a['country']} — `{a['query']}` (Vulnerability: {a['query_vulnerability']}/10)")
        lines.append(f"**Strategy:** {a['recommendation']}\n")
        lines.append("| Pos | App Name | Ratings | Rating | Last Review | 30d Velocity | Last App Update | Classification | Vuln Score |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for c in a["competitors"]:
            last_rev = f"{c['days_since_last_review']}d ago" if c['days_since_last_review'] is not None else "N/A"
            last_up = f"{c['days_since_update']}d ago" if c['days_since_update'] is not None else "N/A"
            lines.append(f"| #{c['rank']} | {c['name'][:24]} | {c['total_ratings']} | {c['avg_rating']}★ | {last_rev} | {c['velocity_30d']} rev | {last_up} | {c['classification']} | **{c['vulnerability_score']}** |")
        lines.append("")
        
    Path(args.output_md).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output_md, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Saved Markdown report to {args.output_md}")
    print(f"Completed in {time.time() - start_t:.1f}s")

if __name__ == "__main__":
    main()
